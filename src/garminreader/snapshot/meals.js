// Meal plan: day by day toward a weight goal. The page works out each day's energy and macro targets
// itself, from Garmin's measured daily burn (marts.fct_daily_energy), the weight trend, today's
// workouts and the training plan's sessions for the coming week; Claude (the `sample` capability)
// only turns those targets into meals. The goal (settings/weight) and the last plan
// (settings/mealplan) live in the artifact's database like the race goal, so a plan is made on
// request and kept, never regenerated on a visit. Estimates for a healthy adult, not medical advice.
const WEIGHT_DOC = 'settings/weight', MEALPLAN_DOC = 'settings/mealplan';
const PLAN_DAYS = 7;
const KCAL_PER_KG = 7700; // energy in a kilogram of body weight, roughly
const RUN_KCAL_PER_KG_KM = 1.0; // running costs about 1 kcal per kg of body weight per km
// Limits the plan never crosses, whatever the goal asks: weekly change as a share of body weight,
// a floor on intake, and the largest share of a day's burn left uneaten.
const MAX_LOSS_PCT = 0.75, MAX_GAIN_PCT = 0.25, MIN_KCAL = 1500, MAX_DEFICIT_SHARE = 0.25;
// Carbohydrate per kg of body weight, from endurance sports nutrition guidance (about 3 g on a rest
// day up to 7 g for two hours or more): by distance, half a gram more for hard sessions.
const HARD = new Set(['intervals', 'threshold', 'race-pace', 'race']);
const carbsPerKg = (kind, km) => (km <= 0 ? 3 : km < 8 ? 4 : km < 15 ? 5 : km < 25 ? 6 : 7) + (HARD.has(kind) ? 0.5 : 0);
// Fat between these, per kg of body weight; carbohydrate takes the rest of the day's energy.
const FAT_G_PER_KG = [0.7, 1.3];

let weightGoal = null, mealPlan = null;
// What the page may do: ask Claude (sample), save (db + write access). Set by startMeals().
const meals = { sample: null, ref: null, canWrite: false, busy: null, budget: null, error: '' };

const avg = a => a.length ? a.reduce((s, v) => s + v, 0) / a.length : null;
const round10 = v => Math.round(v / 10) * 10;
const kcalFmt = v => Math.round(v).toLocaleString('en-GB');
const dayName = d => DOW[(new Date(t(d)).getDay() + 6) % 7];

// The targets for the next PLAN_DAYS days, or null without enough data (a week of burn, three weigh-ins).
function mealBudget(D, goal) {
  const today = iso(new Date()), rows = D.energy || [];
  const complete = rows.filter(r => r.d.slice(0, 10) < today && num(r.kcal) && r.kcal > 0);
  const weights = rows.filter(r => num(r.weight)).map(r => [t(r.d), r.weight]);
  if (complete.length < 7 || weights.length < 3) return null;

  const lastT = weights[weights.length - 1][0];
  const weight = avg(weights.filter(([x]) => x > lastT - 7 * DAY).map(p => p[1]));
  // Weight trend: least-squares slope over the last 4 weeks of weigh-ins, in kg per week.
  const w28 = weights.filter(([x]) => x > lastT - 28 * DAY);
  let trend = null;
  if (w28.length >= 4) {
    const mx = avg(w28.map(p => p[0])), my = avg(w28.map(p => p[1]));
    const sxx = w28.reduce((s, [x]) => s + (x - mx) ** 2, 0);
    if (sxx > 0) trend = w28.reduce((s, [x, y]) => s + (x - mx) * (y - my), 0) / sxx * 7 * DAY;
  }
  // Burn on a day without training: Garmin's total on rest days of the last 4 weeks, or every day
  // minus its workouts when there are too few rest days.
  const recent = complete.filter(r => t(r.d) > t(today) - 28 * DAY);
  const rest = recent.filter(r => !r.workouts);
  const restBurn = rest.length >= 3 ? avg(rest.map(r => r.kcal)) : avg(recent.map(r => r.kcal - (r.workout_kcal || 0)));

  let rate = 0, capped = false, weeks = null, diff = null;
  if (goal && num(goal.target_kg)) {
    diff = goal.target_kg - weight;
    weeks = goal.target_date ? Math.max(1, (t(goal.target_date) - t(today)) / (7 * DAY)) : null;
    const maxLoss = weight * MAX_LOSS_PCT / 100, maxGain = weight * MAX_GAIN_PCT / 100;
    // Without a date, a steady pace: two thirds of the limit.
    rate = Math.abs(diff) < 0.3 ? 0 : weeks ? diff / weeks : (diff < 0 ? -maxLoss : maxGain) * 2 / 3;
    if (rate < -maxLoss) { rate = -maxLoss; capped = true; }
    if (rate > maxGain) { rate = maxGain; capped = true; }
  }
  const delta = rate * KCAL_PER_KG / 7;
  const protein = weight * (rate < 0 ? 1.8 : 1.6), [fatMin, fatMax] = FAT_G_PER_KG.map(f => f * weight);
  const todayRow = rows.find(r => r.d.slice(0, 10) === today);

  let sessions = upcomingSessions(PLAN_DAYS);
  if (!sessions.length) sessions = Array.from({ length: PLAN_DAYS }, (_, k) => { const n = new Date(); return { date: iso(new Date(n.getFullYear(), n.getMonth(), n.getDate() + k)), kind: 'rest', title: 'No plan', km: 0 }; });
  let floored = false;
  const days = sessions.map(s => {
    // Today, once trained, counts what was done instead of what was planned.
    const done = s.date === today && todayRow?.workouts > 0;
    const extra = done ? (todayRow.workout_kcal || 0) : s.km * weight * RUN_KCAL_PER_KG_KM;
    const burn = restBurn + extra;
    let kcal = burn + delta;
    const floor = Math.max(MIN_KCAL, burn * (1 - MAX_DEFICIT_SHARE));
    if (kcal < floor) { kcal = floor; floored = true; }
    let carbs = weight * (done ? carbsPerKg('easy', todayRow.run_km || 8) : carbsPerKg(s.kind, s.km));
    const fat = Math.min(fatMax, Math.max(fatMin, (kcal - protein * 4 - carbs * 4) / 9));
    carbs = Math.max(weight * 2, (kcal - protein * 4 - fat * 9) / 4);
    const title = done ? `Done: ${todayRow.workouts} workout${todayRow.workouts > 1 ? 's' : ''}` : s.title + (s.km && s.kind !== 'race' ? ` ${Math.round(s.km)} km` : '');
    return { date: s.date, kind: done ? 'done' : s.kind, title, burn: round10(burn), kcal: round10(protein * 4 + carbs * 4 + fat * 9), protein: Math.round(protein), carbs: Math.round(carbs), fat: Math.round(fat) };
  });
  return { weight, trend, restBurn, rate, capped, floored, weeks, diff, days, eta: diff && rate ? Math.abs(diff / rate) : null };
}

function renderMeals(D) {
  const b = meals.budget = mealBudget(D, weightGoal), g = weightGoal;
  const sign = v => `${v > 0 ? '+' : v < 0 ? '−' : '±'}${Math.abs(v).toFixed(2)}`;
  if (!b) {
    $('mealstats').innerHTML = '<p class="cap">Needs a week of Garmin calorie data and three weigh-ins from the last six weeks.</p>';
    $('mealbudget').textContent = '';
    $('mealplan').innerHTML = mealPlanHtml();
    bindMealButtons();
    return;
  }
  const tile = (k, v, s) => `<div class="tile"><span class="eyebrow">${k}</span><span class="v">${v}</span><span class="s">${s}</span></div>`;
  $('mealstats').innerHTML = `<div class="tiles">${[
    tile('Weight', `${b.weight.toFixed(1)}<small>kg</small>`, 'average of the last 7 days of weigh-ins'),
    tile('Trend', num(b.trend) ? `${sign(b.trend)}<small>kg/wk</small>` : '–', 'over the last 4 weeks'),
    tile('Goal', g ? `${g.target_kg.toFixed(1)}<small>kg</small>` : '–', g ? (g.target_date ? `by ${fmtDate(g.target_date)} ${new Date(t(g.target_date)).getFullYear()}` : 'no date: steady pace') : 'set it on the right'),
    tile('Planned pace', g ? `${sign(b.rate)}<small>kg/wk</small>` : '–', !g ? 'maintenance until a goal is set' : b.capped ? `<span class="pill warn">capped</span> goal needs ${sign(b.diff / b.weeks)}` : b.eta ? `goal in about ${Math.ceil(b.eta)} weeks` : 'at goal: maintain'),
    tile('Rest-day burn', `${kcalFmt(b.restBurn)}<small>kcal</small>`, 'Garmin, last 4 weeks'),
  ].join('')}</div>`;

  const notes = [];
  if (b.capped) notes.push(`The goal asks for more than ${b.rate < 0 ? `${MAX_LOSS_PCT}% of body weight lost` : `${MAX_GAIN_PCT}% gained`} a week, so the plan holds that pace instead${b.eta ? ` and reaches the goal in about ${Math.ceil(b.eta)} weeks` : ''}.`);
  if (b.floored) notes.push(`Some days stop at ${kcalFmt(MIN_KCAL)} kcal or ${MAX_DEFICIT_SHARE * 100}% below that day's burn, whichever is higher, so training stays fuelled.`);
  $('mealbudget').innerHTML = `<div class="tbl"><table><thead><tr><th>Day</th><th>Training</th><th class="n">Burn</th><th class="n">Eat</th><th class="n">Protein</th><th class="n">Carbs</th><th class="n">Fat</th></tr></thead><tbody>${
    b.days.map(d => `<tr><td>${dayName(d.date)} ${fmtDate(d.date)}</td><td>${esc(d.title)}</td><td class="n">${kcalFmt(d.burn)}</td><td class="n"><b>${kcalFmt(d.kcal)}</b></td><td class="n">${d.protein} g</td><td class="n">${d.carbs} g</td><td class="n">${d.fat} g</td></tr>`).join('')
  }</tbody></table></div><p class="cap">Burn is your rest-day burn plus about ${RUN_KCAL_PER_KG_KM} kcal per kg per km for planned runs (today: what you did, once you trained). ${notes.join(' ')} Estimates for a healthy adult, not medical advice.</p>`;
  $('mealplan').innerHTML = mealPlanHtml();
  bindMealButtons();
}

// The saved plan from today on, with the button that makes a new one when this view may.
function mealPlanHtml() {
  const today = iso(new Date()), b = meals.budget;
  const can = meals.sample && meals.canWrite && b;
  if (meals.busy) return `<p class="livestate" role="status">${esc(meals.busy)}</p><button type="button" class="livebtn" id="meal-stop">Stop</button>`;
  const p = mealPlan, days = (p?.plan?.days || []).filter(d => typeof d?.date === 'string' && d.date >= today);
  const stale = p && (!days.length || (weightGoal?.updated_at && weightGoal.updated_at > p.generated_at));
  const err = meals.error ? `<p class="mmsg">${esc(meals.error)}</p>` : '';
  const button = can ? `<button type="button" class="livebtn" id="meal-make">${p ? 'Make a new plan' : 'Make the meal plan'}</button>` : '';
  if (!p) return `${err}<p class="cap">${can ? 'Claude writes meals for the targets above, around your training and diet. It takes about a minute.' : meals.sample === null ? 'Open the page on claude.ai to have Claude write the meals.' : 'No meal plan yet.'}</p>${button}`;

  const target = new Map((p.basis || []).map(d => [d.date, d]));
  const cards = days.map(d => {
    const list = Array.isArray(d.meals) ? d.meals : [], tg = target.get(d.date);
    const total = list.reduce((s, m) => s + (num(m.kcal) ? m.kcal : 0), 0);
    return `<div class="mday"><div class="head"><h3>${dayName(d.date)} ${fmtDate(d.date)}</h3><span class="eyebrow">${tg ? esc(tg.title) : ''}</span></div>` +
      `<p class="tot">${kcalFmt(total)} kcal${tg ? ` of ${kcalFmt(tg.kcal)} · protein ${list.reduce((s, m) => s + (num(m.protein_g) ? m.protein_g : 0), 0)} of ${tg.protein} g` : ''}</p><ul>${
        list.map(m => `<li><span class="eyebrow">${esc(m.meal)}${num(m.kcal) ? ` · ${Math.round(m.kcal)} kcal` : ''}</span><b>${esc(m.dish)}</b><span>${esc(m.portion)}</span></li>`).join('')
      }</ul>${d.note ? `<p>${esc(d.note)}</p>` : ''}</div>`;
  }).join('');
  const shop = Array.isArray(p.plan.shopping_list) && p.plan.shopping_list.length ? `<details class="mshop"><summary>Shopping list</summary><ul>${p.plan.shopping_list.map(x => `<li>${esc(x)}</li>`).join('')}</ul></details>` : '';
  const tips = Array.isArray(p.plan.tips) && p.plan.tips.length ? `<div class="notes"><h3>Tips</h3><ul>${p.plan.tips.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : '';
  const head = `<p class="cap">Made ${fmtDate(p.generated_at)} at ${new Date(p.generated_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}${stale ? `. <span class="pill warn">out of date</span> ${days.length ? 'the goal changed since' : 'its days are over'}; make a new plan for the targets above.` : '.'}</p>`;
  return `${err}${head}${button}${days.length ? `<div class="mdays">${cards}</div>` : ''}${shop}${tips}`;
}

function bindMealButtons() {
  const make = $('meal-make'), stop = $('meal-stop');
  if (make) make.onclick = makeMealPlan;
  if (stop) stop.onclick = () => meals.ctl?.abort();
}

function mealPrompt(b, g) {
  const days = b.days.map(d => `- ${d.date} ${dayName(d.date)}: ${d.title} · ${d.kcal} kcal · protein ${d.protein} g · carbohydrate ${d.carbs} g · fat ${d.fat} g`).join('\n');
  const goal = g ? `goal ${g.target_kg} kg${g.target_date ? ` by ${g.target_date}` : ''}, planned pace ${b.rate.toFixed(2)} kg per week` : 'no weight goal (maintenance)';
  return `You are a sports dietitian writing a ${b.days.length}-day meal plan for an endurance athlete.

Each day's targets below are already worked out from the athlete's Garmin data: their measured daily burn, the training planned for that day and their weight goal. Do not recompute them. Build meals that reach each day's calories within 5% and at least its protein, with carbohydrate and fat close to their targets.

Athlete: ${b.weight.toFixed(1)} kg${num(b.trend) ? `, trend ${b.trend.toFixed(2)} kg per week over 4 weeks` : ''}, ${goal}.
Main meals per day: ${g?.meals_per_day || 3}, plus snacks where needed to reach the targets.
Diet and preferences (the athlete's own words): ${g?.diet ? JSON.stringify(g.diet) : 'none given'}.

Days:
${days}

Guidance:
- Time carbohydrate around training: a carbohydrate-rich meal two to three hours before long or hard sessions, and protein with carbohydrate within an hour after.
- Simple dishes from ingredients in an ordinary supermarket. Repeat breakfasts and reuse leftovers so shopping stays short.
- Portions in grams or household measures.
- No medical advice and no supplements beyond ordinary food.

Reply with only JSON in this shape:
{"days":[{"date":"YYYY-MM-DD","meals":[{"meal":"Breakfast","dish":"Oats with Greek yoghurt and banana","portion":"80 g oats, 200 g Greek yoghurt, 1 banana","kcal":610,"protein_g":35,"carbs_g":85,"fat_g":14}],"note":"One sentence on how the food fits the day's training."}],"shopping_list":["1 kg rolled oats"],"tips":["At most three short tips"]}
One entry in "days" for each day above, in order.`;
}

async function makeMealPlan() {
  const b = meals.budget, g = weightGoal;
  if (!b || !meals.sample) return;
  meals.ctl = new AbortController();
  meals.error = '';
  meals.busy = 'Claude is writing your meal plan. This usually takes about a minute.';
  $('mealplan').innerHTML = mealPlanHtml(); bindMealButtons();
  try {
    const plan = await meals.sample.json(mealPrompt(b, g), { signal: meals.ctl.signal, cache: false });
    if (!Array.isArray(plan?.days) || !plan.days.every(d => typeof d?.date === 'string' && Array.isArray(d.meals))) throw { code: 'invalid_json' };
    const doc = { generated_at: new Date().toISOString(), basis: b.days, plan };
    mealPlan = doc; // shown at once; the snapshot confirms it for everyone else
    try { await meals.ref.set(doc); } catch (e) { meals.error = e.code === 'quota_exceeded' ? 'The page storage is full; the plan is shown but not saved.' : 'The plan could not be saved; it is shown until you leave the page.'; }
  } catch (e) {
    meals.error = {
      cancelled: '',
      not_granted: 'Claude is not allowed for this page; allow it from the page\'s Permissions menu to make a plan.',
      rate_limited: 'Claude is busy or your usage limit is reached; try again later.',
      invalid_json: 'Claude\'s answer was not a usable plan; try again.',
      refused: 'Claude declined to write this plan; check the diet notes.',
    }[e.code] ?? 'Making the plan failed; try again in a moment.';
    if (['not_granted', 'sampling_disabled', 'not_declared', 'capability_disabled', 'capability_removed'].includes(e.code)) meals.sample = null;
  } finally {
    meals.busy = null;
    $('mealplan').innerHTML = mealPlanHtml(); bindMealButtons();
  }
}

// The weight goal form, as goal.js does the race: shown to those who may write it.
async function startMeals() {
  const box = $('weightform');
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  try { meals.sample = window.claude ? await window.claude.use('sample') : null; } catch { meals.sample = null; }
  if (typeof db?.doc !== 'function') { meals.sample = null; rerender(); return; }
  try { user = await window.claude.use('user'); } catch { user = null; }
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  meals.canWrite = canWrite !== false;
  const ref = db.doc(WEIGHT_DOC);
  meals.ref = db.doc(MEALPLAN_DOC);
  let editing = false;

  const summary = () => {
    const g = weightGoal, edit = meals.canWrite ? `<div class="btns"><button type="button" id="weight-edit">${g ? 'Change goal' : 'Set your weight goal'}</button></div>` : '';
    box.innerHTML = g
      ? `<span class="eyebrow">Your weight goal</span><h3>${g.target_kg.toFixed(1)} kg${g.target_date ? ` by ${fmtDate(g.target_date)} ${new Date(t(g.target_date)).getFullYear()}` : ''}</h3><p>${g.meals_per_day || 3} meals a day${g.diet ? ` · ${esc(g.diet)}` : ''}</p>${edit}`
      : `<p class="cap">No weight goal set: the targets keep your weight steady.</p>${edit}`;
    const btn = $('weight-edit');
    if (btn) btn.onclick = () => { editing = true; form(); };
  };

  const form = (msg = '') => {
    const g = weightGoal || {};
    box.innerHTML = `<span class="eyebrow">${weightGoal ? 'Change your weight goal' : 'Set your weight goal'}</span><form id="weight-f" novalidate>
      <label>Target weight (kg)<input name="target_kg" type="number" step="0.1" min="35" max="250" required value="${num(g.target_kg) ? g.target_kg : ''}"></label>
      <label>By (optional)<input name="target_date" type="date" value="${esc(g.target_date || '')}"></label>
      <label>Main meals a day<select name="meals_per_day">${[2, 3, 4, 5].map(n => `<option${(g.meals_per_day || 3) === n ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
      <label style="grid-column:1/-1">Diet, allergies, dislikes (optional)<input name="diet" maxlength="200" placeholder="e.g. vegetarian, no nuts, quick lunches" value="${esc(g.diet || '')}"></label>
      <div class="btns"><button type="submit" class="primary">Save</button>${weightGoal ? '<button type="button" id="weight-cancel">Cancel</button><button type="button" id="weight-clear">Remove goal</button>' : ''}</div>
    </form>${msg ? `<p class="msg">${esc(msg)}</p>` : ''}`;
    const f = $('weight-f');
    f.onsubmit = async e => {
      e.preventDefault();
      const v = Object.fromEntries(new FormData(f)), kg = Number(v.target_kg);
      if (!(kg >= 35 && kg <= 250)) { form('Enter a target weight between 35 and 250 kg.'); return; }
      if (v.target_date && v.target_date <= iso(new Date())) { form('Pick a date in the future, or leave it empty.'); return; }
      f.querySelector('button[type=submit]').disabled = true;
      try {
        await ref.set({ target_kg: Math.round(kg * 10) / 10, target_date: v.target_date || null, meals_per_day: Number(v.meals_per_day) || 3, diet: v.diet.trim(), updated_at: new Date().toISOString() });
        editing = false;
        summary();
      } catch (err) {
        if (err.code === 'invalid_argument' || err.code === 'permission_denied') { meals.canWrite = false; editing = false; summary(); return; }
        form(err.code === 'quota_exceeded' ? 'The page storage is full.' : 'Saving failed; try again in a moment.');
      }
    };
    const cancel = $('weight-cancel'), clear = $('weight-clear');
    if (cancel) cancel.onclick = () => { editing = false; summary(); };
    if (clear) clear.onclick = async () => {
      clear.disabled = true;
      try { await ref.delete(); editing = false; summary(); } catch { form('Removing failed; try again in a moment.'); }
    };
  };

  ref.onSnapshot(snap => {
    const g = snap.exists ? snap.data() : null;
    weightGoal = g && num(g.target_kg) ? g : null;
    if (!editing) summary();
    rerender();
  }, () => { box.innerHTML = '<p class="cap">The saved weight goal could not be loaded on this view.</p>'; });
  meals.ref.onSnapshot(snap => {
    if (meals.busy) return; // a plan being made replaces this one anyway
    mealPlan = snap.exists ? snap.data() : null;
    rerender();
  }, () => { meals.error = 'The saved meal plan could not be loaded on this view.'; rerender(); });
}

startMeals();
