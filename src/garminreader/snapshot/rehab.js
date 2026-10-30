// Knee rehab: a mode for runner's knee (pain around or behind the kneecap) that the athlete switches
// on in the training plan. It lives in the artifact's database (settings/rehab: {knee: {on, since}})
// like the gym days. While it is on, buildPlan() drops volume and grows it slowly, keeps long runs
// short, holds back fast running for the first weeks, and weekSessions() swaps easy runs for swims;
// rest and leg days get the knee exercises. A knee injury noted under Events suggests the mode.
// Without the `db` capability the mode cannot be switched on and the plan stays as it is.
const REHAB_DOC = 'settings/rehab';
const rehab = { ref: null, canWrite: false, knee: null, busy: false, msg: '' };

// Settings the plan uses while the mode is on: the share of the pre-injury weekly volume to restart
// at, weekly growth, the highest share of that volume to build back to, the longest long run, the
// weeks without intervals or race-pace work, and the swims that replace easy runs, first weeks and later.
const KNEE = { start: 0.7, growth: 1.05, cap: 1, longMax: 12, longStep: 1, noFastWeeks: 3, swimsEarly: 2, swimsLater: 1, earlyWeeks: 2 };
const KNEE_RUN_NOTE = 'Flat route, soft surface where you can, short quick steps (cadence about 5% up), no downhill.';
const KNEE_EXERCISES = 'Knee exercises, 15 min: clamshells 3 × 15, side plank 3 × 30 s, slow step-downs 3 × 10, wall sit 3 × 30–45 s.';
const KNEE_PAIN_RULE = 'Pain rule: up to 3 out of 10 during the run is fine if it has settled by the next morning. Worse than that, or still there in the morning: stop that session and swim or rest instead. If it does not improve within 2 to 3 weeks, see a physiotherapist.';

const kneeOn = () => !!rehab.knee?.on;
// Whole weeks since the mode was switched on, counted from the Monday of that week (0 in the first week).
function kneeWeek(weekStartMs, sig) {
  const since = rehab.knee?.since ? sig.weekStart(rehab.knee.since) : sig.thisWeek;
  return Math.max(0, Math.round((weekStartMs - since) / (7 * DAY)));
}

// An active knee injury under Events (from the last 21 days, or a span still open), for the hint.
function kneeEvent() {
  const today = iso(new Date()), from = shiftIso(today, -21);
  return (evs.items || []).find(n => n.kind === 'injury' && /knie|knee/i.test(n.note || '') && ((n.to || n.from) >= from || !n.to));
}

// Turn easy runs into swims in a week of sessions (Map day -> session), the runs closest to the
// long run first: the knee recovers best with a day off from impact around it.
function kneeSwims(out, w, sig) {
  const n = kneeWeek(w.start, sig) < KNEE.earlyWeeks ? KNEE.swimsEarly : KNEE.swimsLater;
  const easy = [...out.entries()].filter(([, s]) => s.kind === 'easy').map(([d]) => d).sort((a, b) => Math.abs(a - 6) - Math.abs(b - 6));
  for (const d of easy.slice(0, n)) {
    out.set(d, { kind: 'swim', title: 'Swim', km: 0, minutes: 40, detail: '30–45 min easy front crawl, or pool running; a pull buoy if kicking bothers the knee. No breaststroke kick.' });
  }
}

// The line above the plan: the mode's state, what it does, the pain rule, and the switch.
function kneeLine() {
  if (!rehab.ref) return '';
  const btn = label => rehab.canWrite ? ` <button type="button" class="livebtn${kneeOn() ? '' : ' primary'}" id="knee-toggle"${rehab.busy ? ' disabled' : ''}>${label}</button>` : '';
  const msg = rehab.msg ? ` <span class="pill warn">${esc(rehab.msg)}</span>` : '';
  if (kneeOn()) return `<div class="notes warn"><p><b>Knee rehab on</b> since ${fmtDate(rehab.knee.since)}: volume restarts at ${Math.round(KNEE.start * 100)}% and grows about ${Math.round((KNEE.growth - 1) * 100)}% a week, long runs stay at ${KNEE.longMax} km or less, no intervals or race-pace work for the first ${KNEE.noFastWeeks} weeks, and swims replace easy runs. Every run: ${KNEE_RUN_NOTE.toLowerCase()}${btn('Knee has recovered')}${msg}</p><p class="cap">${KNEE_PAIN_RULE}</p></div>`;
  const ev = kneeEvent();
  return `<p class="cap">${ev ? `<b>Knee injury noted</b> (${fmtDate(ev.from)}${ev.note ? `, ${esc(ev.note)}` : ''}). ` : ''}Runner's knee? Knee rehab mode lowers and slows the plan, adds swims and knee exercises.${btn('Start knee rehab')}${msg}</p>`;
}

function bindKnee() {
  const b = $('knee-toggle');
  if (b) b.onclick = () => saveKnee(kneeOn() ? { on: false, since: rehab.knee.since } : { on: true, since: iso(new Date()) });
}

async function saveKnee(knee) {
  if (rehab.busy) return;
  rehab.busy = true;
  rehab.msg = '';
  const before = rehab.knee;
  rehab.knee = knee;
  rerender();
  try {
    await rehab.ref.set({ knee, updated_at: new Date().toISOString() });
  } catch (err) {
    rehab.knee = before;
    if (err.code === 'invalid_argument' || err.code === 'permission_denied') rehab.canWrite = false;
    rehab.msg = err.code === 'quota_exceeded' ? 'The page storage is full.' : 'Saving failed; try again in a moment.';
  } finally {
    rehab.busy = false;
    rerender();
  }
}

async function startRehab() {
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  if (typeof db?.doc !== 'function') return;
  try { user = await window.claude.use('user'); } catch { user = null; }
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  rehab.canWrite = canWrite !== false;
  rehab.ref = db.doc(REHAB_DOC);
  rehab.ref.onSnapshot(snap => {
    if (rehab.busy) return; // a save in flight already shows its result
    const k = snap.exists ? snap.data().knee : null;
    rehab.knee = k && typeof k === 'object' && /^\d{4}-\d{2}-\d{2}$/.test(k.since || '') ? { on: !!k.on, since: k.since } : null;
    rerender();
  }, () => { rehab.ref = null; rehab.knee = null; rerender(); });
  rerender();
}

startRehab();
