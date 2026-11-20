// Weekly report: once a week Claude (the `sample` capability) writes a coach's letter on the last
// full week, Monday to Sunday: what was done against the plan, how recovery and form went, the knee,
// the race goal, and what next week asks. The page gathers the facts itself (it knows the plan log,
// the gym days, swims and rows, which the warehouse does not), so Claude only reads and writes.
// Reports live in the artifact's database (settings/weekly: {reports: {monday: {generated_at, result}}}),
// written once per week: the first time someone who may edit opens the page after the week ends,
// or on the button. Without `sample` or `db` the section shows the last report, or says why not.
const WEEKLY_DOC = 'settings/weekly';
const WEEKLY_KEEP = 12;
const weekly = { sample: null, ref: null, canWrite: false, reports: {}, loaded: false, busy: null, error: '', tried: new Set(), ctl: null };

// The last full week (Monday ISO date) by the data's last day, and the week before it.
function weeklyWeeks() {
  const sig = planCtx?.sig;
  if (!sig) return null;
  const w1 = iso(new Date(sig.thisWeek - 7 * DAY)), w0 = iso(new Date(sig.thisWeek - 14 * DAY)), next = iso(new Date(sig.thisWeek));
  return { w1, w0, next };
}

// The facts of a week, as plain text lines for the prompt.
function weeklyFacts(D, w) {
  const { w1, w0, next } = w, end = shiftIso(w1, 7);
  const inWeek = (d, from) => { const k = String(d).slice(0, 10); return k >= from && k < shiftIso(from, 7); };
  const runs = (D.runs || []).filter(r => inWeek(r.activity_date, w1)), before = (D.runs || []).filter(r => inWeek(r.activity_date, w0));
  const other = (D.history || []).filter(r => inWeek(r.activity_date, w1) && !/run/i.test(r.type || ''));
  const days = (D.daily || []).filter(r => inWeek(r.d, w1)), prevDays = (D.daily || []).filter(r => inWeek(r.d, w0));
  const avg = (rows, k) => { const v = rows.map(r => r[k]).filter(num); return v.length ? (v.reduce((s, x) => s + x, 0) / v.length).toFixed(0) : 'unknown'; };
  const km = rows => rows.reduce((s, r) => s + (r.km || 0), 0).toFixed(1);
  const zone = r => ['z1', 'z2', 'z3', 'z4', 'z5'].map(k => Math.round(r[k] || 0)).join('/');
  const a = adherence(D.runs || [], D.coach, w1, end);
  const dates = Array.from({ length: 7 }, (_, i) => shiftIso(w1, i));
  const gymDays = dates.map(d => gymOn(d) && `${dayName(d)} ${GYM_KINDS[gymOn(d)].label}`).filter(Boolean);
  const swims = dates.map(d => swimOn(d) && `${dayName(d)} ${SWIM_KINDS[swimOn(d)].label}`).filter(Boolean);
  const form = (D.form || []).filter(r => inWeek(r.activity_date, w1));
  const G = planCtx?.G, R = G && RACES[G.distance], st = D.status || {};
  const knee = kneeOn(dates[6]);
  const nextWeek = upcomingSessions(14).filter(s => s.date >= next && s.date < shiftIso(next, 7));
  const notes = (evs.items || []).filter(n => n.from < end && (!n.to || n.to >= w1)).map(n => `${n.kind}${n.note ? ` (${n.note})` : ''} from ${n.from}${n.to ? ` to ${n.to}` : ''}`);
  const lines = [
    `Week: Monday ${w1} to Sunday ${shiftIso(w1, 6)}.`,
    `Runs this week (${runs.length}, ${km(runs)} km; the week before: ${before.length}, ${km(before)} km):`,
    ...runs.map(r => `- ${r.activity_date.slice(0, 10)} ${r.activity_name}: ${r.km} km at ${num(r.pace) ? pace(r.pace) : '?'} /km, avg HR ${r.avg_hr ?? '?'}, minutes in zones 1-5 ${zone(r)}`),
    `Other activities this week: ${other.map(r => `${r.activity_date.slice(0, 10)} ${lower(r.type)} ${Math.round(r.min || 0)} min`).join('; ') || 'none'}.`,
    `Claude's plan for the week against what was run: ${a.n ? `${a.done} of ${a.n} planned runs done, key sessions hit ${a.keyHit} of ${a.key}, planned ${Math.round(a.plannedKm)} km. ${a.sessions.map(x => `${x.date} ${x.title} ${Math.round(x.km)} km: ${x.run ? (x.hit ? 'done' : 'run, but not as asked') : 'missed'}`).join('; ')}` : 'no plan logged for this week'}.`,
    `Garmin Coach that week: ${a.coach.n ? `${a.coach.done} of ${a.coach.n} workouts done` : 'none'}.`,
    `Gym days planned: ${gymDays.join(', ') || 'none'}. Swims and rows planned: ${swims.join(', ') || 'none'} (planned, not confirmed by the data).`,
    `Recovery this week (week before): HRV ${avg(days, 'hrv')} (${avg(prevDays, 'hrv')}) ms, resting HR ${avg(days, 'rhr')} (${avg(prevDays, 'rhr')}) bpm, sleep score ${avg(days, 'sleep')} (${avg(prevDays, 'sleep')}), readiness ${avg(days, 'ready')} (${avg(prevDays, 'ready')}). Load ratio at the end of the week: ${days.length && num(days[days.length - 1].acwr) ? days[days.length - 1].acwr : 'unknown'}.`,
    `Running form this week: ${form.length ? form.map(r => `${r.activity_date.slice(0, 10)} cadence ${r.cadence} spm, stride ${r.stride} m, ground contact ${r.gct} ms${num(r.balance) ? `, balance ${r.balance}% left` : ''}, vertical ratio ${r.vr}% (${r.chest ? 'chest strap' : 'wrist'})`).join('; ') : 'no runs with running dynamics'}.`,
    `Knee: ${knee ? `runner's knee rehab, week ${knee.week + 1} since ${knee.from}` : 'no open knee injury noted'}. Notes in the week: ${notes.join('; ') || 'none'}.`,
    `Race goal: ${G ? `${G.name}${R ? ` (${R.label})` : ''}${G.date ? ` on ${G.date}` : ''}${G.target ? `, target ${G.target}` : ''}${R && num(st[R.status]) ? `; Garmin predicts ${hms(st[R.status])} today` : ''}` : 'none set'}.`,
    `The rest of this week in Claude's plan, from today: ${nextWeek.map(s => `${dayName(s.date)} ${s.title}${s.km ? ` ${Math.round(s.km)} km` : ''}${s.gym ? ` + ${GYM_KINDS[s.gym].label}` : ''}${s.swim && s.kind !== 'swim' ? ` + ${SWIM_KINDS[s.swim].label}` : ''}`).join('; ') || 'no plan'}.`,
  ];
  return lines.join('\n');
}

function weeklyPrompt(facts) {
  return `You are the athlete's running coach, writing the weekly check-in on the week that just ended. The athlete is training for a race, recovering from runner's knee at times, and also does gym work, swimming and rowing. Read the facts, judge the week honestly and plainly, cite numbers, and keep it short: this is read on a phone.

${facts}

Reply with only JSON in this shape:
{"headline":"The week in at most ten words.","summary":"Two or three sentences: how the week went overall.","went_well":["Up to three things, with numbers."],"to_work_on":["Up to three things, each with what to do about it."],"form":"One or two sentences on running form, or on what to measure next if there is no data.","recovery":"One sentence on recovery.","next_week":"Two sentences: what the rest of this week asks and the one session that matters most.","focus":"The single focus for this week, at most eight words."}`;
}

function renderWeekly(D) {
  const el = $('weekly');
  if (!el) return;
  const w = weeklyWeeks();
  const saved = Object.entries(weekly.reports).sort(([a], [b]) => a < b ? 1 : -1);
  const has = w && weekly.reports[w.w1];
  const can = weekly.sample && weekly.canWrite && w;
  // Write last week's report once, when the saved reports and the plan log have loaded.
  if (can && !has && !weekly.busy && weekly.loaded && planlog.days !== null && !weekly.tried.has(w.w1)) {
    weekly.tried.add(w.w1);
    makeWeekly(D, w);
  }
  const list = (title, items) => Array.isArray(items) && items.length ? `<div><h4>${title}</h4><ul>${items.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : '';
  const full = (monday, r) => `<div class="card good weekcard"><div class="head"><span class="eyebrow">Week of ${fmtDate(monday)} · Claude</span>${r.focus ? `<span class="pill good">${esc(r.focus)}</span>` : ''}</div>` +
    `<h3>${esc(r.headline)}</h3><p class="why">${esc(r.summary)}</p><div class="wlist">${list('Went well', r.went_well)}${list('To work on', r.to_work_on)}</div>` +
    `${r.form ? `<p><b>Form.</b> ${esc(r.form)}</p>` : ''}${r.recovery ? `<p><b>Recovery.</b> ${esc(r.recovery)}</p>` : ''}${r.next_week ? `<p><b>This week.</b> ${esc(r.next_week)}</p>` : ''}</div>`;
  let html = '';
  if (weekly.busy) html += `<p class="livestate" role="status">${esc(weekly.busy)}</p><button type="button" class="livebtn" id="weekly-stop">Stop</button>`;
  if (saved.length) {
    const [[monday, latest], ...older] = saved;
    html += full(monday, latest.result);
    if (older.length) html += '<div class="wolder">' + older.map(([m, x]) => `<details><summary><span class="d">${fmtDate(m)}</span><h3>${esc(x.result.headline)}</h3></summary><div class="body"><p>${esc(x.result.summary)}</p>${x.result.next_week ? `<p><b>That week.</b> ${esc(x.result.next_week)}</p>` : ''}</div></details>`).join('') + '</div>';
  } else if (!weekly.busy) {
    html += `<p class="cap">${!weekly.ref ? 'Open the page on claude.ai to get a weekly report from Claude.' : !weekly.sample ? 'Allow Claude for this page (its Permissions menu) to get a weekly report.' : !weekly.canWrite ? 'No weekly report yet; it is written when the page\'s owner opens it after a week ends.' : 'The first report is written for the last full week.'}</p>`;
  }
  if (can && !weekly.busy) html += `<button type="button" class="livebtn" id="weekly-make">${has ? 'Write last week\'s report again' : 'Write last week\'s report'}</button>`;
  if (weekly.error) html += `<p class="mmsg">${esc(weekly.error)}</p>`;
  el.innerHTML = html;
  const make = $('weekly-make'), stop = $('weekly-stop');
  if (make) make.onclick = () => makeWeekly(lastD, weeklyWeeks());
  if (stop) stop.onclick = () => weekly.ctl?.abort();
}

async function makeWeekly(D, w) {
  if (!w || !weekly.sample || weekly.busy) return;
  weekly.ctl = new AbortController();
  weekly.error = '';
  weekly.busy = `Claude is writing the report on the week of ${fmtDate(w.w1)}. This takes about a minute.`;
  rerender();
  try {
    const result = await weekly.sample.json(weeklyPrompt(weeklyFacts(D, w)), { signal: weekly.ctl.signal, cache: false });
    if (typeof result?.headline !== 'string' || typeof result?.summary !== 'string') throw { code: 'invalid_json' };
    const reports = Object.fromEntries(Object.entries({ ...weekly.reports, [w.w1]: { generated_at: new Date().toISOString(), result } })
      .sort(([a], [b]) => a < b ? 1 : -1).slice(0, WEEKLY_KEEP));
    weekly.reports = reports; // shown at once; the snapshot confirms it
    try { await weekly.ref.set({ reports, updated_at: new Date().toISOString() }); } catch { weekly.error = 'The report could not be saved; it is shown until you leave the page.'; }
  } catch (e) {
    weekly.error = {
      cancelled: '',
      not_granted: 'Claude is not allowed for this page; allow it from the page\'s Permissions menu.',
      rate_limited: 'Claude is busy or your usage limit is reached; try again later.',
      invalid_json: 'Claude\'s answer was not usable; try again.',
      refused: 'Claude declined to write the report; try again later.',
    }[e.code] ?? 'Writing the report failed; try again in a moment.';
    if (['not_granted', 'sampling_disabled', 'not_declared', 'capability_disabled', 'capability_removed'].includes(e.code)) weekly.sample = null;
  } finally {
    weekly.busy = null;
    rerender();
  }
}

async function startWeekly() {
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  try { weekly.sample = window.claude ? await window.claude.use('sample') : null; } catch { weekly.sample = null; }
  if (typeof db?.doc !== 'function') { weekly.sample = null; rerender(); return; }
  try { user = await window.claude.use('user'); } catch { user = null; }
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  weekly.canWrite = canWrite !== false;
  weekly.ref = db.doc(WEEKLY_DOC);
  weekly.ref.onSnapshot(snap => {
    if (weekly.busy) return;
    const r = snap.exists ? snap.data().reports : null;
    weekly.reports = r && typeof r === 'object' ? Object.fromEntries(Object.entries(r).filter(([k, v]) => /^\d{4}-\d{2}-\d{2}$/.test(k) && typeof v?.result?.headline === 'string')) : {};
    weekly.loaded = true;
    rerender();
  }, () => { weekly.ref = null; weekly.error = 'The saved reports could not be loaded on this view.'; rerender(); });
}

startWeekly();
