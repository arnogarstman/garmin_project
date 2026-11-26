// When you run (Fitness tab): does the time of day change how a run goes, and do late runs cost the
// night after? D.timing (marts.fct_run_efficiency) holds each comparable run with its efficiency
// against the 6 weeks before, its start time, and the night after with the hours from the run's end to
// bedtime. Nights after a day without a run (from D.sleep) are the baseline for sleep. Differences
// carry a Welch 95% interval; with few runs in a group, the interval says how little it shows.
// Uses sleep.js's statistics and fitness.js's scatter. renderPage() calls renderTiming().
const TODS = [['morning', 'Morning', 'before 11:00'], ['midday', 'Midday', '11:00 to 15:00'], ['afternoon', 'Afternoon', '15:00 to 18:00'], ['evening', 'Evening', 'from 18:00']];
const BED_GAPS = [['late', 'Ended under 3 h before bed', g => g < 3], ['mid', '3 to 6 h before bed', g => g >= 3 && g < 6], ['early', '6 h or more before bed', g => g >= 6]];

// Mean with a 95% interval of the mean, and the difference of two groups with a Welch interval.
const meanCi = a => { const m = sMean(a), v = sVar(a); return a.length ? { n: a.length, m, half: a.length > 1 ? 1.96 * Math.sqrt(v / a.length) : null } : { n: 0, m: null, half: null }; };
function welch(a, b) {
  if (a.length < 3 || b.length < 3) return null;
  const d = sMean(a) - sMean(b), se = Math.sqrt(sVar(a) / a.length + sVar(b) / b.length);
  return { d, lo: d - 1.96 * se, hi: d + 1.96 * se, clear: d - 1.96 * se > 0 || d + 1.96 * se < 0 };
}
const hhmm = h => `${String(Math.floor(h)).padStart(2, '0')}:${String(Math.round((h % 1) * 60)).padStart(2, '0')}`;

// Group means with interval whiskers, one row per group, from a zero line (or from a floor for levels).
function ciBars(id, groups, { fmt, levels = false, W = 480 }) {
  const el = $(id), G = groups.filter(g => num(g.m));
  if (!G.length) { el.innerHTML = '<p class="cap">Not enough runs yet.</p>'; return; }
  const ends = G.flatMap(g => [g.m - (g.half || 0), g.m + (g.half || 0)]);
  let lo = Math.min(...ends), hi = Math.max(...ends);
  if (!levels) { lo = Math.min(0, lo); hi = Math.max(0, hi); } else { const pad = (hi - lo) * 0.15 || 1; lo -= pad; hi += pad; }
  const RH = 42, iw = W - 80, H = RH * groups.length + 4, X = v => (v - lo) / (hi - lo || 1) * iw;
  const base = levels ? lo : 0;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(groups.map(g => `${g.name}: ${num(g.m) ? fmt(g.m) : 'no runs'}`).join('; '))}">`;
  groups.forEach((g, i) => {
    const y = i * RH + 14;
    s += `<text x="0" y="${y}" style="fill:${css('ink2')}">${esc(g.name)} · ${g.n} ${g.unit || 'runs'}</text>`;
    if (!num(g.m)) return;
    const a = X(Math.min(base, g.m)), b = X(Math.max(base, g.m));
    s += `<rect class="mark" x="${a}" y="${y + 8}" width="${Math.max(2, b - a)}" height="12" rx="2" fill="${css(g.color || 'c1')}" fill-opacity="${g.n < 5 ? 0.4 : 0.8}" tabindex="0"${tipAttr(fmt(g.m), `${g.name}, ${g.n} ${g.unit || 'runs'}${num(g.half) ? `; 95% interval ${fmt(g.m - g.half)} to ${fmt(g.m + g.half)}` : ''}`)}/>`;
    if (num(g.half)) s += `<line x1="${X(g.m - g.half)}" x2="${X(g.m + g.half)}" y1="${y + 14}" y2="${y + 14}" stroke="${css('ink')}" stroke-width="1.5"/><line x1="${X(g.m - g.half)}" x2="${X(g.m - g.half)}" y1="${y + 10}" y2="${y + 18}" stroke="${css('ink')}"/><line x1="${X(g.m + g.half)}" x2="${X(g.m + g.half)}" y1="${y + 10}" y2="${y + 18}" stroke="${css('ink')}"/>`;
    s += `<text x="${Math.max(b, num(g.half) ? X(g.m + g.half) : b) + 6}" y="${y + 18}" style="fill:${css('ink')};font-weight:500">${fmt(g.m)}</text>`;
  });
  if (!levels && lo < 0) s += `<line x1="${X(0)}" x2="${X(0)}" y1="4" y2="${H}" stroke="${css('muted')}"/>`;
  el.innerHTML = s + '</svg>';
  bindTips(el);
}

function renderTiming(D) {
  const runs = (D.timing || []).map(r => ({ ...r, d: dayIso(r.activity_date) }));
  const card = (topic, cls, word, head, body, basis) => `<div class="card ${cls}"><div class="head"><span class="eyebrow">${topic}</span><span class="eyebrow">${word}</span></div><h3>${esc(head)}</h3><p>${esc(body)}</p><p class="basis">${esc(basis)}</p></div>`;
  if (runs.length < 10) {
    empty('timefind', 'Needs ten comparable runs before the time of day can be compared.');
    for (const id of ['ch-tod', 'tbl-tod', 'ch-bedgap', 'ch-bedgrp']) $(id).textContent = '';
    return;
  }

  // Efficiency by time of day.
  const pctF = v => signed(v, 1, '%');
  const by = TODS.map(([k, name, span]) => {
    const rs = runs.filter(r => r.tod === k), ev = rs.filter(r => num(r.ev)).map(r => r.ev * 100);
    return { k, name, span, rs, ev, ...meanCi(ev), color: k === 'evening' ? 'c5' : k === 'morning' ? 'c3' : 'c1' };
  });
  ciBars('ch-tod', by.map(g => ({ ...g, name: `${g.name} (${g.span})` })), { fmt: pctF });
  const avgOf = (rs, k) => sMean(rs.map(r => r[k]).filter(num));
  $('tbl-tod').innerHTML = `<table><thead><tr><th>Start</th><th class="n">Runs</th><th class="n">Avg km</th><th class="n">Pace</th><th class="n">Avg HR</th><th class="n">Load</th><th class="n">Efficiency</th></tr></thead><tbody>${by.map(g => {
    const km = avgOf(g.rs, 'km'), pc = avgOf(g.rs, 'pace'), hr = avgOf(g.rs, 'avg_hr'), ld = avgOf(g.rs, 'load');
    return `<tr><td>${g.name}, ${g.span}</td><td class="n">${g.rs.length}</td><td class="n">${num(km) ? km.toFixed(1) : '–'}</td><td class="n">${num(pc) ? pace(pc) + ' /km' : '–'}</td><td class="n">${num(hr) ? Math.round(hr) : '–'}</td><td class="n">${num(ld) ? Math.round(ld) : '–'}</td><td class="n">${num(g.m) ? pctF(g.m) : '–'}</td></tr>`;
  }).join('')}</tbody></table>`;

  // The best-run time of day against all other runs, among groups with five or more.
  const cands = by.filter(g => g.ev.length >= 5).sort((a, b) => b.m - a.m);
  const cards = [];
  if (cands.length >= 2) {
    const best = cands[0], rest = runs.filter(r => r.tod !== best.k && num(r.ev)).map(r => r.ev * 100), w = welch(best.ev, rest);
    if (w) {
    const loadBest = avgOf(best.rs, 'load'), loadRest = avgOf(runs.filter(r => r.tod !== best.k), 'load');
    const harder = num(loadBest) && num(loadRest) && loadBest > loadRest * 1.15;
    cards.push(card('Time of day', w?.clear ? 'link' : 'low', w?.clear ? 'clear difference' : 'no clear difference',
      w?.clear ? `${best.name} runs go best: ${pctF(w.d)} efficiency` : `${best.name} runs edge ahead, within the noise`,
      `${best.name} runs (${best.span}) were ${Math.abs(w.d).toFixed(1)}% ${w.d >= 0 ? 'more' : 'less'} efficient than your runs at other times, each against your own last 6 weeks. 95% interval ${pctF(w.lo)} to ${pctF(w.hi)}.${harder ? ` They also carry more training load (${Math.round(loadBest)} against ${Math.round(loadRest)}), so harder sessions, not the clock alone, may explain part of it.` : ''}`,
      `${best.ev.length} ${best.name.toLowerCase()} runs against ${rest.length} others`));
    }
  }

  // Late runs and the night after, against nights after a day without a run.
  const sleep = (D.sleep || []).map(r => ({ ...r, d: dayIso(r.d) })), byDay = new Map(sleep.map(r => [r.d, r]));
  const restNights = sleep.filter(r => { const prev = byDay.get(iso(new Date(t(r.d) - DAY))); return prev && prev.runs === 0 && num(r.h); });
  const restH = restNights.map(r => r.h), restHrv = restNights.filter(r => num(r.hrv)).map(r => r.hrv);
  // One row per run day: its last run, the one closest to bedtime.
  const lastOfDay = [...runs.reduce((m, r) => m.set(r.d, r), new Map()).values()].filter(r => num(r.to_bed) && r.to_bed > -2 && num(r.next_h));
  const gaps = BED_GAPS.map(([k, name, f]) => { const rs = lastOfDay.filter(r => f(r.to_bed)); return { k, name, rs, h: rs.map(r => r.next_h), hrv: rs.filter(r => num(r.next_hrv)).map(r => r.next_hrv) }; });
  const late = gaps[0], wl = welch(late.h, restH), wlh = welch(late.hrv, restHrv);
  if (wl) {
    const hurt = (wl.clear && wl.d < 0) || (wlh?.clear && wlh.d < 0);
    cards.push(card('Late runs and sleep', hurt ? 'warn' : wl.clear || wlh?.clear ? 'link' : 'low', hurt ? 'costs sleep' : wl.clear || wlh?.clear ? 'clear difference' : 'no clear cost',
      hurt ? `Runs ending under 3 h before bed cost ${wl.d < 0 ? `${Math.round(Math.abs(wl.d) * 60)} min of sleep` : 'HRV'}` : 'Late runs do not cost you sleep, so far',
      `After runs ending under 3 hours before bedtime you slept ${Math.round(Math.abs(wl.d) * 60)} min ${wl.d >= 0 ? 'more' : 'less'} than after a day without a run (95% interval ${signed(wl.lo * 60, 0)} to ${signed(wl.hi * 60, 0)} min)${wlh ? `, and overnight HRV was ${Math.abs(wlh.d).toFixed(1)} ms ${wlh.d >= 0 ? 'higher' : 'lower'} (${signed(wlh.lo, 1)} to ${signed(wlh.hi, 1)} ms)` : ''}.`,
      `${late.h.length} late-run nights against ${restH.length} nights after a day without a run`));
  } else cards.push(card('Late runs and sleep', 'low', 'too little data', 'Not enough late runs yet', `Needs three runs that ended under 3 hours before bed, and three nights after a day without a run; there are ${late.h.length} and ${restH.length}.`, `${lastOfDay.length} run days with the night after`));
  $('timefind').innerHTML = cards.join('');

  // Hours before bed against the night's sleep, with the rest-day nights as the reference level.
  const restMean = sMean(restH);
  multiScatter('ch-bedgap', [{ name: 'Run days', color: 'c5', pts: lastOfDay.map(r => ({ x: r.to_bed, y: r.next_h, tv: `${r.next_h.toFixed(1)} h asleep`, tl: `${fmtDate(r.d)} · run started ${hhmm(r.start_h)}, ended ${r.to_bed.toFixed(1)} h before bed${num(r.next_hrv) ? ` · HRV ${r.next_hrv}` : ''}` })) }],
    { xLabel: 'Hours from the end of the run to bedtime', fmtX: v => `${v} h`, fmtY: (v, axis) => axis ? `${v} h` : `${v.toFixed(1)} h`, W: 480, hline: num(restMean) ? { y: restMean, label: `No run that day: ${restMean.toFixed(1)} h` } : null });
  ciBars('ch-bedgrp', [...gaps.map((g, i) => ({ name: g.name, unit: 'nights', ...meanCi(g.hrv), color: i === 0 ? 'c5' : 'c1' })), { name: 'No run that day', unit: 'nights', ...meanCi(restHrv), color: 'muted' }], { fmt: v => `${Math.round(v)} ms`, levels: true, W: wideW() });
}
