// Fitness tab: is the engine getting better, and which training moved the half marathon prediction?
// Aerobic fitness (D.aerobic, marts.fct_aerobic_fitness): per week, over the 6 weeks up to it, the
// heart rate a fixed reference pace costs and the metres covered per heartbeat on steady runs.
// Training blocks (D.blocks, marts.fct_training_blocks): each 4-week block's volume, longest run, load
// and zone mix against how much faster the prediction got by 2 weeks after it. Every driver is
// correlated with that gain while holding the starting prediction fixed (partial correlation), since
// a slower start leaves more to gain; blocks overlap by 3 weeks, so a quarter of them count as
// independent for the p-value. Uses sleep.js's statistics (sMean, pearson, normCdf).
// renderPage() calls renderFitness().
const STEADY = r => num(r.km) && r.km >= 3 && num(r.pace) && r.pace >= 4 && r.pace <= 9 && num(r.avg_hr) && r.avg_hr > 0;
// Below this many degrees of freedom (independent blocks minus 3) a driver is only an early read.
const EARLY_DF = 5;
const pctFmt = (v, d = 0) => `${(v * 100).toFixed(d)}%`;
const DRIVERS = [
  { key: 'km', name: 'Running per week', fmt: v => `${v.toFixed(0)} km`, more: 'more running' },
  { key: 'rpw', name: 'Runs per week', fmt: v => v.toFixed(1), more: 'more runs a week' },
  { key: 'lr', name: 'Longest run', fmt: v => `${v.toFixed(0)} km`, more: 'a longer long run' },
  { key: 'load', name: 'Training load per week', fmt: v => `${Math.round(v)}`, more: 'more training load' },
  { key: 'easy', name: 'Easy share (zones 1 and 2)', fmt: v => pctFmt(v), more: 'more easy running' },
  { key: 'tempo', name: 'Tempo share (zone 3)', fmt: v => pctFmt(v), more: 'more tempo running' },
  { key: 'hard', name: 'Hard share (zones 4 and 5)', fmt: v => pctFmt(v), more: 'more hard running' },
];

// Two-sided p of a correlation r with df degrees of freedom (t with a normal approximation).
function pOfR(r, df) {
  if (df < 1) return null;
  const tt = Math.abs(r) * Math.sqrt(df / Math.max(1e-12, 1 - r * r));
  const z = tt * (1 - 1 / (4 * df)) / Math.sqrt(1 + tt * tt / (2 * df));
  return 2 * (1 - normCdf(z));
}
// Correlation of x and y with z held fixed, from the three pairwise correlations.
function partialR(rows) {
  const rxy = pearson(rows.map(r => [r.x, r.y]))?.r, rxz = pearson(rows.map(r => [r.x, r.z]))?.r, ryz = pearson(rows.map(r => [r.y, r.z]))?.r;
  if (![rxy, rxz, ryz].every(num)) return null;
  const den = Math.sqrt((1 - rxz ** 2) * (1 - ryz ** 2));
  return den > 1e-9 ? (rxy - rxz * ryz) / den : null;
}

// A scatter with one or more series, each with its own colour and least-squares line.
// `hline` ({y, label}) draws a dashed reference level, such as the average of a comparison group.
function multiScatter(id, series, { xLabel, fmtX, fmtY, W = 520, H = 280, xTicks, yTicks, hline = null }) {
  const el = $(id), all = series.flatMap(s => s.pts);
  if (all.length < 3) { el.innerHTML = '<p class="cap">Not enough data yet.</p>'; return; }
  const L = 52, R = 12, T = 10, B = 40, iw = W - L - R, ih = H - T - B;
  const xt = xTicks || niceTicks(Math.min(...all.map(p => p.x)), Math.max(...all.map(p => p.x)), 5);
  const ys = all.map(p => p.y).concat(hline ? [hline.y] : []);
  const yt = yTicks || niceTicks(Math.min(...ys), Math.max(...ys), 4);
  const X = v => L + (v - xt[0]) / (xt[xt.length - 1] - xt[0]) * iw, Y = v => T + ih - (v - yt[0]) / (yt[yt.length - 1] - yt[0]) * ih;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(series.map(x => `${x.name}: ${x.pts.length}`).join('; '))}">`;
  for (const v of yt) s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${css('grid')}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${fmtY(v, true)}</text>`;
  for (const v of xt) s += `<line x1="${X(v)}" x2="${X(v)}" y1="${T + ih}" y2="${T + ih + 4}" stroke="${css('muted')}"/><text x="${X(v)}" y="${T + ih + 16}" text-anchor="middle">${fmtX(v, true)}</text>`;
  s += `<text x="${L + iw / 2}" y="${H - 4}" text-anchor="middle">${esc(xLabel)}</text>`;
  if (yt[0] < 0 && yt[yt.length - 1] > 0) s += `<line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="${css('muted')}"/>`;
  if (hline) s += `<line x1="${L}" x2="${W - R}" y1="${Y(hline.y)}" y2="${Y(hline.y)}" stroke="${css('ink2')}" stroke-dasharray="5 4"/><text x="${W - R}" y="${Y(hline.y) - 5}" text-anchor="end" style="fill:${css('ink2')}">${esc(hline.label)}</text>`;
  for (const sr of series) {
    for (const p of sr.pts) s += `<circle class="mark" cx="${X(p.x).toFixed(1)}" cy="${Y(p.y).toFixed(1)}" r="${p.r || 4}" fill="${css(sr.color)}" fill-opacity=".6" tabindex="0"${tipAttr(p.tv, p.tl)}/>`;
    const c = sr.fit !== false && pearson(sr.pts.map(p => [p.x, p.y]));
    if (c) {
      const xs = sr.pts.map(p => p.x), a = Math.min(...xs), b = Math.max(...xs);
      s += `<line x1="${X(a)}" y1="${Y(c.icept + c.slope * a)}" x2="${X(b)}" y2="${Y(c.icept + c.slope * b)}" stroke="${css(sr.color)}" stroke-width="2.5"/>`;
    }
  }
  el.innerHTML = s + '</svg>';
  bindTips(el);
}

function renderFitness(D) {
  const aer = (D.aerobic || []).map(r => ({ ...r, wk: dayIso(r.wk) }));
  const tile = (k, v, s) => `<div class="tile"><span class="eyebrow">${k}</span><span class="v">${v}</span><span class="s">${s}</span></div>`;

  // Aerobic fitness.
  const withHr = aer.filter(r => num(r.hr_ref)), withEf = aer.filter(r => num(r.ef));
  const ref = aer.find(r => num(r.ref))?.ref;
  const refLabel = num(ref) ? `${pace(ref)} /km` : 'the reference pace';
  const hrNow = withHr[withHr.length - 1], hrFirst = withHr[0], hr6 = withHr[withHr.length - 7];
  const efNow = withEf[withEf.length - 1], efFirst = withEf[0];
  const days = D.daily || [], vo2 = days.filter(r => num(r.vo2max)), st = D.status || {};
  const vo2Now = num(st.vo2max) ? st.vo2max : vo2[vo2.length - 1]?.vo2max, vo2First = median(vo2.slice(0, 14).map(r => r.vo2max));
  $('fitkpis').innerHTML = `<div class="tiles">${[
    tile(`Heart rate at ${refLabel}`, hrNow ? `${Math.round(hrNow.hr_ref)}<small>bpm</small>` : '–',
      hrNow && hrFirst && hrNow !== hrFirst ? `${signed(hrNow.hr_ref - hrFirst.hr_ref, 0)} since ${fmtDate(hrFirst.wk)}${hr6 ? ` · ${signed(hrNow.hr_ref - hr6.hr_ref, 0)} in 6 weeks` : ''}` : 'Over the last 6 weeks'),
    tile('Distance per heartbeat', efNow ? `${efNow.ef.toFixed(2)}<small>m</small>` : '–',
      efNow && efFirst && efNow !== efFirst ? `${signed((efNow.ef / efFirst.ef - 1) * 100, 1, '%')} since ${fmtDate(efFirst.wk)}` : 'Steady runs, last 6 weeks'),
    tile('VO2 max', num(vo2Now) ? `${vo2Now.toFixed(1)}<small>ml/kg/min</small>` : '–', num(vo2Now) && num(vo2First) ? `${signed(vo2Now - vo2First, 1)} since ${fmtDate(vo2[0].d)}` : 'Garmin'),
    tile('Steady runs', efNow ? `${efNow.runs}` : '–', 'In the last 6 weeks, behind these numbers'),
  ].join('')}</div>`;
  lineChart('ch-hrref', withHr.map(r => [t(r.wk), r.hr_ref]), { fmt: v => `${Math.round(v)} bpm`, label: `Heart rate at ${refLabel}`, color: 'c6' });
  lineChart('ch-ef', withEf.map(r => [t(r.wk), r.ef]), { fmt: v => `${v.toFixed(2)} m`, label: 'Metres per heartbeat', color: 'c2' });

  // Heart rate against pace, early runs against recent ones: the same pace at a lower heart rate
  // shows as the recent line sitting below the early one.
  const steady = (D.runs || []).filter(STEADY).map(r => ({ ...r, d: dayIso(r.activity_date) }));
  if (steady.length >= 6) {
    const first = t(steady[0].d), last = t(steady[steady.length - 1].d);
    const early = steady.filter(r => t(r.d) < first + 42 * DAY), recent = steady.filter(r => t(r.d) > last - 42 * DAY && t(r.d) >= first + 42 * DAY);
    const pt = r => ({ x: r.pace, y: r.avg_hr, r: 3 + Math.min(5, r.km / 4), tv: `${Math.round(r.avg_hr)} bpm`, tl: `${fmtDate(r.d)} · ${r.km.toFixed(1)} km at ${pace(r.pace)} /km` });
    multiScatter('ch-hrpace', [
      { name: `First 6 weeks, from ${fmtDate(steady[0].d)}`, color: 'c3', pts: early.map(pt) },
      { name: 'Last 6 weeks', color: 'c1', pts: recent.map(pt) },
    ], { xLabel: 'Pace (min/km), faster to the left', fmtX: v => pace(v), fmtY: v => `${Math.round(v)}`, W: wideW(), H: 300 });
    $('leg-hrpace').innerHTML = `<span><b style="background:var(--c3)"></b>First 6 weeks (${early.length} runs)</span><span><b style="background:var(--c1)"></b>Last 6 weeks (${recent.length} runs)</span>`;
  } else { empty('ch-hrpace', 'Needs six steady runs.'); $('leg-hrpace').textContent = ''; }
  $('cap-hrpace').textContent = `Average heart rate against pace on steady runs (at least 3 km, 4:00 to 9:00 /km). The lower the line, the less your heart works for a pace. The tiles read each line at ${refLabel}, the median pace of all your steady runs, over the 6 weeks up to each week; races are left out there.`;

  // What moved the prediction.
  const blocks = (D.blocks || []).map(b => ({ ...b, wk: dayIso(b.wk) })), done = blocks.filter(b => num(b.dhm) && num(b.hm0));
  const neff = done.length / 4, df = Math.floor(neff) - 3;
  const drivers = DRIVERS.map(f => {
    const rows = done.filter(b => num(b[f.key])).map(b => ({ x: b[f.key], y: -b.dhm * 100, z: b.hm0, b }));
    const raw = pearson(rows.map(r => [r.x, r.y])), pr = rows.length >= 8 ? partialR(rows) : null;
    const p = num(pr) ? pOfR(pr, df) : null;
    const verdict = !num(pr) ? 'too little data' : df < EARLY_DF ? 'early read' : p < 0.05 ? 'strong' : p < 0.2 ? 'a hint' : 'no signal';
    return { ...f, rows, raw, pr, p, verdict };
  }).sort((a, b) => Math.abs(b.pr ?? 0) - Math.abs(a.pr ?? 0));

  const best = drivers.find(d => num(d.pr));
  const top = drivers.filter(d => num(d.pr) && (d.verdict === 'strong' || d.verdict === 'a hint'));
  const blockTxt = `${done.length} blocks with an outcome, about ${Math.max(0, Math.floor(neff))} independent`;
  let lead;
  if (!best) lead = `<h3>Not enough blocks yet</h3><p>Each block needs its 4 weeks plus 2 to adapt, and a prediction before and after. ${blockTxt}.</p>`;
  else if (df < EARLY_DF) lead = `<h3>Early read: ${esc(best.more)} went with ${best.pr < 0 ? 'smaller' : 'bigger'} gains</h3><p>Across ${blockTxt}, ${esc(best.more)} lined up most with how much faster the prediction got (r ${best.pr.toFixed(2)}, starting level held fixed). With so few independent blocks this is a lead to watch, not a finding. About ${Math.max(1, Math.ceil((EARLY_DF + 3 - neff) * 4))} more weeks of training make the first verdicts possible.</p>`;
  else if (!top.length) lead = `<h3>No training factor stands out yet</h3><p>Across ${blockTxt}, none of the drivers below separates the blocks that made you faster from the ones that did not, once your starting level is held fixed.</p>`;
  else lead = `<h3>${esc(top.map(d => d.more).join(', ').replace(/^./, c => c.toUpperCase()))}: ${top[0].pr > 0 ? 'faster' : 'slower'} predictions after</h3><p>Across ${blockTxt}: ${top.map(d => `${esc(d.more)} (r ${d.pr.toFixed(2)}, ${d.verdict})`).join('; ')}. Positive r means blocks with more of it were followed by a faster prediction.</p>`;
  $('fitfind').innerHTML = `<div class="card${top.some(d => d.verdict === 'strong') ? ' link' : ''}"><div class="head"><span class="eyebrow">Half marathon prediction</span><span class="eyebrow">${esc(blockTxt)}</span></div>${lead}</div>`;

  // Drivers: partial correlation with the gain, one bar each from zero.
  {
    const el = $('ch-drivers'), W = 480, RH = 42, L = 0, mid = W / 2, half = W / 2 - 60, H = RH * drivers.length + 20;
    if (!done.length) empty('ch-drivers', 'No block has an outcome yet.');
    else {
      let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(drivers.map(d => `${d.name}: ${num(d.pr) ? d.pr.toFixed(2) : 'no data'}`).join('; '))}">`;
      s += `<text x="${mid - half}" y="${H - 2}">← slower after</text><text x="${mid + half}" y="${H - 2}" text-anchor="end">faster after →</text>`;
      drivers.forEach((d, i) => {
        const y = i * RH + 14;
        s += `<text x="${L}" y="${y}" style="fill:${css('ink2')}">${esc(d.name)} · ${d.verdict}</text>`;
        if (!num(d.pr)) return;
        const x = mid + d.pr * half, a = Math.min(mid, x), w = Math.max(2, Math.abs(x - mid));
        s += `<rect class="mark" x="${a}" y="${y + 8}" width="${w}" height="12" rx="2" fill="${css(d.pr >= 0 ? 'c2' : 'c3')}" fill-opacity="${d.verdict === 'strong' ? 1 : d.verdict === 'a hint' || d.verdict === 'early read' ? 0.75 : 0.4}" tabindex="0"${tipAttr(`r ${d.pr.toFixed(2)}`, `${d.name}: partial correlation with the gain, starting level held fixed${num(d.p) ? `, p ${d.p.toFixed(2)}` : ''}; without holding it, r ${d.raw ? d.raw.r.toFixed(2) : '–'}`)}/>`;
        s += `<text x="${d.pr >= 0 ? x + 6 : x - 6}" y="${y + 18}" text-anchor="${d.pr >= 0 ? 'start' : 'end'}" style="fill:${css('ink')};font-weight:500">${d.pr >= 0 ? '+' : '−'}${Math.abs(d.pr).toFixed(2)}</text>`;
      });
      s += `<line x1="${mid}" x2="${mid}" y1="6" y2="${H - 14}" stroke="${css('muted')}"/>`;
      el.innerHTML = s + '</svg>';
      bindTips(el);
    }
  }
  // The strongest driver as a scatter: each dot a block.
  if (best) {
    multiScatter('ch-driver', [{ name: best.name, color: 'c5', pts: best.rows.map(r => ({ x: r.x, y: r.y, tv: `${signed(r.y, 1, '%')} faster`, tl: `Block ${fmtDate(iso(new Date(t(r.b.wk) - 21 * DAY)))} to ${fmtDate(iso(new Date(t(r.b.wk) + 6 * DAY)))} · ${best.name.toLowerCase()} ${best.fmt(r.x)} · prediction ${hms(r.b.hm0)} to ${hms(r.b.hm1)}` })) }],
      { xLabel: best.name, fmtX: v => best.fmt(v), fmtY: (v, axis) => axis ? `${v}%` : signed(v, 1, '%'), W: 480 });
    $('h-driver').textContent = `${best.name} against the gain in prediction`;
  } else { empty('ch-driver', 'No block has an outcome yet.'); $('h-driver').textContent = 'Strongest driver'; }

  // The blocks as a table, newest first.
  $('tbl-blocks').innerHTML = blocks.length ? `<table><thead><tr><th>Block</th><th class="n">km/wk</th><th class="n">Runs/wk</th><th class="n">Longest</th><th class="n">Easy</th><th class="n">Tempo</th><th class="n">Hard</th><th class="n">Half before</th><th class="n">2 weeks after</th><th class="n">Gain</th></tr></thead><tbody>${
    [...blocks].reverse().map(b => `<tr><td>${fmtDate(iso(new Date(t(b.wk) - 21 * DAY)))} to ${fmtDate(iso(new Date(t(b.wk) + 6 * DAY)))}</td><td class="n">${num(b.km) ? b.km.toFixed(1) : '–'}</td><td class="n">${num(b.rpw) ? b.rpw.toFixed(1) : '–'}</td><td class="n">${num(b.lr) ? b.lr.toFixed(1) : '–'}</td><td class="n">${num(b.easy) ? pctFmt(b.easy) : '–'}</td><td class="n">${num(b.tempo) ? pctFmt(b.tempo) : '–'}</td><td class="n">${num(b.hard) ? pctFmt(b.hard) : '–'}</td><td class="n">${num(b.hm0) ? hms(b.hm0) : '–'}</td><td class="n">${num(b.hm1) ? hms(b.hm1) : 'adapting'}</td><td class="n">${num(b.dhm) ? signed(-b.dhm * 100, 1, '%') : '–'}</td></tr>`).join('')
  }</tbody></table>` : '';
}
