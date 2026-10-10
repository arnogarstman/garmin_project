// Training plan: week by week up to race day (or 8 weeks without a race), built from the current
// weekly volume, runs per week, longest run and predictions, in phases base, build, peak, taper and
// race week. Every session carries its reason, drawn from what the coach's checks found (sig).
// renderPage() calls renderPlan(); the selected week survives re-renders.
let planWeek = 0;

const PLAN_PEAK_KM = { '5k': 45, '10k': 55, half: 65, marathon: 85 };
const PLAN_LONG_KM = { '5k': 10, '10k': 14, half: 18, marathon: 32 };
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

function buildPlan({ G, R, st, sig }) {
  const dist = R ? G.distance : 'half', race = RACES[dist];
  const mean = a => a.length ? a.reduce((s, v) => s + v, 0) / a.length : null;
  const raceT = G && G.date ? t(G.date) : null;
  const hasRace = raceT !== null && raceT >= sig.x1 && R;
  const raceWeek = hasRace ? sig.weekStart(G.date) : null;
  const n = hasRace ? Math.min(26, Math.round((raceWeek - sig.thisWeek) / (7 * DAY)) + 1) : 8;
  const full = [1, 2, 3].filter(i => sig.thisWeek - i * 7 * DAY >= sig.covered).map(sig.wk);
  const baseKm = Math.max(12, full.length ? mean(full) : 20);
  const peakKm = Math.max(baseKm, Math.min(PLAN_PEAK_KM[dist], Math.max(baseKm * 1.4, baseKm + 10)));
  const runsPerWeek = Math.min(6, Math.max(3, Math.round(sig.runsPerWeek || 3)));
  const longGoal = PLAN_LONG_KM[dist], taperWeeks = dist === 'marathon' ? 2 : 1;

  // Paces in min/km, from the predictions; race pace is the target when one is set.
  const hmP = num(st.predicted_half_marathon_s) ? st.predicted_half_marathon_s / 60 / HM_KM : null;
  if (!hmP) return null;
  const p10 = num(st.predicted_10k_s) ? st.predicted_10k_s / 60 / 10 : hmP - 0.15;
  const p5 = num(st.predicted_5k_s) ? st.predicted_5k_s / 60 / 5 : hmP - 0.35;
  const predS = num(st[race.status]) ? st[race.status] : null;
  const raceS = G && G.targetS && R ? G.targetS : predS;
  const rp = raceS ? raceS / 60 / race.km : hmP;
  const paces = { easy: [hmP + 1.0, hmP + 1.5], long: [hmP + 0.75, hmP + 1.25], threshold: [p10 + 0.05, hmP], interval: p5, race: rp };

  const weeks = [];
  let km = baseKm, longKm = Math.min(Math.max(sig.longest || 8, 6) + 1, longGoal), sinceDown = 0;
  for (let i = 0; i < n; i++) {
    const toRace = n - 1 - i;
    const phase = !hasRace ? (i < 3 ? 'base' : 'build')
      : toRace === 0 ? 'race' : toRace <= taperWeeks ? 'taper' : toRace <= taperWeeks + 2 ? 'peak' : toRace <= taperWeeks + 8 ? 'build' : 'base';
    let weekKm, weekLong, down = false;
    if (phase === 'race') { weekKm = km * 0.45; weekLong = 0; }
    else if (phase === 'taper') { weekKm = km * (toRace === 1 ? 0.65 : 0.8); weekLong = longKm * (toRace === 1 ? 0.6 : 0.75); }
    else {
      down = i > 0 && sinceDown >= 3 && phase !== 'peak';
      if (down) { sinceDown = 0; weekKm = km * 0.75; weekLong = longKm * 0.75; }
      else {
        if (i > 0) { km = Math.min(peakKm, km * 1.07); longKm = Math.min(longGoal, longKm + 1.5); }
        sinceDown++; weekKm = km; weekLong = longKm;
      }
    }
    weekLong = Math.min(weekLong, weekKm * (dist === 'marathon' ? 0.45 : 0.4));
    weeks.push({ i, start: sig.thisWeek + i * 7 * DAY, phase, down, km: weekKm, long: weekLong });
  }
  return { weeks, hasRace, race, dist, paces, runsPerWeek, raceS, predS, longGoal, baseKm };
}

// The sessions of one week: [day index 0 = Monday, session] with km and the workout.
function weekSessions(plan, w, G) {
  const { paces, runsPerWeek, dist } = plan;
  const p = v => pace(v), range = ([a, b]) => `${pace(a)}–${pace(b)}`;
  const out = new Map();
  const set = (day, s) => out.set(day, s);
  if (w.phase === 'race') {
    const rd = (new Date(t(G.date)).getDay() + 6) % 7;
    if (rd >= 3) set(1, { kind: 'race-pace', title: 'Sharpener', km: 7, detail: `2 km easy, 3 × 1 km at ${p(paces.race)} /km with 2 min jog, 2 km easy` });
    if (rd >= 2) set(Math.max(0, rd - 2), { kind: 'easy', title: 'Easy + strides', km: 5, detail: `5 km at ${range(paces.easy)} /km, then 4 × 20 s strides` });
    if (rd >= 1) set(rd - 1, { kind: 'shakeout', title: 'Shakeout', km: 3, detail: `15–20 min very easy, legs loose` });
    set(rd, { kind: 'race', title: G.name, km: plan.race.km, detail: `Race at ${p(paces.race)} /km; first kilometre no faster than that` });
    return out;
  }
  const q = Math.min(12, Math.max(7, w.km * 0.18));
  const quality = [], easyDays = [];
  if (w.phase === 'base' || w.down) quality.push({ kind: 'strides', title: 'Easy + strides', km: Math.min(q, 8), detail: `${Math.round(Math.min(q, 8) - 1)} km at ${range(paces.easy)} /km, then 6 × 20 s strides with full recovery` });
  else if (w.phase === 'build') {
    const reps = dist === '5k' ? `6 × 800 m at ${p(paces.interval)} /km, 2 min jog` : `5 × 1 km at ${p(paces.interval)} /km, 2 min jog`;
    const tempo = ['3 × 8 min', '2 × 12 min', '20 min continuous'][Math.min(2, Math.floor(w.i / 3))];
    quality.push({ kind: 'intervals', title: 'Intervals', km: q, detail: `2 km easy, ${reps}, 2 km easy` });
    if (runsPerWeek >= 4) quality.push({ kind: 'threshold', title: 'Threshold', km: q, detail: `2 km easy, ${tempo} at ${range(paces.threshold)} /km with 2 min jog, 2 km easy` });
  } else if (w.phase === 'peak') {
    const block = dist === '5k' ? `8 × 600 m at ${p(paces.race)} /km` : dist === '10k' ? `4 × 2 km at ${p(paces.race)} /km` : dist === 'half' ? `3 × 3 km at ${p(paces.race)} /km` : `2 × 5 km at ${range(paces.threshold)} /km`;
    quality.push({ kind: 'race-pace', title: 'Race-pace session', km: q, detail: `2 km easy, ${block} with 3 min jog, 2 km easy` });
    if (runsPerWeek >= 4) quality.push({ kind: 'threshold', title: 'Threshold', km: q, detail: `2 km easy, 20–25 min at ${range(paces.threshold)} /km, 2 km easy` });
  } else if (w.phase === 'taper') {
    quality.push({ kind: 'race-pace', title: 'Race-pace reminder', km: Math.min(q, 8), detail: `2 km easy, 4 × 1 km at ${p(paces.race)} /km with 90 s jog, 2 km easy` });
  }
  // Day layout: Tuesday and Thursday for quality, Sunday long, easy days in between, Monday rest.
  const slots = runsPerWeek === 3 ? [1, 3, 6] : runsPerWeek === 4 ? [1, 2, 3, 6] : runsPerWeek === 5 ? [1, 2, 3, 5, 6] : [1, 2, 3, 4, 5, 6];
  const long = { kind: 'long', title: 'Long run', km: w.long, detail: dist === 'marathon' && w.phase === 'peak' ? `${Math.round(w.long)} km, the last ${Math.round(w.long / 3)} at ${p(paces.race)} /km` : `${Math.round(w.long)} km at ${range(paces.long)} /km${w.phase === 'peak' ? ', last 3 km at race pace' : ''}` };
  set(6, long);
  const qDays = [1, 3].filter(d => slots.includes(d));
  quality.forEach((s, k) => qDays[k] !== undefined && set(qDays[k], s));
  for (const d of slots) if (!out.has(d)) easyDays.push(d);
  const used = [...out.values()].reduce((s, x) => s + x.km, 0);
  const each = easyDays.length ? Math.max(4, (w.km - used) / easyDays.length) : 0;
  for (const d of easyDays) set(d, { kind: 'easy', title: 'Easy run', km: each, detail: `${Math.round(each)} km at ${range(paces.easy)} /km, conversational` });
  return out;
}

// Why this session is good for this athlete: the general purpose plus what the data says.
function sessionWhy(s, plan, w, ctx) {
  const { sig, st, G } = ctx, pc = plan.paces, f0 = v => v.toFixed(0);
  const rangeTxt = ([a, b]) => `${pace(a)}–${pace(b)} /km`;
  switch (s.kind) {
    case 'easy': return 'Easy kilometres build the aerobic engine (capillaries, mitochondria, tendons) at little cost. ' +
      (num(sig.easyShare) && sig.easyShare < 75 ? `Only ${f0(sig.easyShare)}% of your last 4 weeks was easy, so hold ${rangeTxt(pc.easy)} even when it feels slow.`
        : num(sig.efficiency) && sig.efficiency > 2 ? `Your efficiency on easy runs is up ${f0(sig.efficiency)}%; this is the work that keeps it climbing.`
          : 'Keep it truly conversational so the hard days can be hard.');
    case 'strides': return 'Short relaxed bursts keep your stride quick and economical without adding fatigue, a gentle start before harder sessions.';
    case 'intervals': return `Repeats at ${pace(pc.interval)} /km raise your VO2 max${num(st.vo2max) ? ` (now ${st.vo2max.toFixed(1)})` : ''}, so race pace uses a smaller share of your ceiling and feels easier.`;
    case 'threshold': return `Threshold running (${rangeTxt(pc.threshold)}) lifts the pace you can hold for about an hour, the strongest single lever on a ${plan.race.label.toLowerCase()} time.` +
      (plan.raceS && plan.predS && plan.raceS < plan.predS ? ` It is how you close the ${hms(plan.predS - plan.raceS)} between your prediction and target.` : '');
    case 'race-pace': return `Rehearses ${pace(pc.race)} /km${G && G.targetS ? ', your target pace,' : ''} so on race day it feels familiar and you can hold it calmly instead of guessing.`;
    case 'long': return (num(sig.longest) && sig.longest >= plan.longGoal
      ? `Keeps the endurance you have: you already reach ${sig.longest.toFixed(1)} km, so the plan holds long runs around ${plan.longGoal} km where they build fitness without long recovery. `
      : `Builds the endurance to finish strong: your longest recent run is ${num(sig.longest) ? sig.longest.toFixed(1) : '–'} km and this plan takes it to about ${plan.longGoal} km. `) +
      (num(sig.drift) && sig.drift > 3 ? `Your heart rate drifts ${f0(sig.drift)}% on long runs: start slower and take fluid and carbohydrate every 30 to 40 minutes.` : 'Run it easy; the time on your feet is the point, not the pace.');
    case 'shakeout': return 'Loosens the legs and settles nerves before the race without costing any freshness.';
    case 'race': return `Everything leads here. Start at ${pace(pc.race)} /km and let the second half be your fastest.`;
    default: return '';
  }
}

// The k-th rest day of the week gets its own reason, so the week does not repeat itself.
function restWhy(k, ctx) {
  const { sig } = ctx;
  if (k === 0) {
    if (sig.recovery === 'crit' || sig.recovery === 'warn') return `Recovery is where fitness is made. Your HRV is ${sig.hrvToday} against a normal ${Math.round(sig.hrvNormal)}, so take the rest seriously.`;
    if (num(sig.sleepGain) && sig.sleepGain >= 5) return `Recovery is where fitness is made. A good night lifts your readiness by about ${sig.sleepGain.toFixed(0)} points: use it for sleep.`;
    return 'Recovery is where fitness is made; a rest day lets the training of the past days turn into adaptation.';
  }
  if (k === 1) return 'Space between hard days means you can hit the paces of the next session instead of running it tired.';
  return 'Low-impact movement like cycling or mobility keeps you loose and gives tendons and bones a break from pounding.';
}

const PHASE_NOTE = {
  base: 'Base: mostly easy running and strides to build volume and durability before harder work.',
  build: 'Build: two quality sessions a week raise VO2 max and threshold while volume grows about 7% a week.',
  peak: 'Peak: sessions get race-specific so the body learns exactly what race day asks.',
  taper: 'Taper: volume drops while some intensity stays, so you arrive fresh with full fitness.',
  race: 'Race week: little volume, short sharpeners, and lots of rest.',
};

function renderPlan(ctx) {
  const plan = buildPlan(ctx);
  if (!plan) { $('plan').innerHTML = '<p class="cap">Needs a half marathon prediction from the watch to set training paces.</p>'; return; }
  const { weeks } = plan, { G, sig } = ctx;
  planWeek = Math.min(planWeek, weeks.length - 1);
  const maxKm = Math.max(...weeks.map(w => w.km));
  const head = plan.hasRace
    ? `${weeks.length} week${weeks.length === 1 ? '' : 's'} to ${esc(G.name)} on ${fmtDate(G.date)}, from about ${Math.round(plan.baseKm)} km a week now.`
    : `No race set: an 8-week build toward a ${plan.race.label.toLowerCase()}, from about ${Math.round(plan.baseKm)} km a week now. Set your race above to plan to race day.`;
  const strip = weeks.map(w => `<button type="button" class="pw${w.i === planWeek ? ' on' : ''}" data-w="${w.i}" aria-pressed="${w.i === planWeek}">` +
    `<span class="bar"><i style="height:${Math.max(8, w.km / maxKm * 100).toFixed(0)}%"></i></span><b>W${w.i + 1}</b><span>${fmtDate(iso(new Date(w.start)))}</span><span>${w.phase === 'race' ? 'race' : w.down ? 'lighter' : w.phase}</span><span>${Math.round(w.km)} km</span></button>`).join('');

  const w = weeks[planWeek], sessions = weekSessions(plan, w, G), today = iso(new Date(sig.x1));
  let rows = '', rests = 0;
  for (let d = 0; d < 7; d++) {
    const date = iso(new Date(w.start + d * DAY)), past = date < today, s = sessions.get(d);
    const done = sig.runs.filter(r => r.activity_date.slice(0, 10) === date);
    const when = `<div class="pd"><b>${DOW[d]}</b><span>${fmtDate(date)}</span>${date === today ? '<span class="pill good">today</span>' : ''}</div>`;
    if (past) {
      // The plan starts now: past days show what was actually run.
      rows += `<div class="prow past">${when}<div><h4>${done.length ? 'Done' : 'No run'}</h4><p>${done.map(r => `${esc(r.activity_name)}: ${r.km.toFixed(1)} km${num(r.pace) ? ` at ${pace(r.pace)} /km` : ''}`).join('; ')}</p></div><div></div></div>`;
      continue;
    }
    let sess = s;
    // Under-recovered today: today's hard session becomes an easy run.
    if (s && date === today && sig.recovery === 'crit' && !['easy', 'long', 'race', 'shakeout'].includes(s.kind)) sess = { ...s, kind: 'easy', title: 'Easy run (swapped)', detail: `Recovery is low today: ${Math.round(s.km)} km easy instead of ${s.title.toLowerCase()}; do the session later in the week if you feel fresh` };
    rows += sess
      ? `<div class="prow ${sess.kind}">${when}<div><h4>${esc(sess.title)} <span class="km">${sess.kind === 'race' ? plan.race.label : `${Math.round(sess.km)} km`}</span></h4><p>${esc(sess.detail)}</p></div><p class="why"><b>Why:</b> ${esc(sessionWhy(sess, plan, w, ctx))}</p></div>`
      : `<div class="prow rest">${when}<div><h4>Rest</h4><p>Off, or 20–30 min of easy cycling or mobility.</p></div><p class="why"><b>Why:</b> ${esc(restWhy(rests++, ctx))}</p></div>`;
  }
  const total = [...sessions.values()].reduce((s, x) => s + (x.kind === 'race' ? 0 : x.km), 0);
  $('plan').innerHTML = `<p>${head}</p><div class="pstrip" role="group" aria-label="Weeks">${strip}</div>` +
    `<div class="pweek"><div class="phead"><h3>Week ${w.i + 1} · ${w.phase === 'race' ? 'Race week' : w.down ? 'Lighter week' : w.phase[0].toUpperCase() + w.phase.slice(1)}</h3><span class="tot">${Math.round(total)} km${w.long ? ` · long run ${Math.round(w.long)} km` : ''}</span></div>` +
    `<p class="note">${w.down ? 'A lighter week: every fourth week drops about 25% so the three before it can sink in. ' : ''}${PHASE_NOTE[w.phase]}</p>${rows}</div>`;
  for (const b of $('plan').querySelectorAll('.pw')) b.onclick = () => { planWeek = +b.dataset.w; renderPlan(ctx); };
}
