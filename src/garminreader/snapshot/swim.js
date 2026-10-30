// Swim days and knee rehab.
// Swim days: easy swims or swim intervals, entered by hand in the training plan like the gym days
// (settings/swim: {weekly: {weekday: kind}, days: {date: kind or 'none'}}). The plan shows each swim
// beside the run, and the meal plan (meals.js) adds its energy and carbohydrate to that day's targets.
// Knee rehab: while an injury event about the knee is open (settings/events, events.js), the plan
// eases running in stages from the event's start: hard sessions become swims, runs get shorter and
// stay flat and easy, and the days without a run carry a short knee strength routine. General
// guidance for patellofemoral pain ("runner's knee"), not a diagnosis or a physio's programme.
const SWIM_DOC = 'settings/swim';
const SWIM_KEEP_DAYS = 120;
const SWIM_KINDS = {
  easy: { label: 'Easy swim', min: 40, detail: '30–40 min of steady front crawl with a pull buoy if kicking bothers the knee; breathe every 3 strokes.' },
  intervals: { label: 'Swim intervals', min: 45, detail: '10 min easy, 8–10 × 100 m at a hard but even effort with 20 s rest, 5 min easy. Front crawl, not breaststroke.' },
};
// Energy of a swim above resting, in kcal per kg of body weight (about 6 MET for an easy 40 minutes,
// 8 for intervals), and the extra carbohydrate it asks, in g per kg.
const SWIM_KCAL_PER_KG = { easy: 4, intervals: 5.5 };
const SWIM_CARBS_PER_KG = { easy: 0.5, intervals: 1 };
const swim = { ref: null, canWrite: false, weekly: {}, days: {}, busy: false, msg: '' };

// The swim on a date (easy or intervals), or null: the day's own choice, else the weekly pattern.
function swimOn(date) {
  const v = swim.days[date] ?? swim.weekly[weekdayOf(date)];
  return SWIM_KINDS[v] ? v : null;
}

// --- Knee rehab ---------------------------------------------------------------------------------

// An injury note about the knee: "runner's knee", "lopersknie", "knie", "patella", ...
const KNEE_RE = /kn(ee|ie)|patell/i;
const KNEE_STRENGTH = 'Knee strength, 15 min, pain-free: 3 × 15 side-lying leg raises and clamshells, 3 × 12 glute bridges, ' +
  '3 × 30–45 s wall sit at a comfortable depth, 3 × 10 slow step-downs from a low step, 3 × 15 calf raises.';
const KNEE_PAIN_RULE = 'Pain rule: up to 3 out of 10 during a run is fine if it settles by the next morning; more, or worse the next day, means go back a stage.';

// The open knee injury on a date: {from, week} (week 0 is the first week), or null.
function kneeOn(date) {
  const n = evs.items.filter(e => e.kind === 'injury' && KNEE_RE.test(e.note || '') && e.from <= date && (!e.to || e.to >= date))
    .sort((a, b) => a.from < b.from ? 1 : -1)[0];
  return n ? { id: n.id, from: n.from, week: Math.floor((t(date) - t(n.from)) / (7 * DAY)) } : null;
}
// The rehab stage by weeks since the knee started: calm (weeks 1–2), rebuild (3–4), return (5–6),
// then still open after 6 weeks: keep returning, and see a physio.
const kneeStage = week => week < 2 ? 'calm' : week < 4 ? 'rebuild' : 'return';
const KNEE_STAGES = {
  calm: { label: 'Calm', share: 0.5, maxKm: 5, note: 'Calm the knee: short, flat, easy runs on soft ground; hard sessions become swims.' },
  rebuild: { label: 'Rebuild', share: 0.7, maxKm: 8, note: 'Rebuild: runs grow back to about 70%, still easy and flat; swims keep the hard work.' },
  return: { label: 'Return', share: 0.85, maxKm: 14, note: 'Return: strides come back and the long run grows to about 80%; one hard session stays a swim.' },
};
const HARD_KINDS = ['intervals', 'threshold', 'race-pace'];

// The session of a day, adapted to an open knee injury; unchanged without one.
function rehabSession(s, date, plan) {
  const knee = kneeOn(date);
  if (!s || !knee || s.kind === 'race') return s;
  const stage = KNEE_STAGES[kneeStage(knee.week)], range = ([a, b]) => `${pace(a)}–${pace(b)}`;
  const easyRun = (km, title) => ({
    kind: 'easy', title, km, knee: true,
    detail: `${Math.round(km)} km at ${range(plan.paces.easy)} /km on flat, soft ground; a cadence 5–10% higher than usual, short steps. Walk a minute whenever the knee speaks up.`,
  });
  // Hard sessions become swims: intervals for a hard one, the rest easy (in Return one stays strides).
  if (HARD_KINDS.includes(s.kind)) {
    if (stage === KNEE_STAGES.return && s.kind === 'threshold') return { ...easyRun(Math.min(s.km, 8), 'Easy + strides (knee)'), detail: `${Math.round(Math.min(s.km, 8) - 1)} km easy on the flat, then 4 × 20 s relaxed strides; skip them if the knee aches.` };
    return { kind: 'swim', title: 'Swim intervals (knee)', km: 0, swim: 'intervals', knee: true, detail: SWIM_KINDS.intervals.detail };
  }
  if (s.kind === 'long') {
    const km = Math.min(s.km * (stage === KNEE_STAGES.return ? 0.8 : stage.share), stage.maxKm);
    return easyRun(km, stage === KNEE_STAGES.calm ? 'Easy run (knee, instead of the long run)' : 'Long run, shortened (knee)');
  }
  if (s.kind === 'strides' && stage !== KNEE_STAGES.return) return easyRun(Math.min(s.km * stage.share, stage.maxKm), 'Easy run (knee)');
  if (s.kind === 'easy' || s.kind === 'strides' || s.kind === 'shakeout') return easyRun(Math.min(s.km * stage.share, stage.maxKm), `${s.title.replace(/ \(.*\)$/, '')} (knee)`);
  return s;
}

// Why a knee rehab session helps.
function kneeWhy(s, date) {
  const knee = kneeOn(date), stage = knee && KNEE_STAGES[kneeStage(knee.week)];
  const late = knee && knee.week >= 6 ? ' Six weeks on and still sore: have a physio look at it.' : '';
  if (s.kind === 'swim') return `Keeps your aerobic fitness and heart rate work without loading the knee, so the run comes back on a fitter engine. Front crawl or a pull buoy: breaststroke kick twists the knee.${late}`;
  return `Running keeps the tendon and kneecap used to load, which helps it heal, as long as it stays easy, flat and short (${stage.label.toLowerCase()} stage, about ${Math.round(stage.share * 100)}% of your plan). Downhill and hard efforts load the knee most, so they wait. ${KNEE_PAIN_RULE}${late}`;
}

// The knee line above the week: the stage and its rules, or the button that starts rehab.
function kneeLine(weekDates) {
  const knee = weekDates.map(kneeOn).find(Boolean);
  const canAdd = evs.ref && evs.canWrite;
  if (!knee) return `<p class="cap"><b>Knee:</b> runner's knee or another knee niggle? ${canAdd ? '<button type="button" class="livebtn" id="knee-start">I have runner\'s knee</button> eases the plan around it,' : 'Add an injury event with "knee" in its note under History → Events and the plan eases around it,'} with swims for the hard work and a knee strength routine.</p>`;
  const stage = KNEE_STAGES[kneeStage(knee.week)];
  const end = canAdd ? ` <button type="button" class="livebtn" id="knee-end">Knee recovered</button>` : '';
  return `<div class="knee"><p><b>Knee rehab, week ${knee.week + 1}</b> (since ${fmtDate(knee.from)}) · <b>${stage.label}:</b> ${stage.note}${end}</p>` +
    `<p class="cap">${KNEE_PAIN_RULE} On days without a run: ${KNEE_STRENGTH}${knee.week >= 6 ? ' <span class="pill warn">six weeks</span> Still sore after six weeks: see a physio.' : ''} Guidance, not a diagnosis: see a physio or doctor for swelling, locking, giving way or pain at rest.</p></div>`;
}

// Start rehab (an injury event from today) or close it (the open event ends yesterday).
function bindKnee() {
  const start = $('knee-start'), end = $('knee-end');
  if (start) start.onclick = () => saveEvents([...evs.items, { id: Date.now().toString(36), kind: 'injury', from: iso(new Date()), to: '', note: "Runner's knee" }].slice(-EVENTS_MAX));
  if (end) end.onclick = () => {
    const today = iso(new Date()), open = kneeOn(today);
    if (open) saveEvents(evs.items.map(e => e.id === open.id ? { ...e, to: e.from < today ? shiftIso(today, -1) : today } : e));
  };
}

// --- Swim days in the plan ----------------------------------------------------------------------

// The swim part of a day in the plan: the session with its reason, and the picker when this view may save.
// `run` is the day's planned session (already a swim when knee rehab turned a hard session into one).
function swimCell(date, run) {
  const kind = swimOn(date), sw = kind && SWIM_KINDS[kind];
  let why = '';
  if (kind && run && ['intervals', 'threshold', 'race-pace', 'long'].includes(run.kind)) why = `A ${run.title.toLowerCase()} is on today as well: keep the swim easy, or swim on a rest day instead.`;
  else if (kind === 'intervals') why = 'Hard aerobic work with no impact: it lifts your fitness while your legs recover from running.';
  else if (kind) why = kneeOn(date) ? 'Easy aerobic time that unloads the knee while it heals.' : 'Easy aerobic time with no impact: it adds fitness and loosens legs that are tired from running.';
  const body = sw && run?.swim !== kind ? `<div class="gym swimpart"><h4>${sw.label} <span class="km">${sw.min} min</span></h4><p>${esc(sw.detail)}</p><p class="why"><b>Why:</b> ${esc(why)}</p></div>` : '';
  if (!swim.ref || !swim.canWrite) return body;
  const opts = [['', 'No swim'], ...Object.entries(SWIM_KINDS).map(([k, v]) => [k, v.label])]
    .map(([k, l]) => `<option value="${k}"${(kind || '') === k ? ' selected' : ''}>${l}</option>`).join('');
  return `${body}<label class="gymsel">Swim<select data-swim="${date}"${swim.busy ? ' disabled' : ''}>${opts}</select></label>`;
}

// The line above the week: what the picker does, and the button that repeats this week's swims.
function swimLine(weekDates) {
  if (!swim.ref) return '<p class="cap">Open the page on claude.ai to add swims to your week; they count in the food targets under Nutrition.</p>';
  const n = weekDates.filter(swimOn).length;
  const repeat = swim.canWrite ? ` <button type="button" class="livebtn" id="swim-repeat"${swim.busy ? ' disabled' : ''}>${n ? 'Repeat these swims every week' : 'No swims every week'}</button>` : '';
  return `<p class="cap"><b>Swim:</b> ${swim.canWrite ? 'pick an easy swim or swim intervals per day below. ' : ''}Each swim adds to that day's energy and carbohydrate under Nutrition.${swim.msg ? ` <span class="pill warn">${esc(swim.msg)}</span>` : ''}${repeat}</p>`;
}

// Wire the swim pickers, the repeat button and the knee buttons; weekDates are the shown week's 7 days.
function bindSwim(root, weekDates) {
  for (const sel of root.querySelectorAll('[data-swim]')) sel.onchange = () => {
    saveSwim(swim.weekly, { ...swim.days, [sel.dataset.swim]: sel.value || 'none' });
  };
  const repeat = $('swim-repeat');
  if (repeat) repeat.onclick = () => {
    const weekly = Object.fromEntries(weekDates.map(d => [weekdayOf(d), swimOn(d)]).filter(([, k]) => k));
    // From this week on the pattern holds: drop the days' own choices that would override it.
    saveSwim(weekly, Object.fromEntries(Object.entries(swim.days).filter(([d]) => d < weekDates[0])));
  };
  bindKnee();
}

async function saveSwim(weekly, days) {
  if (swim.busy) return;
  const oldest = shiftIso(iso(new Date()), -SWIM_KEEP_DAYS);
  days = Object.fromEntries(Object.entries(days).filter(([d]) => d >= oldest));
  swim.busy = true;
  swim.msg = '';
  // Shown at once; the snapshot confirms it.
  const before = { weekly: swim.weekly, days: swim.days };
  Object.assign(swim, { weekly, days });
  rerender();
  try {
    await swim.ref.set({ weekly, days, updated_at: new Date().toISOString() });
  } catch (err) {
    Object.assign(swim, before);
    if (err.code === 'invalid_argument' || err.code === 'permission_denied') swim.canWrite = false;
    swim.msg = err.code === 'quota_exceeded' ? 'The page storage is full.' : 'Saving failed; try again in a moment.';
  } finally {
    swim.busy = false;
    rerender();
  }
}

async function startSwim() {
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  if (typeof db?.doc !== 'function') return;
  try { user = await window.claude.use('user'); } catch { user = null; }
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  swim.canWrite = canWrite !== false;
  swim.ref = db.doc(SWIM_DOC);
  swim.ref.onSnapshot(snap => {
    const v = snap.exists ? snap.data() : {};
    const valid = o => o && typeof o === 'object' ? o : {};
    if (swim.busy) return; // a save in flight already shows its result
    swim.weekly = valid(v.weekly);
    swim.days = Object.fromEntries(Object.entries(valid(v.days)).filter(([d]) => /^\d{4}-\d{2}-\d{2}$/.test(d)));
    rerender();
  }, () => { swim.ref = null; rerender(); });
  rerender();
}

startSwim();
