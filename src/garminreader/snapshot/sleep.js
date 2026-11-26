// Sleep tab: does a night's sleep show up in the runs and the weight that follow? Each row of D.sleep
// (marts.fct_sleep_effects) is one night, on the day it ends, with the morning's recovery readings,
// that day's runs (aerobic efficiency against the 42 days before) and the morning weigh-in.
// Sleep is read one of three ways (hours, Garmin's score, or the 7-night average hours, for sleep
// debt), chosen above the tab and remembered in this browser. Each outcome compares the best-slept
// third of nights with the worst-slept third (difference with a 95% interval) and gives the
// correlation over all nights, so a verdict always shows how much data stands behind it.
// renderPage() calls renderSleep().
const SLEEP_KEY = 'garminreader.sleepMeasure';
const SLEEP_MEASURES = {
  h: { label: 'Hours', axis: 'Sleep (h)', fmt: v => `${v.toFixed(1)} h`, of: 'sleep' },
  score: { label: 'Score', axis: 'Sleep score', fmt: v => `${Math.round(v)}`, of: 'sleep score' },
  h7: { label: '7-night average', axis: '7-night average (h)', fmt: v => `${v.toFixed(1)} h`, of: '7-night average sleep' },
};
let sleepMeasure = 'h';
try { sleepMeasure = localStorage.getItem(SLEEP_KEY) || 'h'; } catch { sleepMeasure = 'h'; }
if (!SLEEP_MEASURES[sleepMeasure]) sleepMeasure = 'h';

// Statistics, all on plain arrays of numbers.
const sMean = a => a.length ? a.reduce((s, v) => s + v, 0) / a.length : null;
const sVar = a => { const m = sMean(a); return a.length > 1 ? a.reduce((s, v) => s + (v - m) ** 2, 0) / (a.length - 1) : null; };
function pearson(pairs) {
  const n = pairs.length;
  if (n < 5) return null;
  const mx = sMean(pairs.map(p => p[0])), my = sMean(pairs.map(p => p[1]));
  let sxy = 0, sxx = 0, syy = 0;
  for (const [x, y] of pairs) { sxy += (x - mx) * (y - my); sxx += (x - mx) ** 2; syy += (y - my) ** 2; }
  if (!sxx || !syy) return null;
  const r = sxy / Math.sqrt(sxx * syy), slope = sxy / sxx;
  // Two-sided p of t = r√(n−2)/√(1−r²), with a normal approximation of the t distribution.
  const df = n - 2, tt = Math.abs(r) * Math.sqrt(df / Math.max(1e-12, 1 - r * r));
  const z = tt * (1 - 1 / (4 * df)) / Math.sqrt(1 + tt * tt / (2 * df));
  return { r, n, p: 2 * (1 - normCdf(z)), slope, icept: my - slope * mx };
}
function normCdf(z) {
  // Abramowitz and Stegun 7.1.26.
  const x = Math.abs(z) / Math.SQRT2, k = 1 / (1 + 0.3275911 * x);
  const erf = 1 - k * (0.254829592 + k * (-0.284496736 + k * (1.421413741 + k * (-1.453152027 + k * 1.061405429)))) * Math.exp(-x * x);
  return z >= 0 ? (1 + erf) / 2 : (1 - erf) / 2;
}
// Thirds of the nights by sleep, with the cut points, so every outcome uses the same groups.
function sleepThirds(values) {
  const v = values.filter(num).sort((a, b) => a - b);
  if (v.length < 9) return null;
  return [v[Math.floor(v.length / 3)], v[Math.floor(v.length * 2 / 3)]];
}
const thirdOf = (x, cuts) => x < cuts[0] ? 0 : x < cuts[1] ? 1 : 2;
// Mean outcome per third, and the best third minus the worst with a Welch 95% interval.
function byThird(pairs, cuts) {
  const g = [[], [], []];
  for (const [x, y] of pairs) g[thirdOf(x, cuts)].push(y);
  const groups = g.map(a => ({ n: a.length, mean: sMean(a) }));
  let diff = null;
  if (g[0].length >= 3 && g[2].length >= 3) {
    const d = sMean(g[2]) - sMean(g[0]), se = Math.sqrt(sVar(g[2]) / g[2].length + sVar(g[0]) / g[0].length);
    diff = { d, lo: d - 1.96 * se, hi: d + 1.96 * se };
  }
  return { groups, diff };
}
// How firm a link is: clear when the interval of the difference excludes zero and the correlation
// agrees; a hint when one of the two points that way; otherwise none to see.
function strength(c, diff) {
  if (!c || !diff) return { word: 'too little data', cls: 'low' };
  const sep = diff.lo > 0 || diff.hi < 0, sig = c.p < 0.05;
  if (sep && sig) return { word: Math.abs(c.r) >= 0.3 ? 'clear link' : 'small but real link', cls: 'link' };
  if (sep || sig || c.p < 0.15) return { word: 'possible link', cls: '' };
  return { word: 'no clear link', cls: 'low' };
}

const signed = (v, d = 1, unit = '') => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(d)}${unit}`;
const bedFmt = h => { const m = Math.round(h * 60) % (24 * 60); return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`; };

// A scatter of outcome against sleep, with the least-squares line.
function sleepScatter(id, pts, { xLabel, yLabel, fmtX, fmtY, fit, tip, W = 520, H = 260 }) {
  const el = $(id);
  if (pts.length < 5) { el.innerHTML = '<p class="cap">Not enough nights with this measure yet.</p>'; return; }
  const L = 52, R = 12, T = 10, B = 40, iw = W - L - R, ih = H - T - B;
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const xt = niceTicks(Math.min(...xs), Math.max(...xs), 5), yt = niceTicks(Math.min(...ys), Math.max(...ys), 4);
  const X = v => L + (v - xt[0]) / (xt[xt.length - 1] - xt[0]) * iw, Y = v => T + ih - (v - yt[0]) / (yt[yt.length - 1] - yt[0]) * ih;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(`${yLabel} against ${xLabel}, ${pts.length} nights`)}">`;
  for (const v of yt) s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${css('grid')}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${fmtY(v, true)}</text>`;
  for (const v of xt) s += `<line x1="${X(v)}" x2="${X(v)}" y1="${T + ih}" y2="${T + ih + 4}" stroke="${css('muted')}"/><text x="${X(v)}" y="${T + ih + 16}" text-anchor="middle">${fmtX(v, true)}</text>`;
  s += `<text x="${L + iw / 2}" y="${H - 4}" text-anchor="middle">${esc(xLabel)}</text>`;
  if (yt[0] < 0 && yt[yt.length - 1] > 0) s += `<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="${css('muted')}"/>`;
  for (const p of pts) s += `<circle class="mark" cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="4" fill="${css('c5')}" fill-opacity=".55" tabindex="0"${tipAttr(fmtY(p.y), tip(p))}/>`;
  if (fit) {
    const a = xt[0], b = xt[xt.length - 1], ya = fit.icept + fit.slope * a, yb = fit.icept + fit.slope * b;
    s += `<line x1="${X(a)}" y1="${Y(ya)}" x2="${X(b)}" y2="${Y(yb)}" stroke="${css('ink')}" stroke-width="2" stroke-dasharray="${fit.p < 0.05 ? '0' : '5 4'}"/>`;
  }
  el.innerHTML = s + '</svg>';
  bindTips(el);
}

// The outcome per third of nights: a bar from zero (or from the lowest third, for levels such as
// HRV) per group, its value and how many nights stand behind it.
function thirdBars(id, res, cuts, { fmtY, levels = false, W = 360 }) {
  const el = $(id), M = SLEEP_MEASURES[sleepMeasure];
  const g = res.groups, vals = g.map(x => x.mean).filter(num);
  if (vals.length < 2) { el.innerHTML = '<p class="cap">Not enough nights in each group yet.</p>'; return; }
  const names = [`Worst third · under ${M.fmt(cuts[0])}`, `Middle · ${M.fmt(cuts[0])} to ${M.fmt(cuts[1])}`, `Best third · ${M.fmt(cuts[1])} and up`];
  const base = levels ? Math.min(...vals) - (Math.max(...vals) - Math.min(...vals) || Math.abs(vals[0]) * 0.1 || 1) * 0.6 : 0;
  const lo = Math.min(base, ...vals), hi = Math.max(base, ...vals), span = hi - lo || 1;
  const RH = 34, L = 0, iw = W - 70, H = RH * 3 + 4;
  const X = v => L + (v - lo) / span * iw;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(names.map((n, i) => `${n}: ${num(g[i].mean) ? fmtY(g[i].mean) : 'no data'}`).join('; '))}">`;
  g.forEach((x, i) => {
    const y = i * RH + 16;
    s += `<text x="0" y="${y - 4}" style="fill:${css('ink2')}">${esc(names[i])} · ${x.n} ${x.n === 1 ? 'night' : 'nights'}</text>`;
    if (!num(x.mean)) return;
    const a = X(Math.min(base, x.mean)), b = X(Math.max(base, x.mean));
    s += `<rect class="mark" x="${a}" y="${y}" width="${Math.max(2, b - a)}" height="12" rx="2" fill="${css(i === 2 ? 'c5' : i === 1 ? 'muted' : 'c3')}"${i === 1 ? ' fill-opacity=".6"' : ''} tabindex="0"${tipAttr(fmtY(x.mean), `${names[i]}, ${x.n} nights`)}/>`;
    s += `<text x="${b + 6}" y="${y + 10}" style="fill:${css('ink')};font-weight:500">${fmtY(x.mean)}</text>`;
  });
  if (!levels && lo < 0) s += `<line x1="${X(0)}" x2="${X(0)}" y1="4" y2="${H}" stroke="${css('muted')}"/>`;
  el.innerHTML = s + '</svg>';
  bindTips(el);
}

function renderSleep(D) {
  const rows = (D.sleep || []).map(r => ({ ...r, d: dayIso(r.d) }));
  const M = SLEEP_MEASURES[sleepMeasure], k = sleepMeasure;

  // Measure filter.
  $('sleepfilter').innerHTML = `<span class="eyebrow">Measure sleep by</span><div class="seg" role="group" aria-label="Sleep measure">${Object.entries(SLEEP_MEASURES).map(([key, m]) => `<button type="button" data-m="${key}" aria-pressed="${key === k}">${m.label}</button>`).join('')}</div>`;
  for (const b of $('sleepfilter').querySelectorAll('button')) b.onclick = () => {
    sleepMeasure = b.dataset.m;
    try { localStorage.setItem(SLEEP_KEY, sleepMeasure); } catch { /* storage blocked: the choice lasts this view */ }
    renderSleep(D);
  };

  if (rows.length < 14) {
    for (const id of ['sleepkpis', 'sleepfind', 'ch-sleep', 'ch-sleeprun', 'ch-sleeprunb', 'ch-sleephrv', 'ch-sleeprhr', 'ch-sleepready', 'ch-sleepdw', 'ch-sleepwk']) $(id).textContent = '';
    empty('sleepkpis', 'Two weeks of sleep data are needed before sleep can be compared with what followed.');
    return;
  }

  // Summary tiles: the last 30 nights against the 30 before.
  const last = rows[rows.length - 1].d, cut = iso(new Date(t(last) - 30 * DAY)), cut2 = iso(new Date(t(last) - 60 * DAY));
  const now = rows.filter(r => r.d > cut), before = rows.filter(r => r.d > cut2 && r.d <= cut);
  const avg = (a, f) => sMean(a.map(f).filter(num));
  const tile = (key, v, s) => `<div class="tile"><span class="eyebrow">${key}</span><span class="v">${v}</span><span class="s">${s}</span></div>`;
  const hNow = avg(now, r => r.h), hBefore = avg(before, r => r.h), scNow = avg(now, r => r.score), scBefore = avg(before, r => r.score);
  const short = now.filter(r => num(r.h)).length ? now.filter(r => num(r.h) && r.h < 7).length / now.filter(r => num(r.h)).length : null;
  const bed = median(now.map(r => r.bed)), bedSpread = (() => { const b = now.map(r => r.bed).filter(num); return b.length > 2 ? Math.sqrt(sVar(b)) * 60 : null; })();
  const deep = avg(now, r => r.deep), rem = avg(now, r => r.rem);
  $('sleepkpis').innerHTML = `<div class="tiles">${[
    tile('Sleep, 30 nights', num(hNow) ? `${hNow.toFixed(1)}<small>h</small>` : '–', num(hNow) && num(hBefore) ? `${signed((hNow - hBefore) * 60, 0)} min a night vs the 30 before` : 'Average per night'),
    tile('Sleep score', num(scNow) ? `${Math.round(scNow)}<small>/100</small>` : '–', num(scNow) && num(scBefore) ? `${signed(scNow - scBefore, 0)} vs the 30 before` : 'Average'),
    tile('Under 7 hours', num(short) ? `${Math.round(short * 100)}<small>%</small>` : '–', 'Of the last 30 nights'),
    tile('Bedtime', num(bed) ? bedFmt(bed) : '–', num(bedSpread) ? `Typical, varies ±${Math.round(bedSpread)} min` : 'Typical'),
    tile('Deep · REM', num(deep) && num(rem) ? `${Math.round(deep * 100)}<small>%</small> · ${Math.round(rem * 100)}<small>%</small>` : '–', 'Share of sleep, 30 nights'),
  ].join('')}</div>`;

  // Sleep per night with its 7-night average.
  lineChart('ch-sleep', rows.filter(r => num(r.h7)).map(r => [t(r.d), r.h7]), { fmt: v => `${v.toFixed(1)} h`, label: '7-night average sleep', color: 'c5', W: wideW(), H: 200 });
  const best = rows.filter(r => num(r.h)).reduce((a, r) => (!a || r.h > a.h ? r : a), null);
  $('cap-sleep').textContent = `7-night average of hours asleep, ${rows.length} nights since ${fmtDate(rows[0].d)}.${best ? ` Longest night: ${best.h.toFixed(1)} h, ending ${fmtDate(best.d)}.` : ''}`;

  // The thirds, on every night with the chosen measure.
  const cuts = sleepThirds(rows.map(r => r[k]));
  const pairsOf = f => rows.filter(r => num(r[k]) && num(f(r))).map(r => [r[k], f(r), r]);
  const outcomes = [
    { key: 'ef', topic: 'Running', name: 'Run efficiency', f: r => num(r.ef) ? r.ef * 100 : null, fmt: (v, axis) => axis ? `${v > 0 ? '+' : ''}${v}%` : signed(v, 1, '%'), better: 1,
      unit: '% speed per heartbeat', say: d => `runs were ${Math.abs(d).toFixed(1)}% ${d >= 0 ? 'more' : 'less'} efficient (speed per heartbeat, against your own last 6 weeks)` },
    { key: 'hrv', topic: 'Recovery', name: 'Morning HRV', f: r => r.hrv, fmt: v => `${Math.round(v)} ms`, dfmt: v => signed(v, 1, ' ms'), better: 1, levels: true,
      say: d => `overnight HRV was ${Math.abs(d).toFixed(1)} ms ${d >= 0 ? 'higher' : 'lower'}` },
    { key: 'rhr', topic: 'Recovery', name: 'Resting heart rate', f: r => r.rhr, fmt: v => `${v.toFixed(v % 1 ? 1 : 0)} bpm`, dfmt: v => signed(v, 1, ' bpm'), better: -1, levels: true,
      say: d => `resting heart rate was ${Math.abs(d).toFixed(1)} bpm ${d >= 0 ? 'higher' : 'lower'}` },
    { key: 'ready', topic: 'Recovery', name: 'Readiness', f: r => r.ready, fmt: v => `${Math.round(v)}`, dfmt: v => signed(v, 0, ' points'), better: 1, levels: true,
      say: d => `training readiness was ${Math.abs(d).toFixed(0)} points ${d >= 0 ? 'higher' : 'lower'}` },
    { key: 'dw', topic: 'Weight', name: 'Daily weight change', f: r => r.dw, fmt: (v, axis) => axis ? `${v > 0 ? '+' : ''}${v} kg` : signed(v, 2, ' kg'), better: -1,
      say: d => `the morning weigh-in moved ${Math.abs(d).toFixed(2)} kg ${d >= 0 ? 'more up' : 'more down'} from the day before` },
  ];
  const results = {};
  for (const o of outcomes) {
    const pairs = pairsOf(o.f);
    results[o.key] = { pairs, c: pearson(pairs), t: cuts ? byThird(pairs, cuts) : null };
  }

  // Weekly: a week's sleep against the change in average weight from the week before.
  const weekOf = d => iso(mondayOf(new Date(t(d))));
  const weeks = new Map();
  for (const r of rows) {
    const w = weeks.get(weekOf(r.d)) || { s: [], kg: [] };
    if (num(r[k === 'h7' ? 'h' : k])) w.s.push(r[k === 'h7' ? 'h' : k]);
    if (num(r.weight)) w.kg.push(r.weight);
    weeks.set(weekOf(r.d), w);
  }
  const wk = [...weeks.entries()].sort(([a], [b]) => a < b ? -1 : 1);
  const weekly = [];
  for (let i = 1; i < wk.length; i++) {
    const [d, w] = wk[i], [pd, p] = wk[i - 1];
    if (t(d) - t(pd) !== 7 * DAY || w.s.length < 4 || !w.kg.length || !p.kg.length) continue;
    weekly.push({ d, x: sMean(w.s), y: sMean(w.kg) - sMean(p.kg), n: w.s.length });
  }
  const weeklyC = pearson(weekly.map(w => [w.x, w.y]));

  // Findings: one card per outcome, strongest evidence first.
  const findings = outcomes.map(o => {
    const R = results[o.key], diff = R.t?.diff, st = strength(R.c, diff), df = o.dfmt || o.fmt;
    const n = R.pairs.length;
    const head = !diff ? 'Not enough data yet'
      : st.word === 'no clear link' ? `No clear difference in ${o.name.toLowerCase()}`
      : `${o.name}: ${df(diff.d)} after your best-slept nights`;
    const body = !diff ? `Needs at least three nights in each third; ${n} so far.`
      : `After the best-slept third of nights (${M.of} ${M.fmt(cuts[1])} or more), ${o.say(diff.d)} than after the worst third (under ${M.fmt(cuts[0])}). 95% interval ${df(diff.lo)} to ${df(diff.hi)}.`;
    const rank = !diff ? 9 : st.cls === 'link' ? 0 : st.word === 'possible link' ? 1 : 2;
    return { rank, html: `<div class="card ${st.cls}"><div class="head"><span class="eyebrow">${o.topic}</span><span class="eyebrow">${st.word}</span></div><h3>${esc(head)}</h3><p>${esc(body)}</p>` +
      `<p class="basis">${n} nights${R.c ? ` · r = ${R.c.r.toFixed(2)}, p = ${R.c.p < 0.001 ? '<0.001' : R.c.p.toFixed(3)}` : ''}</p></div>` };
  });
  {
    const st = weeklyC ? (weeklyC.p < 0.05 ? { word: 'clear link', cls: 'link' } : weeklyC.p < 0.15 ? { word: 'possible link', cls: '' } : { word: 'no clear link', cls: 'low' }) : { word: 'too little data', cls: 'low' };
    const per = weeklyC ? weeklyC.slope * (k === 'score' ? 10 : 1) : null;
    const head = !weeklyC ? 'Not enough weeks yet' : st.cls === 'low' ? 'No clear link between weekly sleep and weight' : `Weight: ${signed(per, 2, ' kg')} a week per ${k === 'score' ? '10 score points' : 'extra hour a night'}`;
    findings.push({ rank: !weeklyC ? 9 : st.cls === 'link' ? 0 : st.cls ? 2 : 1, html: `<div class="card ${st.cls}"><div class="head"><span class="eyebrow">Weight trend</span><span class="eyebrow">${st.word}</span></div><h3>${esc(head)}</h3>` +
      `<p>${weeklyC ? `Weeks with more sleep against the change in average weight from the week before, over ${weekly.length} weeks. The line's slope is ${signed(weeklyC.slope, 2, ' kg')} per ${k === 'score' ? 'score point' : 'hour'}.` : 'Needs five weeks with at least four nights of sleep and weigh-ins in that week and the one before.'}</p>` +
      `<p class="basis">${weekly.length} weeks${weeklyC ? ` · r = ${weeklyC.r.toFixed(2)}, p = ${weeklyC.p < 0.001 ? '<0.001' : weeklyC.p.toFixed(3)}` : ''}</p></div>` });
  }
  $('sleepfind').innerHTML = findings.sort((a, b) => a.rank - b.rank).map(f => f.html).join('');

  // Running.
  const run = results.ef, ro = outcomes[0];
  const tipRun = p => { const r = p.r; return `${fmtDate(r.d)} · ${M.fmt(p.x)} · ${num(r.km) ? r.km.toFixed(1) + ' km' : ''}${num(r.pace) ? ' at ' + pace(r.pace) + ' /km' : ''}${num(r.hr) ? ', ' + r.hr + ' bpm' : ''}`; };
  sleepScatter('ch-sleeprun', run.pairs.map(([x, y, r]) => ({ x, y, r })), { xLabel: M.axis, yLabel: 'Run efficiency', fmtX: M.fmt, fmtY: ro.fmt, fit: run.c, tip: tipRun, W: 480 });
  if (cuts) thirdBars('ch-sleeprunb', run.t, cuts, { fmtY: ro.fmt }); else empty('ch-sleeprunb', 'Not enough nights yet.');
  $('cap-sleeprun').textContent = `Each dot is a run day after a night's sleep. 0% is your usual efficiency over the 6 weeks before that run, so fitness gained over months does not count as sleep. Races, runs under 2 km and runs without heart rate are left out; the line is dashed when it could be chance.`;
  // Run days per third, with the raw numbers behind the efficiency.
  if (cuts) {
    const g = [[], [], []];
    for (const r of rows) if (num(r[k]) && r.runs > 0 && num(r.km)) g[thirdOf(r[k], cuts)].push(r);
    const names = ['Worst third', 'Middle', 'Best third'];
    $('tbl-sleeprun').innerHTML = `<table><thead><tr><th>Sleep before</th><th class="n">Run days</th><th class="n">Avg km</th><th class="n">Pace</th><th class="n">Avg HR</th><th class="n">Efficiency</th></tr></thead><tbody>${g.map((a, i) => {
      const km = sMean(a.map(r => r.km)), pc = sMean(a.filter(r => num(r.pace)).map(r => r.pace)), hr = sMean(a.filter(r => num(r.hr)).map(r => r.hr)), ef = sMean(a.filter(r => num(r.ef)).map(r => r.ef * 100));
      return `<tr><td>${names[i]}</td><td class="n">${a.length}</td><td class="n">${num(km) ? km.toFixed(1) : '–'}</td><td class="n">${num(pc) ? pace(pc) + ' /km' : '–'}</td><td class="n">${num(hr) ? Math.round(hr) : '–'}</td><td class="n">${num(ef) ? signed(ef, 1, '%') : '–'}</td></tr>`;
    }).join('')}</tbody></table>`;
  }

  // Recovery: the morning after.
  for (const [key, id] of [['hrv', 'ch-sleephrv'], ['rhr', 'ch-sleeprhr'], ['ready', 'ch-sleepready']]) {
    const o = outcomes.find(x => x.key === key);
    if (cuts) thirdBars(id, results[key].t, cuts, { fmtY: o.fmt, levels: true, W: 320 }); else empty(id, 'Not enough nights yet.');
  }

  // Weight.
  const dw = results.dw, wo = outcomes.find(x => x.key === 'dw');
  if (cuts) thirdBars('ch-sleepdw', dw.t, cuts, { fmtY: wo.fmt, W: 420 }); else empty('ch-sleepdw', 'Not enough weigh-ins yet.');
  sleepScatter('ch-sleepwk', weekly, {
    xLabel: k === 'score' ? 'Average sleep score that week' : 'Average sleep that week (h)', yLabel: 'Weight change from the week before',
    fmtX: k === 'score' ? (v => `${Math.round(v)}`) : (v => `${v.toFixed(1)} h`), fmtY: wo.fmt, fit: weeklyC,
    tip: w => `Week of ${fmtDate(w.d)} · ${k === 'score' ? Math.round(w.x) : w.x.toFixed(1) + ' h'} average over ${w.n} nights`, W: 480,
  });
}
