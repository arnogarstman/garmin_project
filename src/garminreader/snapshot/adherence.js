// Plan against what was done. The page rebuilds its plan from the data on every render, so it keeps
// what it planned: each of the next 7 days' sessions goes into the artifact's database
// (settings/planlog), rewritten while the plan changes and fixed once the day has passed or has a
// run. adherence() matches the logged sessions to the runs, and reads Garmin Coach's workouts by
// their done or missed status. Without the `db` capability nothing is logged and only Garmin Coach
// is compared.
const PLANLOG_DOC = 'settings/planlog';
const PLANLOG_KEEP_DAYS = 120;
const KEY_KINDS = ['intervals', 'threshold', 'race-pace', 'long', 'race'];
const planlog = { ref: null, canWrite: false, days: null, pending: null, writing: false, timer: 0 };
const shiftIso = (date, n) => { const d = new Date(t(date)); return iso(new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)); };

// Log the planned session of each of the 7 days from today. A day that has passed (by the clock)
// or already has a run keeps what was logged, so finishing a session never rewrites its plan.
function logPlan(plan, ctx) {
  if (!planlog.ref || !planlog.canWrite || planlog.days === null) return;
  const clock = iso(new Date()), dataDay = iso(new Date(ctx.sig.x1)), start = dataDay > clock ? dataDay : clock;
  const ran = new Set(ctx.sig.runs.map(r => r.activity_date.slice(0, 10)));
  const same = (a, b) => a && a.k === b.k && a.t === b.t && a.km === b.km;
  const next = { ...(planlog.pending || planlog.days) };
  let changed = false;
  for (let k = 0; k < 7; k++) {
    const date = shiftIso(start, k);
    if (ran.has(date) && next[date]) continue;
    const s = plannedOn(plan, ctx, date);
    const entry = s ? { k: s.kind, t: s.title, km: Math.round(s.km * 10) / 10 } : { k: 'rest', t: 'Rest', km: 0 };
    if (!same(next[date], entry)) { next[date] = entry; changed = true; }
  }
  const oldest = shiftIso(clock, -PLANLOG_KEEP_DAYS);
  for (const d of Object.keys(next)) if (d < oldest) { delete next[d]; changed = true; }
  if (!changed) return;
  // Renders come in bursts (one per query on a live page): write once the burst has settled.
  planlog.pending = next;
  clearTimeout(planlog.timer);
  planlog.timer = setTimeout(flushPlanlog, 2000);
}

async function flushPlanlog() {
  if (planlog.writing || !planlog.pending) return;
  const days = planlog.pending;
  planlog.pending = null;
  planlog.writing = true;
  try {
    await planlog.ref.set({ days, updated_at: new Date().toISOString() });
    planlog.days = days;
  } catch {
    // Refused (a read-only view) or failing: stop logging for this visit rather than retry.
    planlog.canWrite = false;
  } finally {
    planlog.writing = false;
    if (planlog.pending && planlog.canWrite) flushPlanlog();
  }
}

// Whether a run did what the session asked: a long run or race at 80% of its distance or more,
// intervals and race-pace work with 8 minutes or more in zones 4-5, threshold with 15 or more in
// zones 3-5. An easy session counts once there is a run.
function sessionHit(kind, km, run) {
  const z = k => num(run[k]) ? run[k] : 0;
  if (kind === 'long' || kind === 'race') return run.km >= 0.8 * km;
  if (kind === 'intervals' || kind === 'race-pace') return z('z4') + z('z5') >= 8;
  if (kind === 'threshold') return z('z3') + z('z4') + z('z5') >= 15;
  return true;
}

// Planned against done on the days from `from` up to `to` (ISO dates, `to` excluded). A session
// takes a run on its own day, else on the day after or before when that day has no session of its own.
function adherence(runs, coach, from, to) {
  const logged = Object.entries(planlog.days || {}).filter(([d]) => d >= from && d < to).sort(([a], [b]) => a < b ? -1 : 1);
  // Swims are not runs: the run data cannot say whether they were done, so they are not compared.
  const planned = logged.filter(([, e]) => e.k !== 'rest' && e.k !== 'swim');
  const busy = new Set(planned.map(([d]) => d)), byDay = new Map(), used = new Set();
  for (const r of runs) { const d = r.activity_date.slice(0, 10); byDay.set(d, [...(byDay.get(d) || []), r]); }
  const sessions = planned.map(([date, e]) => {
    let run = null;
    for (const d of [date, shiftIso(date, 1), shiftIso(date, -1)]) {
      if (d !== date && (busy.has(d) || d >= to)) continue;
      run = (byDay.get(d) || []).filter(r => !used.has(r)).sort((a, b) => b.km - a.km)[0] || null;
      if (run) break;
    }
    if (run) used.add(run);
    return { date, kind: e.k, title: e.t, km: e.km, run, key: KEY_KINDS.includes(e.k), hit: !!run && sessionHit(e.k, e.km, run) };
  });
  const ranKm = runs.filter(r => { const d = r.activity_date.slice(0, 10); return d >= from && d < to; }).reduce((s, r) => s + r.km, 0);
  const gc = (coach || []).filter(c => { const d = String(c.d).slice(0, 10); return d >= from && d < to && !c.rest && c.name; });
  const gcDone = gc.filter(c => /COMPLETE/.test(c.status || '') && !/NOT/.test(c.status || ''));
  return {
    days: logged.length, sessions, n: sessions.length, done: sessions.filter(s => s.run).length,
    key: sessions.filter(s => s.key).length, keyHit: sessions.filter(s => s.key && s.hit).length,
    plannedKm: sessions.reduce((s, x) => s + x.km, 0), ranKm,
    coach: { n: gc.length, done: gcDone.length, missed: gc.filter(c => !gcDone.includes(c)) },
  };
}

// The first logged day, for saying since when the plan is compared.
const planlogStart = () => Object.keys(planlog.days || {}).sort()[0] || null;
const planlogActive = () => !!planlog.ref;

async function startAdherence() {
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  if (typeof db?.doc !== 'function') return;
  try { user = await window.claude.use('user'); } catch { user = null; }
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  planlog.canWrite = canWrite !== false;
  planlog.ref = db.doc(PLANLOG_DOC);
  planlog.ref.onSnapshot(snap => {
    const days = snap.exists ? snap.data().days : null;
    planlog.days = days && typeof days === 'object' ? days : {};
    rerender();
  }, () => { planlog.ref = null; planlog.days = null; rerender(); });
}

startAdherence();
