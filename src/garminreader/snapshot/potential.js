// Your potential: Claude reads the fitness and training data behind the race goal and says what is
// within reach by race day: a target time that is ambitious but realistic, the training level
// that fits, why, the risks, and what to focus on. Asked on a click (the `sample` capability), kept
// in the artifact's database (settings/potential) with the inputs it answered, and applied to the
// race goal (target and level, settings/race) with one click.
const POTENTIAL_DOC = 'settings/potential';
const pot = { sample: null, ref: null, raceRef: null, canWrite: false, saved: null, busy: null, error: '', input: null, ctl: null };

// The question: the race and the numbers a coach would read. Null without a race to aim at.
function potentialInput(D, ctx) {
  const G = ctx?.G, R = G && RACES[G.distance];
  if (!R || !G.date) return null;
  const { st, sig } = ctx, days = D.daily || [], pred = (D.pred || []).filter(r => num(r[R.pred]));
  const vo2 = days.filter(r => num(r.vo2max)), weeks = (D.weekly || []).slice(-9, -1);
  const predNow = num(st[R.status]) ? st[R.status] : pred.length ? pred[pred.length - 1][R.pred] : null;
  const pred8 = pred.find(r => t(r.d) >= sig.x1 - 56 * DAY);
  const fmt = (v, d = 0) => num(v) ? v.toFixed(d) : 'unknown';
  const facts = {
    race: `${R.label} on ${G.date} (${Math.round((t(G.date) - sig.x1) / (7 * DAY))} weeks from now)`,
    currentTarget: G.target || 'none',
    currentLevel: planLevel(G).label,
    garminPredictionNow: predNow ? hms(predNow) : 'unknown',
    garminPrediction8WeeksAgo: pred8 ? hms(pred8[R.pred]) : 'unknown',
    vo2max: vo2.length ? `${vo2[vo2.length - 1].vo2max} now, ${vo2[0].vo2max} at the start of the year of data` : 'unknown',
    runningKmPerWeekLast8Weeks: weeks.map(w => w.run_km).join(', ') || 'unknown',
    runsPerWeek: fmt(sig.runsPerWeek, 1),
    longestRunLast4WeeksKm: fmt(sig.longest, 1),
    easyShare: num(sig.easyShare) ? `${sig.easyShare.toFixed(0)}% of running time in heart rate zones 1-2 over 4 weeks (about 80% is the endurance norm)` : 'unknown',
    aerobicEfficiencyTrend: num(sig.efficiency) ? `${sig.efficiency >= 0 ? '+' : ''}${sig.efficiency.toFixed(0)}% metres per heartbeat on easy runs over the period` : 'unknown',
    heartRateDriftOnLongRuns: num(sig.drift) ? `${sig.drift.toFixed(0)}% more beats per km than easy runs` : 'unknown',
    recoveryToday: sig.recovery || 'unknown',
    races: (D.races || []).map(r => `${r.race_distance} ${hms(r.finish_time_s)} on ${String(r.race_date).slice(0, 10)}`).join('; ') || 'none in the data',
  };
  // The assessment depends on the data, not on the target and level it may already have set.
  const { currentTarget, currentLevel, ...data } = facts;
  return { facts, key: JSON.stringify(data), distance: G.distance };
}

function potentialPrompt(input) {
  const facts = Object.entries(input.facts).map(([k, v]) => `- ${k}: ${v}`).join('\n');
  return `You are an experienced running coach. The athlete thinks their training is too easy and that they can do better. Read their data and say honestly what they can reach by race day.

The data:
${facts}

Training levels the plan offers:
- Steady: volume up about 5% a week, one quality session a week.
- Balanced: volume up about 7% a week, two quality sessions a week with four or more runs.
- Ambitious: volume up about 10% a week and one run more, threshold work from the first week, intervals and threshold every build week, long runs finishing at race pace.

Set a target time that is ambitious but realistic for the race date: what this athlete can run with good training from where they are now. Use Garmin's prediction, its trend, VO2 max, volume and long runs; say where the untapped potential is and what limits it today (for example too much moderate running, too little volume, short long runs). Choose the level that gets them there without likely injury. Cite the numbers. Plain words, no jargon.

Reply with only JSON in this shape:
{"target":"h:mm:ss","level":"ambitious","headline":"The verdict in at most twelve words.","potential":"Two or three sentences: what is realistic by race day and where the potential is.","reasons":["Up to three short reasons with numbers."],"risks":["Up to two risks to watch."],"focus":["Up to three things to focus on in training."]}`;
}

function renderPotential(D, ctx) {
  const el = $('potential');
  if (!el) return;
  pot.input = potentialInput(D, ctx);
  const saved = pot.saved, r = saved?.result, current = saved && pot.input && saved.key === pot.input.key;
  const can = pot.sample && pot.canWrite && pot.input;
  if (pot.busy) {
    el.innerHTML = `<p class="livestate" role="status">${esc(pot.busy)}</p><button type="button" class="livebtn" id="pot-stop">Stop</button>`;
  } else if (!r) {
    el.innerHTML = `<div class="potintro"><h3>Is there more in you?</h3><p class="cap">${!pot.input ? 'Set your race and its date to have Claude assess your potential.' : pot.sample ? 'Claude reads your fitness and training data and says what you can reach by race day, and at which training level.' : 'Open the page on claude.ai to have Claude assess your potential.'}</p>` +
      `${can ? '<button type="button" class="livebtn" id="pot-make">Ask Claude about my potential</button>' : ''}${pot.error ? `<p class="mmsg">${esc(pot.error)}</p>` : ''}</div>`;
  } else {
    const G = ctx?.G, R = G && RACES[G.distance], lv = LEVELS[r.level];
    const targetS = R ? parseTarget(r.target, G.distance) : null, predS = R && num(ctx.st[R.status]) ? ctx.st[R.status] : null;
    const vsPred = targetS && predS ? `${hms(Math.abs(predS - targetS))} ${targetS < predS ? 'faster' : 'slower'} than Garmin's prediction of ${hms(predS)}` : '';
    const list = (title, items) => Array.isArray(items) && items.length ? `<div><h4>${title}</h4><ul>${items.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : '';
    const applied = G && G.target === r.target && (G.level || 'balanced') === r.level;
    el.innerHTML = `<div class="card good potcard${current ? '' : ' stale'}"><div class="head"><span class="eyebrow">Your potential · Claude, ${fmtDate(saved.generated_at)}</span>${current ? '' : '<span class="pill warn">out of date</span>'}</div>` +
      `<h3>${esc(r.headline)}</h3><div class="tiles"><div class="tile"><span class="eyebrow">Target</span><span class="v">${esc(r.target)}</span><span class="s">${vsPred}</span></div>` +
      `<div class="tile"><span class="eyebrow">Level</span><span class="v">${esc(lv?.label || r.level)}</span><span class="s">${esc(lv?.note || '')}</span></div></div>` +
      `<p class="why">${esc(r.potential)}</p><div class="wlist">${list('Why', r.reasons)}${list('Watch', r.risks)}${list('Focus', r.focus)}</div>` +
      `<div class="btns">${can && targetS && lv && !applied ? '<button type="button" class="livebtn primary" id="pot-apply">Use this target and level</button>' : applied ? '<span class="pill good">in your race goal</span>' : ''}${can ? '<button type="button" class="livebtn" id="pot-make">Ask Claude again</button>' : ''}</div>` +
      `${pot.error ? `<p class="mmsg">${esc(pot.error)}</p>` : ''}</div>`;
  }
  const make = $('pot-make'), stop = $('pot-stop'), apply = $('pot-apply');
  if (make) make.onclick = makePotential;
  if (stop) stop.onclick = () => pot.ctl?.abort();
  if (apply) apply.onclick = applyPotential;
}

// Ask Claude for a new read; true once there is one to use.
async function makePotential() {
  const input = pot.input;
  if (!input || !pot.sample || pot.busy) return false;
  let ok = false;
  pot.ctl = new AbortController();
  pot.error = '';
  pot.busy = 'Claude is reading your data. This usually takes under a minute.';
  rerender();
  try {
    const result = await pot.sample.json(potentialPrompt(input), { signal: pot.ctl.signal, cache: false });
    if (typeof result?.target !== 'string' || !parseTarget(result.target, input.distance) || !LEVELS[result.level]) throw { code: 'invalid_json' };
    const doc = { generated_at: new Date().toISOString(), key: input.key, result };
    pot.saved = doc;
    ok = true;
    try { await pot.ref.set(doc); } catch { pot.error = 'The assessment could not be saved; it is shown until you leave the page.'; }
  } catch (e) {
    pot.error = {
      cancelled: '',
      not_granted: 'Claude is not allowed for this page; allow it from the page\'s Permissions menu.',
      rate_limited: 'Claude is busy or your usage limit is reached; try again later.',
      invalid_json: 'Claude\'s answer was not usable; try again.',
      refused: 'Claude declined to answer; try again later.',
    }[e.code] ?? 'Asking Claude failed; try again in a moment.';
    if (['not_granted', 'sampling_disabled', 'not_declared', 'capability_disabled', 'capability_removed'].includes(e.code)) pot.sample = null;
  } finally {
    pot.busy = null;
    rerender();
  }
  return ok;
}

// Put the target and level in the race goal; the plan and projection follow on the next render.
async function applyPotential() {
  const r = pot.saved?.result;
  if (!r || !pageGoal || !pot.raceRef) return;
  if (pageGoal.target === r.target && (pageGoal.level || 'balanced') === r.level) return;
  try {
    await pot.raceRef.set({ ...pageGoal, target: r.target, level: r.level, updated_at: new Date().toISOString() });
  } catch {
    pot.error = 'The race goal could not be updated; try again in a moment.';
    rerender();
  }
}

// The training plan's line on Claude's read: whether the plan follows it, and one button that
// recalculates the plan from it. With no read, or one the data has moved past, the button asks
// Claude first; then it puts the target and level in the race goal, which rebuilds the plan.
function potentialPlanLine(ctx) {
  const input = lastD && potentialInput(lastD, ctx);
  if (!input) return '';
  const saved = pot.saved, r = saved?.result, G = ctx.G;
  const current = !!r && saved.key === input.key, applied = !!r && G.target === r.target && (G.level || 'balanced') === r.level;
  const lv = r && (LEVELS[r.level]?.label || r.level).toLowerCase(), when = r && fmtDate(saved.generated_at);
  const state = !r ? 'Claude has not assessed your potential yet.'
    : applied ? `The plan follows Claude's read of ${when}: ${esc(r.target)} at the ${esc(lv)} level${current ? '.' : ', from before your latest data.'}`
      : `Claude's read of ${when} suggests ${esc(r.target)} at the ${esc(lv)} level${current ? '' : ' (out of date)'}; the plan does not use it yet.`;
  const can = pot.sample && pot.canWrite;
  const [mode, label] = !r || !current ? ['fresh', 'Recalculate with Claude\'s potential'] : !applied ? ['apply', 'Recalculate with Claude\'s target and level'] : ['fresh', 'Ask Claude again and recalculate'];
  const action = pot.busy ? `<span class="cap" role="status">${esc(pot.busy)}</span>`
    : can ? `<button type="button" class="livebtn${applied && current ? '' : ' primary'}" id="plan-recalc" data-mode="${mode}">${label}</button>` : '';
  return `<div class="planpot"><p class="cap">${state}</p>${action}${pot.error && !pot.busy ? `<p class="mmsg">${esc(pot.error)}</p>` : ''}</div>`;
}

async function recalcFromPotential(e) {
  const mode = e?.currentTarget?.dataset.mode;
  if (pot.busy) return;
  if (mode === 'fresh' && !(await makePotential())) return;
  await applyPotential();
}

async function startPotential() {
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  try { pot.sample = window.claude ? await window.claude.use('sample') : null; } catch { pot.sample = null; }
  if (typeof db?.doc !== 'function') { pot.sample = null; return; }
  try { user = await window.claude.use('user'); } catch { user = null; }
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  pot.canWrite = canWrite !== false;
  pot.ref = db.doc(POTENTIAL_DOC);
  pot.raceRef = db.doc(GOAL_DOC);
  pot.ref.onSnapshot(snap => {
    if (pot.busy) return;
    pot.saved = snap.exists ? snap.data() : null;
    rerender();
  }, () => { pot.error = 'The saved assessment could not be loaded on this view.'; rerender(); });
}

startPotential();
