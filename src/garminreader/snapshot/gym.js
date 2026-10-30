// Gym days: strength training, split in chest, back and leg days, entered by hand in the training
// plan. A day's choice, or the week's pattern when the day has none, lives in the artifact's database
// (settings/gym: {weekly: {weekday: kind}, days: {date: kind or 'none'}}), like the race goal. The
// plan shows each gym day beside the run, and the meal plan (meals.js) adds its energy, protein and
// carbohydrate to that day's targets. Without the `db` capability no gym days exist.
const GYM_DOC = 'settings/gym';
const GYM_KEEP_DAYS = 120;
const GYM_KINDS = {
  chest: { label: 'Chest day', detail: 'Chest, shoulders and triceps: presses and flyes, 3–4 sets of 6–12 reps.' },
  back: { label: 'Back day', detail: 'Back and biceps: rows, pull-ups and pulldowns, 3–4 sets of 6–12 reps.' },
  legs: { label: 'Leg day', detail: 'Legs and core: squats, deadlifts and lunges, 3–4 sets of 6–12 reps.' },
};
// Energy of an hour in the gym above resting, in kcal per kg of body weight (about 5 MET, legs 6:
// the biggest muscles cost the most), and the extra carbohydrate it asks, in g per kg.
const GYM_KCAL_PER_KG = { chest: 4, back: 4, legs: 5 };
const GYM_CARBS_PER_KG = { chest: 0.5, back: 0.5, legs: 1 };
const GYM_PROTEIN_PER_KG = 2.0;
const gym = { ref: null, canWrite: false, weekly: {}, days: {}, busy: false, msg: '' };

const weekdayOf = date => (new Date(t(date)).getDay() + 6) % 7;
// The gym session on a date (chest, back or legs), or null: the day's own choice, else the weekly pattern.
function gymOn(date) {
  const v = gym.days[date] ?? gym.weekly[weekdayOf(date)];
  return GYM_KINDS[v] ? v : null;
}

// The gym part of a day in the plan: the session with its reason, and the picker when this view may save.
// `run` is the day's planned run and `next` the next day's (null for rest), for the leg day advice.
function gymCell(date, run, next) {
  const kind = gymOn(date), g = kind && GYM_KINDS[kind];
  const hard = s => s && ['intervals', 'threshold', 'race-pace', 'long', 'race'].includes(s.kind);
  let why = '';
  if (kind === 'legs' && hard(run)) why = `Run the ${run.title.toLowerCase()} first and lift after, or move leg day: tired legs cost the session its quality.`;
  else if (kind === 'legs' && hard(next)) why = `Tomorrow is a ${next.title.toLowerCase()}: keep leg day light or move it, so your legs are fresh for it.`;
  else if (kind) why = 'Strength work makes muscles and tendons more robust and running more economical; eat protein within an hour after.';
  // An open knee injury (swim.js): leg day without deep knee bends, built around the rehab work.
  const knee = kind === 'legs' && kneeOn(date);
  if (knee) why = 'Keep training the legs, but around the knee: hips and quads that are strong take load off the kneecap. Stop any exercise that hurts.';
  const detail = knee ? `Knee-friendly: no deep squats or lunges. Hip thrusts, Romanian deadlifts, leg press in a short range, side planks; then ${KNEE_STRENGTH.charAt(0).toLowerCase()}${KNEE_STRENGTH.slice(1)}` : g?.detail;
  const body = g ? `<div class="gym"><h4>${g.label}</h4><p>${esc(detail)}</p><p class="why"><b>Why:</b> ${esc(why)}</p></div>` : '';
  if (!gym.ref || !gym.canWrite) return body;
  const opts = [['', 'No gym'], ...Object.entries(GYM_KINDS).map(([k, v]) => [k, v.label])]
    .map(([k, l]) => `<option value="${k}"${(kind || '') === k ? ' selected' : ''}>${l}</option>`).join('');
  return `${body}<label class="gymsel">Gym<select data-gym="${date}"${gym.busy ? ' disabled' : ''}>${opts}</select></label>`;
}

// The line above the week: what the picker does, and the button that repeats this week's gym days.
function gymLine(weekDates) {
  if (!gym.ref) return '<p class="cap">Open the page on claude.ai to add your gym days (chest, back, legs); they count in the food targets under Nutrition.</p>';
  const n = weekDates.filter(gymOn).length;
  const repeat = gym.canWrite ? ` <button type="button" class="livebtn" id="gym-repeat"${gym.busy ? ' disabled' : ''}>${n ? 'Repeat these gym days every week' : 'No gym days every week'}</button>` : '';
  return `<p class="cap"><b>Gym:</b> ${gym.canWrite ? 'pick chest, back or legs per day below. ' : ''}Each gym day adds to that day's energy, protein and carbohydrate under Nutrition.${gym.msg ? ` <span class="pill warn">${esc(gym.msg)}</span>` : ''}${repeat}</p>`;
}

// Wire the pickers and the repeat button in the plan; weekDates are the 7 days of the shown week.
function bindGym(root, weekDates) {
  for (const sel of root.querySelectorAll('[data-gym]')) sel.onchange = () => {
    saveGym(gym.weekly, { ...gym.days, [sel.dataset.gym]: sel.value || 'none' });
  };
  const repeat = $('gym-repeat');
  if (repeat) repeat.onclick = () => {
    const weekly = Object.fromEntries(weekDates.map(d => [weekdayOf(d), gymOn(d)]).filter(([, k]) => k));
    // From this week on the pattern holds: drop the days' own choices that would override it.
    saveGym(weekly, Object.fromEntries(Object.entries(gym.days).filter(([d]) => d < weekDates[0])));
  };
}

async function saveGym(weekly, days) {
  if (gym.busy) return;
  const oldest = shiftIso(iso(new Date()), -GYM_KEEP_DAYS);
  days = Object.fromEntries(Object.entries(days).filter(([d]) => d >= oldest));
  gym.busy = true;
  gym.msg = '';
  // Shown at once; the snapshot confirms it.
  const before = { weekly: gym.weekly, days: gym.days };
  Object.assign(gym, { weekly, days });
  rerender();
  try {
    await gym.ref.set({ weekly, days, updated_at: new Date().toISOString() });
  } catch (err) {
    Object.assign(gym, before);
    if (err.code === 'invalid_argument' || err.code === 'permission_denied') gym.canWrite = false;
    gym.msg = err.code === 'quota_exceeded' ? 'The page storage is full.' : 'Saving failed; try again in a moment.';
  } finally {
    gym.busy = false;
    rerender();
  }
}

async function startGym() {
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  if (typeof db?.doc !== 'function') return;
  try { user = await window.claude.use('user'); } catch { user = null; }
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  gym.canWrite = canWrite !== false;
  gym.ref = db.doc(GYM_DOC);
  gym.ref.onSnapshot(snap => {
    const v = snap.exists ? snap.data() : {};
    const valid = o => o && typeof o === 'object' ? o : {};
    if (gym.busy) return; // a save in flight already shows its result
    gym.weekly = valid(v.weekly);
    gym.days = Object.fromEntries(Object.entries(valid(v.days)).filter(([d]) => /^\d{4}-\d{2}-\d{2}$/.test(d)));
    rerender();
  }, () => { gym.ref = null; rerender(); });
  rerender();
}

startGym();
