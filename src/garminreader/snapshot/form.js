// Form tab: running dynamics per run (marts.fct_running_form). The latest run against the last four
// weeks and Garmin's ranges, a coach's read on what the numbers mean (cadence and the knee, ground
// contact, bounce, left/right balance), and a trend chart per metric. Runs measured by a chest strap
// (HRM 600, HRM-Pro) carry ground contact balance, and their oscillation and contact time read
// differently from the wrist's estimate, so the baseline compares like with like and the charts mark
// the first chest strap run. renderPage() calls renderForm().

// Garmin's colour ranges for each metric, from its population of runners: the band limits, best
// band first, and whether lower is better. Labels say where a value sits among runners.
const FORM_BANDS = {
  cadence: { cuts: [183, 174, 164, 153], higher: true },
  gct: { cuts: [208, 241, 273, 306], higher: false },
  vo: { cuts: [6.4, 8.2, 9.8, 11.6], higher: false },
  vr: { cuts: [6.1, 7.5, 8.7, 10.2], higher: false },
};
const FORM_LEVELS = [['top 5%', 'good'], ['top 30%', 'good'], ['middle', ''], ['bottom 30%', 'warn'], ['bottom 5%', 'crit']];
const FORM_METRICS = [
  { key: 'cadence', label: 'Cadence', unit: 'spm', fmt: v => v.toFixed(0), color: 'c1', range: 'Garmin: 164–173 spm is the middle of runners, 174 and up the top 30%.' },
  { key: 'stride', label: 'Stride length', unit: 'm', fmt: v => v.toFixed(2), color: 'c2', range: 'Follows pace: longer when you run faster. Watch it at the same pace.' },
  { key: 'gct', label: 'Ground contact', unit: 'ms', fmt: v => v.toFixed(0), color: 'c5', range: 'Garmin: 241–272 ms is the middle, under 241 the top 30%.' },
  { key: 'balance', label: 'Left/right balance', unit: '% left', fmt: v => v.toFixed(1), color: 'c3', range: '50% is even; within 49.2–50.8% counts as balanced. HRM 600 only.' },
  { key: 'vo', label: 'Vertical oscillation', unit: 'cm', fmt: v => v.toFixed(1), color: 'c6', range: 'Garmin: 8.2–9.7 cm is the middle. Chest and wrist read differently.' },
  { key: 'vr', label: 'Vertical ratio', unit: '%', fmt: v => v.toFixed(1), color: 'c4', range: 'Bounce per metre of stride. Garmin: 7.5–8.6% is the middle, lower is more efficient.' },
];

// Where a value sits in Garmin's ranges: [label, pill class], or null for a metric without bands.
function formLevel(key, v) {
  const b = FORM_BANDS[key];
  if (!b || !num(v)) return null;
  const i = b.cuts.findIndex(c => b.higher ? v >= c : v < c);
  return FORM_LEVELS[i < 0 ? 4 : i];
}
// Balance: how far the left share sits from an even 50%.
function balanceLevel(v) {
  if (!num(v)) return null;
  const off = Math.abs(v - 50);
  return off <= 0.8 ? ['balanced', 'good'] : off <= 2.2 ? ['slight imbalance', 'warn'] : ['imbalanced', 'crit'];
}

function renderForm(D) {
  const rows = (D.form || []).filter(r => num(r.cadence) && r.cadence > 0);
  const empty = msg => { $('formtiles').innerHTML = `<p class="cap">${msg}</p>`; for (const id of ['formsrc', 'formnotes', 'formcharts']) $(id).innerHTML = ''; };
  if (!rows.length) { empty('No runs with running dynamics yet. Run with the HRM 600 and the next refresh fills this tab.'); return; }

  const last = rows[rows.length - 1], today = iso(new Date());
  const since = shiftIso(today, -28);
  const chestRuns = rows.filter(r => r.chest), firstChest = chestRuns[0];
  // The baseline: the last four weeks of runs from the same sensor as the latest run, so a chest
  // strap reading is never judged against the wrist's estimates.
  const recent = rows.filter(r => r.activity_date.slice(0, 10) >= since);
  const same = recent.filter(r => !!r.chest === !!last.chest);
  const base = same.length ? same : [last];
  const baseLabel = `${base.length === 1 ? 'latest run' : `${base.length} runs`}${last.chest ? ', chest strap' : ''}`;
  const med = key => median(base.map(r => r[key]));

  $('formsrc').innerHTML = `<p class="cap">${firstChest
    ? `Measured by your chest strap since ${fmtDate(firstChest.activity_date)} (${chestRuns.length} run${chestRuns.length === 1 ? '' : 's'}); runs before that were estimated at the wrist, and ground contact and vertical oscillation read differently between the two, so the figures below compare chest strap runs only.${base.length < 3 ? ' With so few of them yet, the read firms up over the next runs.' : ''}`
    : 'These are estimated at the wrist. Wear the HRM 600 on your runs: it measures at the chest and adds left/right balance.'}</p>`;

  // Tiles: the latest run, its place in Garmin's ranges, and the four-week median.
  const tile = m => {
    const v = last[m.key], lv = m.key === 'balance' ? balanceLevel(v) : formLevel(m.key, v), mv = med(m.key);
    return `<div class="tile"><span class="eyebrow">${m.label}</span><span class="v">${num(v) ? m.fmt(v) : '–'}<small>${m.unit}</small></span>` +
      `<span class="s">${lv ? `<span class="pill ${lv[1]}">${lv[0]}</span> ` : ''}${num(mv) && base.length > 1 ? `4 weeks: ${m.fmt(mv)}` : !num(v) && m.key === 'balance' ? 'needs the HRM 600' : ''}</span></div>`;
  };
  const power = num(last.power) ? `<div class="tile"><span class="eyebrow">Power</span><span class="v">${Math.round(last.power)}<small>W</small></span><span class="s">${[num(D.status?.weight_kg) && `${(last.power / D.status.weight_kg).toFixed(1)} W/kg`, base.length > 1 && `4 weeks: ${Math.round(med('power') || 0)} W`].filter(Boolean).join(' · ')}</span></div>` : '';
  $('formtiles').innerHTML = `<p class="cap">Latest run: ${esc(last.activity_name)}, ${fmtDate(last.activity_date)}${num(last.km) ? `, ${last.km.toFixed(1)} km` : ''}${num(last.pace) ? ` at ${pace(last.pace)} /km` : ''}${last.chest ? ' · chest strap' : ' · wrist'}</p>` +
    `<div class="tiles">${FORM_METRICS.map(tile).join('')}${power}</div>`;

  // The coach's read, on the four-week medians.
  const notes = [];
  const card = (topic, status, label, verdict, body) => `<div class="card ${status}"><div class="head"><span class="eyebrow">${topic}</span><span class="pill ${status}">${label}</span></div><h3>${verdict}</h3><p>${body}</p></div>`;
  const knee = typeof kneeOn === 'function' && kneeOn(today);
  const cad = med('cadence'), gct = med('gct'), vr = med('vr'), vo = med('vo');
  if (num(cad)) {
    const target = Math.round(cad * 1.05);
    notes.push(cad < 170
      ? card('Cadence', 'warn', 'low', `${Math.round(cad)} steps a minute: room to quicken`, `Raising cadence 5 to 10% at the same pace shortens the stride and lands the foot closer under you, which measurably lowers the load on the knee and hip${knee ? ': the most direct lever on your runner\'s knee' : ''}. Aim for about ${target} spm on easy runs: a metronome or the watch's cadence alert helps, and give it two to three weeks to feel normal.`)
      : card('Cadence', 'good', 'fine', `${Math.round(cad)} steps a minute`, `A cadence that keeps the stride compact and the knee load moderate.${knee ? ' Keep it there while the knee recovers; a few more steps a minute on easy runs does no harm.' : ''}`));
  }
  if (num(gct)) {
    notes.push(gct >= 273
      ? card('Ground contact', 'warn', 'long', `${Math.round(gct)} ms on the ground per step`, 'Long contact usually goes with a low cadence and a foot landing ahead of the body. Quicker, lighter steps shorten it; short strides and hill sprints build the springiness.')
      : card('Ground contact', 'good', 'fine', `${Math.round(gct)} ms on the ground per step`, 'Contact time in the normal range for your paces. It drops naturally as you run faster.'));
  }
  if (num(vr)) {
    notes.push(vr >= 8.7
      ? card('Bounce', 'warn', 'bouncy', `${vr.toFixed(1)}% vertical ratio`, `${num(vo) ? `You move ${vo.toFixed(1)} cm up and down per step: ` : ''}more of your energy goes up instead of forward. Run tall with a slight forward lean from the ankles and quicker steps; the ratio drops as the stride stays flat.`)
      : card('Bounce', 'good', 'efficient', `${vr.toFixed(1)}% vertical ratio`, `${num(vo) ? `${vo.toFixed(1)} cm up and down per step, ` : ''}little bounce for the length of your stride: efficient.`));
  }
  const bal = median(chestRuns.filter(r => r.activity_date.slice(0, 10) >= since).map(r => r.balance));
  if (!num(bal)) notes.push(card('Left/right balance', '', 'no data', 'Needs the HRM 600', 'Balance only comes from the chest strap. Wear it on your runs and the next refresh shows whether one leg stays on the ground longer.'));
  else {
    const off = Math.abs(bal - 50), side = bal > 50 ? 'left' : 'right', other = bal > 50 ? 'right' : 'left';
    notes.push(off <= 0.8
      ? card('Left/right balance', 'good', 'balanced', `${bal.toFixed(1)}% left, ${(100 - bal).toFixed(1)}% right`, `Both legs share the work evenly.${knee ? ' Good sign for the knee: you are not protecting one side.' : ''}`)
      : card('Left/right balance', off <= 2.2 ? 'warn' : 'crit', off <= 2.2 ? 'slight' : 'imbalanced', `Your ${side} foot stays on the ground longer`, `${bal.toFixed(1)}% left against ${(100 - bal).toFixed(1)}% right. A leg that hurts or is weaker usually gets the shorter contact, so this can mean you are sparing your ${other} leg${knee ? ', for example around a sore knee' : ''}. Single-leg strength work (step-downs, single-leg bridges) evens it out; if it grows, have a physio look.`));
  }
  $('formnotes').innerHTML = notes.join('');
  $('formbase').textContent = `Last 4 weeks · ${baseLabel}`;

  // Trends: one chart per metric over the period, the first chest strap run and the events marked.
  const x0 = t(rows[0].activity_date), x1 = t(last.activity_date);
  const marks = (firstChest ? [{ s: t(firstChest.activity_date), e: t(firstChest.activity_date), color: 'c5', value: 'HRM 600', label: `${fmtDate(firstChest.activity_date)} · first run with the chest strap` }] : [])
    .concat(chartEvents(D, x0, x1, { races: false }));
  $('formcharts').innerHTML = FORM_METRICS.map(m => `<div class="chart"><h3>${m.label}</h3><div id="ch-f-${m.key}"></div><div class="cap">${m.range}</div></div>`).join('');
  for (const m of FORM_METRICS) {
    const pts = rows.filter(r => num(r[m.key])).map(r => [t(r.activity_date), r[m.key]]);
    if (pts.length === 1) { $(`ch-f-${m.key}`).innerHTML = `<p class="cap">One run so far: ${m.fmt(pts[0][1])} ${m.unit} on ${fmtDate(iso(new Date(pts[0][0])))}. The line starts with the next one.</p>`; continue; }
    lineChart(`ch-f-${m.key}`, pts, { fmt: (v, axis) => axis ? m.fmt(v) : `${m.fmt(v)} ${m.unit}`, label: m.label, color: m.color, events: marks.filter(e => e.s >= (pts[0]?.[0] ?? x0)) });
  }
}

bindTips($('panel-form'));
