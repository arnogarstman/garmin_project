// History tab: what the last months of training add up to. One period filter (3, 6 or 12 months)
// scopes every view below it: summary tiles against the period before, volume per month or week,
// a heatmap of daily training load, pace per run with its trend, resting heart rate, HRV and weight,
// when you train, the mix of run distances and activities, records, the activity log (the table
// view of everything charted) and the calendar of runs and weigh-ins. Every chart carries a hover
// and focus tooltip; values also sit in the tables, so the tooltip never gates a number. renderPage() calls renderHistory().
// A period is whole calendar months: this month and the ones before it, so 3 months never shows a
// day of a fourth.
const HIST_KEY = 'garminreader.historyMonths';
const HIST_PERIODS = [[3, '3 months'], [6, '6 months'], [12, '12 months']];
let histMonths = 12, histType = 'all', histAll = false;
try { histMonths = Number(localStorage.getItem(HIST_KEY)) || 12; } catch { histMonths = 12; }
if (!HIST_PERIODS.some(([m]) => m === histMonths)) histMonths = 12;

const isRun = type => /run/i.test(type || '');
const sumBy = (rows, k) => rows.reduce((s, r) => s + (num(r[k]) ? r[k] : 0), 0);
const dayIso = d => d.slice(0, 10);
const addDays = (date, n) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
const mondayOf = date => addDays(date, -((date.getDay() + 6) % 7));
const kmFmt = v => `${v >= 100 ? Math.round(v).toLocaleString('en-GB') : v.toFixed(1)} km`;
const hoursFmt = min => min >= 600 ? `${Math.round(min / 60)} h` : hms(min * 60).replace(/:\d{2}$/, '') + ' h';
const pct = (a, b) => num(a) && num(b) && b ? (a / b - 1) * 100 : null;
// A value bar's top: square at the baseline, 4px rounded data end.
const colPath = (x, y, w, h) => { const r = Math.min(4, w / 2, h); return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`; };
// Drawing width of the full-width charts: narrower on a phone, so their text stays readable.
const wideW = () => innerWidth < 700 ? 520 : 1000;
const tipAttr = (value, label) => ` data-tv="${esc(value)}" data-tl="${esc(label)}"`;

// One tooltip for the whole page: value strong, label after, both as text (never as HTML).
const histTip = (() => {
  const el = document.createElement('div');
  el.className = 'tip';
  el.setAttribute('role', 'tooltip');
  el.hidden = true;
  el.append(document.createElement('b'), document.createElement('span'));
  document.body.append(el);
  return el;
})();
function showTip(mark, x, y) {
  histTip.firstChild.textContent = mark.dataset.tv;
  histTip.lastChild.textContent = mark.dataset.tl || '';
  histTip.hidden = false;
  const w = histTip.offsetWidth, h = histTip.offsetHeight;
  histTip.style.left = `${Math.max(8, Math.min(innerWidth - w - 8, x - w / 2))}px`;
  histTip.style.top = `${y - h - 12 < 8 ? y + 16 : y - h - 12}px`;
}
function bindTips(root) {
  root.addEventListener('pointermove', e => {
    const m = e.target.closest('[data-tv]');
    if (m && root.contains(m)) showTip(m, e.clientX, e.clientY); else histTip.hidden = true;
  });
  root.addEventListener('pointerleave', () => { histTip.hidden = true; });
  root.addEventListener('focusin', e => {
    const m = e.target.closest('[data-tv]');
    if (m) { const r = m.getBoundingClientRect(); showTip(m, r.left + r.width / 2, r.top); }
  });
  root.addEventListener('focusout', () => { histTip.hidden = true; });
}

// A line chart with a crosshair: the pointer snaps to the nearest point and shows its value, and
// the events (events.js) near it. `events` are drawn under the line.
function lineChart(id, pts, { fmt, label, color = 'c1', W = 360, H = 190, events = [] }) {
  const el = $(id), P = pts.filter(p => num(p[1]));
  if (P.length < 2) { el.innerHTML = '<p class="cap">Not enough readings in this period.</p>'; return; }
  const ys = P.map(p => p[1]), lo = Math.min(...ys), hi = Math.max(...ys), pad = (hi - lo) * 0.15 || 1;
  const f = frame({ x0: P[0][0], x1: P[P.length - 1][0], yTicks: niceTicks(lo - pad, hi + pad, 3), fmtY: v => fmt(v, true), W, H });
  const last = P[P.length - 1];
  el.innerHTML = f.s + eventMarks(f, events) + `<path d="${path(P, f.X, f.Y)}" fill="none" stroke="${css(color)}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>` +
    `<circle cx="${f.X(last[0])}" cy="${f.Y(last[1])}" r="4" fill="${css(color)}" stroke="${css('bg')}" stroke-width="2"/>` +
    `<text x="${f.X(last[0]) - 8}" y="${f.Y(last[1]) - 10}" text-anchor="end" style="fill:${css('ink')};font-weight:500;paint-order:stroke;stroke:${css('bg')};stroke-width:4px;stroke-linejoin:round">${fmt(last[1])}</text>` +
    `<line class="xh" y1="${f.T}" y2="${f.T + f.ih}" stroke="${css('muted')}" stroke-width="1" visibility="hidden"/>` +
    `<circle class="xd" r="4" fill="${css(color)}" stroke="${css('bg')}" stroke-width="2" visibility="hidden"/>` +
    `<rect class="hit" x="${f.L}" y="${f.T}" width="${f.W - f.L - f.R}" height="${f.ih}" fill="transparent" tabindex="0" aria-label="${esc(label)}: ${P.length} readings, latest ${fmt(last[1])}"/></svg>`;
  const svg = el.querySelector('svg'), xh = svg.querySelector('.xh'), xd = svg.querySelector('.xd'), hit = svg.querySelector('.hit');
  const at = clientX => {
    const r = svg.getBoundingClientRect(), x = (clientX - r.left) / r.width * f.W;
    let best = P[0];
    for (const p of P) if (Math.abs(f.X(p[0]) - x) < Math.abs(f.X(best[0]) - x)) best = p;
    return best;
  };
  const show = (p, clientY) => {
    const px = f.X(p[0]), py = f.Y(p[1]), r = svg.getBoundingClientRect();
    xh.setAttribute('x1', px); xh.setAttribute('x2', px); xd.setAttribute('cx', px); xd.setAttribute('cy', py);
    xh.setAttribute('visibility', 'visible'); xd.setAttribute('visibility', 'visible');
    const near = eventsNear(p[0], 4);
    hit.dataset.tv = fmt(p[1]); hit.dataset.tl = `${label} · ${fmtDate(iso(new Date(p[0])))}${near.length ? ` · ${near.join('; ')}` : ''}`;
    showTip(hit, r.left + px / f.W * r.width, clientY ?? r.top + py / H * r.height);
  };
  const hide = () => { xh.setAttribute('visibility', 'hidden'); xd.setAttribute('visibility', 'hidden'); histTip.hidden = true; };
  hit.addEventListener('pointermove', e => { e.stopPropagation(); show(at(e.clientX), e.clientY); });
  hit.addEventListener('pointerleave', hide);
  hit.addEventListener('focus', () => show(last));
  hit.addEventListener('blur', hide);
  hit.addEventListener('keydown', e => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const i = Math.max(0, Math.min(P.length - 1, P.findIndex(p => p[0] === Number(hit.dataset.at ?? last[0])) + step));
    hit.dataset.at = P[i][0];
    show(P[i]);
  });
}

// Run calendar: one continuous grid of weeks, Monday to Sunday, newest week on top, so the
// last day of a month and the first of the next sit side by side in the week they share. Each
// month is headed above its own days in its topmost week, alternates in tint and marks its 1st.
// Each run is a bubble whose area is proportional to its distance (diameter grows with the square
// root), on one fixed scale. Only the days of the History period show, start to last, and a
// month's heading totals only those days.
function renderCalendar(D, start, last) {
  const from = iso(start), today = iso(last), inPeriod = k => k >= from && k <= today;
  const runs = (D.runs || []).filter(r => inPeriod(r.activity_date.slice(0, 10))), byDay = new Map(), totals = new Map();
  for (const r of runs) {
    const k = r.activity_date.slice(0, 10), m = k.slice(0, 7);
    if (!byDay.has(k)) byDay.set(k, []);
    byDay.get(k).push(r);
    const tot = totals.get(m) || { n: 0, km: 0 };
    totals.set(m, { n: tot.n + 1, km: tot.km + (r.km || 0) });
  }
  const bubble = km => `<span class="bub" style="--r:${Math.sqrt(Math.max(km || 0, 0.25)).toFixed(3)}"></span>`;
  // Weigh-ins: each day's weight with its change since the previous weigh-in, and each month's
  // change from its first to its last weigh-in. A change toward the weight goal (meals.js) is
  // marked good, away from it marked warn; without a goal the change stays neutral.
  const weights = (D.body || []).filter(r => num(r.weight)).map(r => [r.d.slice(0, 10), r.weight]).sort();
  const wByDay = new Map(), wMonth = new Map();
  weights.forEach(([k, w], i) => {
    if (!inPeriod(k)) return;
    wByDay.set(k, { w, delta: i ? w - weights[i - 1][1] : null });
    const m = wMonth.get(k.slice(0, 7)) || { first: w, last: w };
    m.last = w; wMonth.set(k.slice(0, 7), m);
  });
  const goalDir = typeof weightGoal !== 'undefined' && weightGoal && weights.length ? Math.sign(weightGoal.target_kg - weights[weights.length - 1][1]) : 0;
  const tone = d => !goalDir || Math.abs(d) < 0.05 ? 'flat' : Math.sign(d) === goalDir ? 'good' : 'warn';
  const signedKg = d => `${d > 0 ? '+' : d < 0 ? '−' : '±'}${Math.abs(d).toFixed(1)}`;
  const monday = d => new Date(d.getFullYear(), d.getMonth(), d.getDate() - (d.getDay() + 6) % 7);
  $('calkeys').innerHTML = (runs.length ? 'Bubble area is proportional to distance:' + [5, 10, 21.1].map(km => `<span>${bubble(km)}${km} km</span>`).join('') : '') +
    (weights.length ? `<span class="wkey"><span class="wt">80.4<i class="${goalDir ? 'good' : 'flat'}">−0.3</i></span>weight and change since the last weigh-in${goalDir ? `, green toward your ${weightGoal.target_kg.toFixed(1)} kg goal` : ''}</span>` : '');
  const headed = new Set();
  let html = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => `<span class="dow">${d}</span>`).join('');
  for (let w = monday(last); w >= monday(start); w = new Date(w.getFullYear(), w.getMonth(), w.getDate() - 7)) {
    const week = [...Array(7)].map((_, i) => new Date(w.getFullYear(), w.getMonth(), w.getDate() + i));
    // Head each month above its topmost week, spanning only its own days in that week, so the
    // heading and its rule mark exactly where the month starts.
    const segs = [];
    week.forEach((d, i) => {
      if (d < start || d > last) return;
      const m = iso(d).slice(0, 7), seg = segs[segs.length - 1];
      if (seg && seg.m === m) seg.b = i; else segs.push({ m, a: i, b: i });
    });
    const heads = segs.filter(g => !headed.has(g.m));
    if (heads.length) {
      let col = 0;
      for (const { m, a, b } of heads) {
        headed.add(m);
        if (a > col) html += `<span class="mgap" style="grid-column:span ${a - col}"></span>`;
        const tot = totals.get(m) || { n: 0, km: 0 }, [y, mo] = m.split('-').map(Number);
        const wm = wMonth.get(m), wmTxt = wm && wm.last !== wm.first ? ` · <i class="${tone(wm.last - wm.first)}">${signedKg(wm.last - wm.first)} kg</i>` : '';
        html += `<div class="mhead" style="grid-column:${a + 1} / span ${b - a + 1}"><h3>${MON[mo - 1]} ${y}</h3><span class="tot">${tot.n} run${tot.n === 1 ? '' : 's'} · ${tot.km.toFixed(1)} km${wmTxt}</span></div>`;
        col = b + 1;
      }
      if (col < 7) html += `<span class="mgap" style="grid-column:span ${7 - col}"></span>`;
    }
    for (const d of week) {
      if (d < start || d > last) { html += '<span class="day pad"></span>'; continue; }
      const key = iso(d), rs = byDay.get(key) || [];
      const wd = wByDay.get(key);
      const tip = (wd ? [`Weight ${wd.w.toFixed(1)} kg${num(wd.delta) ? ` (${signedKg(wd.delta)} kg since the last weigh-in)` : ''}`] : []).concat(rs.map(r => `${r.activity_name}: ${num(r.km) ? r.km.toFixed(1) + ' km' : ''}${num(r.min) ? ' in ' + hms(r.min * 60) : ''}${num(r.pace) ? ', ' + pace(r.pace) + ' /km' : ''}`)).join('\n');
      const cls = ['day', d.getMonth() % 2 ? 'alt' : '', d.getDate() === 1 ? 'first' : '', key === today ? 'today' : ''].filter(Boolean).join(' ');
      html += `<div class="${cls}"${tip ? ` title="${esc(tip)}"` : ''}><span class="dn">${d.getDate() === 1 ? `1 ${MON[d.getMonth()]}` : d.getDate()}</span>` +
        (rs.length ? '<div class="runs">' + rs.map(r => `<div class="run">${bubble(r.km)}<span class="km">${num(r.km) ? r.km.toFixed(1) : '–'}<small>km</small></span><span class="nm">${esc(r.activity_name)}</span></div>`).join('') + '</div>' : '') +
        (wd ? `<span class="wt">${wd.w.toFixed(1)}${num(wd.delta) ? `<i class="${tone(wd.delta)}">${signedKg(wd.delta)}</i>` : ''}</span>` : '') + '</div>';
    }
  }
  $('cal').innerHTML = `<div class="mgrid">${html}</div>`;
}

function renderHistory(D) {
  const today = new Date(), todayIso = iso(today), start = new Date(today.getFullYear(), today.getMonth() - histMonths + 1, 1), startIso = iso(start);
  // Days in the period so far; the period before is as many days, so the comparison is like for like.
  const histDays = Math.round((t(todayIso) - t(startIso)) / DAY) + 1;
  const all = (D.history || []).map(r => ({ ...r, d: dayIso(r.activity_date) }));
  const inP = (rows, key = 'd') => rows.filter(r => r[key] >= startIso && r[key] <= todayIso);
  const acts = inP(all), runs = acts.filter(r => isRun(r.type) && num(r.km) && r.km > 0);
  const prevStart = iso(addDays(start, -histDays)), prev = all.filter(r => r.d >= prevStart && r.d < startIso);
  const prevRuns = prev.filter(r => isRun(r.type) && num(r.km) && r.km > 0);
  const hasPrev = all.length && all[0].d <= prevStart;
  const periodLabel = `${histDays} days`;

  $('histfilter').innerHTML = `<span class="eyebrow">Period</span><div class="seg" role="group" aria-label="Period">${
    HIST_PERIODS.map(([m, l]) => `<button type="button" data-months="${m}" aria-pressed="${m === histMonths}">${l}</button>`).join('')
  }</div><span class="cap">${fmtDate(startIso)}${start.getFullYear() !== today.getFullYear() ? ` ${start.getFullYear()}` : ''} to ${fmtDate(todayIso)} ${today.getFullYear()}${hasPrev ? `, compared with the ${periodLabel} before` : ''}</span>`;
  for (const b of $('histfilter').querySelectorAll('button')) b.onclick = () => {
    histMonths = Number(b.dataset.months);
    try { localStorage.setItem(HIST_KEY, histMonths); } catch { /* storage blocked: the choice lasts this visit */ }
    renderHistory(D);
  };

  renderCalendar(D, start, today);

  if (!acts.length) {
    for (const id of ['histkpis', 'ch-vol', 'ch-heat', 'ch-pace', 'ch-rhr', 'ch-hrv', 'ch-weight', 'ch-when', 'ch-dist', 'ch-mix', 'records', 'histlog']) $(id).innerHTML = '';
    $('histkpis').innerHTML = '<p class="cap">No activities in this period.</p>';
    return;
  }

  // Summary tiles, each against the period before when the data reaches back that far.
  {
    const weeks = histDays / 7, km = sumBy(runs, 'km'), min = sumBy(acts, 'min');
    const longest = runs.reduce((a, r) => r.km > (a?.km ?? 0) ? r : a, null);
    const delta = (now, before, unit = '%') => {
      if (!hasPrev) return '';
      const d = pct(now, before);
      return d === null ? '' : `<span class="delta">${d >= 0 ? '+' : '−'}${Math.abs(d).toFixed(0)}${unit} vs before</span>`;
    };
    const tile = (k, v, s) => `<div class="tile"><span class="eyebrow">${k}</span><span class="v">${v}</span><span class="s">${s}</span></div>`;
    $('histkpis').innerHTML = `<div class="tiles">${[
      tile('Running', `${Math.round(km).toLocaleString('en-GB')}<small>km</small>`, delta(km, sumBy(prevRuns, 'km')) || `${runs.length} runs`),
      tile('Runs', runs.length, delta(runs.length, prevRuns.length) || `${(runs.length / weeks).toFixed(1)} a week`),
      tile('Per week', `${(km / weeks).toFixed(1)}<small>km</small>`, `${(runs.length / weeks).toFixed(1)} runs a week`),
      tile('Time training', hoursFmt(min), delta(min, sumBy(prev, 'min')) || `${acts.length} activities`),
      tile('Longest run', longest ? `${longest.km.toFixed(1)}<small>km</small>` : '–', longest ? `${fmtDate(longest.d)} · ${esc(longest.name)}` : ''),
    ].join('')}</div>`;
  }

  // Volume: running km per month (12 months) or per week (shorter periods); the current, unfinished
  // one faded. Labels on the largest and the latest complete bar; every bar in the tooltip and table.
  {
    const weekly = histMonths <= 6;
    const key = d => weekly ? iso(mondayOf(new Date(t(d)))) : d.slice(0, 7);
    const buckets = [];
    for (let c = weekly ? mondayOf(start) : new Date(start.getFullYear(), start.getMonth(), 1); c <= today; c = weekly ? addDays(c, 7) : new Date(c.getFullYear(), c.getMonth() + 1, 1)) {
      buckets.push({ k: weekly ? iso(c) : iso(c).slice(0, 7), date: c, km: 0, n: 0, min: 0 });
    }
    const byKey = new Map(buckets.map(b => [b.k, b]));
    for (const r of runs) { const b = byKey.get(key(r.d)); if (b) { b.km += r.km; b.n++; b.min += r.min || 0; } }
    const name = b => weekly ? `Week of ${fmtDate(iso(b.date))}` : `${MON[b.date.getMonth()]} ${b.date.getFullYear()}`;
    const W = wideW(), H = W < 1000 ? 200 : 220, L = 44, R = 8, T = 18, B = 26, iw = W - L - R, ih = H - T - B;
    const ticks = niceTicks(0, Math.max(10, ...buckets.map(b => b.km)), 4), top = ticks[ticks.length - 1];
    const slot = iw / buckets.length, bw = Math.min(24, slot * 0.62);
    const Y = v => T + ih - v / top * ih;
    const maxB = buckets.reduce((a, b) => b.km > a.km ? b : a, buckets[0]), lastFull = buckets[buckets.length - 2];
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Running km per ${weekly ? 'week' : 'month'}">`;
    for (const v of ticks) s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${css('grid')}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${v}</text>`;
    buckets.forEach((b, i) => {
      const x = L + i * slot + (slot - bw) / 2, y = Y(b.km), partial = i === buckets.length - 1;
      if (b.km > 0) s += `<path d="${colPath(x, y, bw, Y(0) - y)}" fill="${css('c1')}" opacity="${partial ? 0.4 : 0.9}"/>`;
      s += `<rect class="mark" x="${L + i * slot}" y="${T}" width="${slot}" height="${ih}" fill="transparent" tabindex="0"${tipAttr(kmFmt(b.km), `${name(b)}${partial ? ' (so far)' : ''} · ${b.n} run${b.n === 1 ? '' : 's'} · ${hoursFmt(b.min)}`)}/>`;
      if ((b === maxB || b === lastFull) && b.km > 0) s += `<text x="${x + bw / 2}" y="${y - 6}" text-anchor="middle" style="fill:${css('ink')};font-weight:500">${Math.round(b.km)}</text>`;
      const showLabel = weekly ? b.date.getDate() <= 7 : (buckets.length <= 13 || i % 2 === 0);
      if (showLabel) s += `<text x="${L + i * slot + slot / 2}" y="${H - 8}" text-anchor="middle">${MON[b.date.getMonth()]}</text>`;
    });
    $('ch-vol').innerHTML = s + '</svg>';
    $('vol-title').textContent = `Running per ${weekly ? 'week' : 'month'}`;
    const full = buckets.slice(0, -1).filter(b => b.km > 0);
    $('cap-vol').textContent = full.length
      ? `Biggest ${weekly ? 'week' : 'month'}: ${name(maxB)} with ${kmFmt(maxB.km)}. Average ${kmFmt(sumBy(full, 'km') / full.length)} per active ${weekly ? 'week' : 'month'}. The faded bar is the current, unfinished one.`
      : '';
    $('tbl-vol').innerHTML = `<table><thead><tr><th>${weekly ? 'Week' : 'Month'}</th><th class="n">Km</th><th class="n">Runs</th><th class="n">Time</th></tr></thead><tbody>${
      [...buckets].reverse().map(b => `<tr><td>${name(b)}</td><td class="n">${b.km.toFixed(1)}</td><td class="n">${b.n}</td><td class="n">${hoursFmt(b.min)}</td></tr>`).join('')
    }</tbody></table>`;
  }

  // Heatmap: Garmin's training load per day, all activities, Monday to Sunday down each column.
  // One hue, five steps by quintile of the active days; rest days in the panel tint.
  {
    const byDay = new Map();
    for (const r of acts) {
      const e = byDay.get(r.d) || { load: 0, km: 0, names: [] };
      e.load += r.load || 0; e.km += r.km || 0; e.names.push(lower(r.type));
      byDay.set(r.d, e);
    }
    const loads = [...byDay.values()].map(e => e.load).filter(v => v > 0).sort((a, b) => a - b);
    const q = [0.2, 0.4, 0.6, 0.8].map(p => loads[Math.floor(p * (loads.length - 1))] ?? 0);
    const step = v => v <= 0 ? 0 : 1 + q.filter(x => v > x).length;
    const tint = [null, 22, 42, 62, 82, 100];
    const fill = k => k === 0 ? css('panel') : `color-mix(in srgb, ${css('c1')} ${tint[k]}%, ${css('bg')})`;
    const first = mondayOf(start), weeks = Math.ceil((addDays(today, 1) - first) / (7 * DAY));
    const W = wideW(), L = 34, T = 18, cell = Math.min(24, (W - L - 4) / weeks), gap = Math.max(1.5, cell * 0.14), H = T + 7 * cell + 4;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Training load per day">`;
    ['Mon', 'Wed', 'Fri'].forEach((d, i) => { s += `<text x="${L - 6}" y="${T + (i * 2 + 0.5) * cell + 4}" text-anchor="end">${d}</text>`; });
    let lastMonth = -1;
    for (let w = 0; w < weeks; w++) {
      const monday = addDays(first, w * 7), shown = monday < start ? start : monday;
      if (shown.getMonth() !== lastMonth) { lastMonth = shown.getMonth(); if (w < weeks - 1) s += `<text x="${L + w * cell}" y="${T - 6}">${MON[lastMonth]}</text>`; }
      for (let d = 0; d < 7; d++) {
        const day = addDays(monday, d), k = iso(day);
        if (k < startIso || k > todayIso) continue;
        const e = byDay.get(k), lv = e ? step(e.load) : 0;
        const label = `${DOW[d]} ${fmtDate(k)}${e ? ` · ${[...new Set(e.names)].join(', ')}${e.km ? ` · ${kmFmt(e.km)}` : ''}` : ' · rest'}`;
        s += `<rect class="mark" x="${L + w * cell + gap / 2}" y="${T + d * cell + gap / 2}" width="${cell - gap}" height="${cell - gap}" rx="2" fill="${fill(lv)}"${tipAttr(e ? `${Math.round(e.load)} load` : 'Rest day', label)}/>`;
      }
    }
    $('ch-heat').innerHTML = s + '</svg>';
    const active = byDay.size, restShare = 100 - active / histDays * 100;
    $('heat-legend').innerHTML = `<span>Less</span>${[0, 1, 2, 3, 4, 5].map(k => `<i style="background:${fill(k)}"></i>`).join('')}<span>More training load</span>`;
    $('cap-heat').textContent = `${active} active days, ${Math.round(restShare)}% rest days. Darker is a bigger training load (Garmin's load per activity, summed per day).`;
  }

  // Pace per run over time: faster is higher. Dot area follows distance; the line is the median
  // pace of the runs in a rolling 4 weeks, the trend the dots are noise around.
  {
    const pts = runs.filter(r => num(r.pace) && r.pace > 2.5 && r.pace < 10 && r.km >= 2).map(r => [t(r.d), r.pace, r]);
    if (pts.length < 3) $('ch-pace').innerHTML = '<p class="cap">Needs at least three runs with a pace in this period.</p>';
    else {
      const ps = pts.map(p => p[1]), lo = Math.min(...ps), hi = Math.max(...ps);
      const tk = niceTicks(lo - 0.15, hi + 0.15, 4).reverse();
      // Faster (smaller) pace on top: flip the scale by plotting the negative.
      const f = frame({ x0: t(startIso), x1: t(todayIso), yTicks: tk.map(v => -v).sort((a, b) => a - b), fmtY: v => pace(-v), W: wideW(), H: wideW() < 1000 ? 260 : 300 });
      // Only where the 4 weeks hold at least three runs, so a single run is never called a trend.
      // The window also counts runs from before the period, so the line starts settled.
      const pool = all.filter(r => isRun(r.type) && num(r.pace) && r.pace > 2.5 && r.pace < 10 && r.km >= 2).map(r => [t(r.d), r.pace]);
      // And only once the data covers the whole 4 weeks before a point.
      const covered = pool.length ? pool[0][0] + 28 * DAY : Infinity;
      const trend = pts.filter(([x]) => x >= covered).map(([x]) => [x, pool.filter(([y]) => y > x - 28 * DAY && y <= x).map(p => p[1])]).filter(([, w]) => w.length >= 3).map(([x, w]) => [x, -median(w)]);
      let s = f.s + eventMarks(f, chartEvents(D, t(startIso), t(todayIso)));
      for (const [x, y, r] of pts) {
        const rad = Math.max(4, Math.min(10, 2.2 * Math.sqrt(r.km)));
        s += `<circle cx="${f.X(x)}" cy="${f.Y(-y)}" r="${rad}" fill="${css('c1')}" fill-opacity=".45" stroke="${css('bg')}" stroke-width="2"/>`;
        s += `<circle class="mark" cx="${f.X(x)}" cy="${f.Y(-y)}" r="${Math.max(12, rad + 4)}" fill="transparent" tabindex="0"${tipAttr(`${pace(y)} /km`, `${fmtDate(r.d)} · ${r.name} · ${kmFmt(r.km)}${num(r.avg_hr) ? ` · ${Math.round(r.avg_hr)} bpm` : ''}`)}/>`;
      }
      s += `<path d="${path(trend, f.X, f.Y)}" fill="none" stroke="${css('ink')}" stroke-width="2" stroke-linejoin="round" pointer-events="none"/>`;
      $('ch-pace').innerHTML = s + '</svg>';
      const a = trend.length ? -trend[0][1] : null, b = trend.length ? -trend[trend.length - 1][1] : null, d = (a - b) * 60;
      $('cap-pace').textContent = !trend.length ? 'Too few runs close together for a trend line.' : `Typical pace (4-week median) went from ${pace(a)} to ${pace(b)} /km: ${Math.abs(d) < 3 ? 'about the same' : `${Math.round(Math.abs(d))} s/km ${d > 0 ? 'faster' : 'slower'}`}. Pace mixes easy and hard runs; the trend matters more than any dot.`;
    }
  }

  // Recovery and body: weekly averages, as three small charts (each its own scale, never two axes).
  {
    const weeklyAvg = (rows, k) => {
      const m = new Map();
      for (const r of rows) { if (!num(r[k])) continue; const w = iso(mondayOf(new Date(t(r.d)))); const e = m.get(w) || []; e.push(r[k]); m.set(w, e); }
      return [...m.entries()].sort().map(([w, v]) => [t(w) + 3 * DAY, v.reduce((s, x) => s + x, 0) / v.length]);
    };
    const days = inP(D.daily || []), body = inP((D.body || []).map(r => ({ ...r, d: dayIso(r.d) })));
    // Each chart spans its own points, so it gets the events of its own span.
    const evIn = pts => { const P = pts.filter(q => num(q[1])); return P.length > 1 ? chartEvents(D, P[0][0], P[P.length - 1][0]) : []; };
    const rhr = weeklyAvg(days, 'rhr'), hrv = weeklyAvg(days, 'hrv'), wt = weeklyAvg(body, 'weight');
    lineChart('ch-rhr', rhr, { fmt: (v, axis) => axis ? Math.round(v) : `${v.toFixed(0)} bpm`, label: 'Resting HR, weekly average', color: 'c6', events: evIn(rhr) });
    lineChart('ch-hrv', hrv, { fmt: (v, axis) => axis ? Math.round(v) : `${v.toFixed(0)} ms`, label: 'HRV, weekly average', color: 'c2', events: evIn(hrv) });
    lineChart('ch-weight', wt, { fmt: (v, axis) => axis ? v.toFixed(axis === true && v % 1 ? 1 : 0) : `${v.toFixed(1)} kg`, label: 'Weight, weekly average', color: 'c5', events: evIn(wt) });
    $('evkey-history').innerHTML = eventKey(D, t(startIso), t(todayIso));
  }

  // When you train: weekday by time of day, dot area by the number of activities.
  {
    const SLOTS = [[0, 9, 'Morning', 'before 9', '<9'], [9, 12, 'Late morning', '9 to 12', '9–12'], [12, 15, 'Midday', '12 to 15', '12–15'], [15, 18, 'Afternoon', '15 to 18', '15–18'], [18, 21, 'Evening', '18 to 21', '18–21'], [21, 24, 'Night', 'after 21', '21+']];
    const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
    const grid = DAYS.map(() => SLOTS.map(() => 0));
    for (const r of acts) {
      if (!num(r.hr)) continue;
      grid[(new Date(t(r.d)).getDay() + 6) % 7][SLOTS.findIndex(([a, b]) => r.hr >= a && r.hr < b)]++;
    }
    const max = Math.max(1, ...grid.flat());
    const W = 360, L = 34, T = 28, cw = (W - L) / SLOTS.length, ch = 26, H = T + 7 * ch + 4;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Activities by weekday and time of day">`;
    SLOTS.forEach(([, , , , short], j) => { s += `<text x="${L + j * cw + cw / 2}" y="${T - 12}" text-anchor="middle">${short}</text>`; });
    DAYS.forEach((d, i) => {
      s += `<text x="${L - 8}" y="${T + i * ch + ch / 2 + 4}" text-anchor="end">${d.slice(0, 3)}</text>`;
      SLOTS.forEach(([, , n, span], j) => {
        const c = grid[i][j], cx = L + j * cw + cw / 2, cy = T + i * ch + ch / 2;
        s += `<circle cx="${cx}" cy="${cy}" r="1.5" fill="${css('grid')}"/>`;
        if (c) s += `<circle cx="${cx}" cy="${cy}" r="${(Math.sqrt(c / max) * (ch / 2 - 2)).toFixed(1)}" fill="${css('c1')}" fill-opacity=".85" stroke="${css('bg')}" stroke-width="2"/>`;
        s += `<rect class="mark" x="${L + j * cw}" y="${T + i * ch}" width="${cw}" height="${ch}" fill="transparent"${c ? ' tabindex="0"' : ''}${tipAttr(`${c} activit${c === 1 ? 'y' : 'ies'}`, `${d} ${n.toLowerCase()} (${span})`)}/>`;
      });
    });
    $('ch-when').innerHTML = s + '</svg>';
    const flat = grid.flatMap((row, i) => row.map((c, j) => [c, i, j])).sort((a, b) => b[0] - a[0]);
    const byDayCount = grid.map(r => r.reduce((a, b) => a + b, 0)), busiest = byDayCount.indexOf(Math.max(...byDayCount));
    $('cap-when').textContent = flat[0][0] ? `Most often on ${DAYS[flat[0][1]]} ${SLOTS[flat[0][2]][2].toLowerCase()}s; ${DAYS[busiest]} is your busiest day.` : '';
  }

  // Run distances: how the runs split by length.
  {
    const BINS = [[0, 5, '<5'], [5, 8, '5–8'], [8, 12, '8–12'], [12, 16, '12–16'], [16, 21, '16–21'], [21, 99, '21+']];
    const counts = BINS.map(([a, b]) => runs.filter(r => r.km >= a && r.km < b).length);
    const W = 360, H = 220, L = 30, R = 8, T = 18, B = 26, iw = W - L - R, ih = H - T - B;
    const ticks = niceTicks(0, Math.max(4, ...counts), 3), top = ticks[ticks.length - 1], slot = iw / BINS.length, bw = Math.min(24, slot * 0.6);
    const Y = v => T + ih - v / top * ih;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Runs by distance">`;
    for (const v of ticks) s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${css('grid')}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${v}</text>`;
    BINS.forEach(([, , n], i) => {
      const x = L + i * slot + (slot - bw) / 2, c = counts[i], y = Y(c);
      if (c) s += `<path d="${colPath(x, y, bw, Y(0) - y)}" fill="${css('c1')}" opacity=".9"/><text x="${x + bw / 2}" y="${y - 6}" text-anchor="middle" style="fill:${css('ink')};font-weight:500">${c}</text>`;
      s += `<rect class="mark" x="${L + i * slot}" y="${T}" width="${slot}" height="${ih}" fill="transparent" tabindex="0"${tipAttr(`${c} run${c === 1 ? '' : 's'}`, `${n} km · ${runs.length ? Math.round(c / runs.length * 100) : 0}% of runs`)}/>`;
      s += `<text x="${L + i * slot + slot / 2}" y="${H - 8}" text-anchor="middle">${n}</text>`;
    });
    s += `<text x="${W - R}" y="${T - 6}" text-anchor="end">runs per distance, km</text>`;
    $('ch-dist').innerHTML = s + '</svg>';
    const long = runs.filter(r => r.km >= 16).length;
    $('cap-dist').textContent = runs.length ? `${long} long run${long === 1 ? '' : 's'} of 16 km or more; the median run is ${median(runs.map(r => r.km)).toFixed(1)} km.` : '';
  }

  // Activity mix: hours per activity type, one colour (the types have no order), biggest first.
  {
    const by = new Map();
    for (const r of acts) { const e = by.get(lower(r.type)) || { min: 0, n: 0 }; e.min += r.min || 0; e.n++; by.set(lower(r.type), e); }
    let rows = [...by.entries()].sort((a, b) => b[1].min - a[1].min);
    if (rows.length > 6) rows = [...rows.slice(0, 5), ['other', rows.slice(5).reduce((s, [, e]) => ({ min: s.min + e.min, n: s.n + e.n }), { min: 0, n: 0 })]];
    const total = rows.reduce((s, [, e]) => s + e.min, 0) || 1, max = Math.max(...rows.map(([, e]) => e.min), 1);
    $('ch-mix').innerHTML = `<div class="hbars">${rows.map(([name, e]) => `<div class="hbar" tabindex="0"${tipAttr(hoursFmt(e.min), `${name} · ${e.n} activit${e.n === 1 ? 'y' : 'ies'} · ${Math.round(e.min / total * 100)}% of the time`)}>` +
      `<span class="n">${esc(name)}</span><span class="track"><i style="width:${(e.min / max * 100).toFixed(1)}%"></i></span><span class="v">${hoursFmt(e.min)}</span></div>`).join('')}</div>`;
  }

  // Records in the period.
  {
    const best = (rows, k, minKm) => rows.filter(r => r.km >= minKm && num(r[k]) && r[k] > 2.5).reduce((a, r) => !a || r[k] < a[k] ? r : a, null);
    const longest = runs.reduce((a, r) => !a || r.km > a.km ? r : a, null);
    const weeks = new Map(), months = new Map();
    for (const r of runs) {
      const w = iso(mondayOf(new Date(t(r.d)))), m = r.d.slice(0, 7);
      weeks.set(w, (weeks.get(w) || 0) + r.km); months.set(m, (months.get(m) || 0) + r.km);
    }
    const top = map => [...map.entries()].reduce((a, e) => !a || e[1] > a[1] ? e : a, null);
    const bw = top(weeks), bm = top(months);
    // Longest run of consecutive weeks with at least one run.
    let streak = 0, run = 0, streakEnd = null;
    for (let w = mondayOf(start); w <= today; w = addDays(w, 7)) {
      if (weeks.has(iso(w))) { run++; if (run > streak) { streak = run; streakEnd = w; } } else run = 0;
    }
    const climb = acts.reduce((a, r) => !a || (r.elev || 0) > (a.elev || 0) ? r : a, null);
    const p5 = best(runs, 'pace', 5), p10 = best(runs, 'pace', 10);
    const rec = (k, v, s) => `<div class="tile"><span class="eyebrow">${k}</span><span class="v">${v}</span><span class="s">${s}</span></div>`;
    $('records').innerHTML = `<div class="tiles">${[
      longest && rec('Longest run', `${longest.km.toFixed(1)}<small>km</small>`, `${fmtDate(longest.d)} · ${esc(longest.name)}`),
      p5 && rec('Fastest pace, 5 km+', `${pace(p5.pace)}<small>/km</small>`, `${fmtDate(p5.d)} · ${p5.km.toFixed(1)} km`),
      p10 && rec('Fastest pace, 10 km+', `${pace(p10.pace)}<small>/km</small>`, `${fmtDate(p10.d)} · ${p10.km.toFixed(1)} km`),
      bw && rec('Biggest week', `${bw[1].toFixed(1)}<small>km</small>`, `week of ${fmtDate(bw[0])}`),
      bm && rec('Biggest month', `${Math.round(bm[1])}<small>km</small>`, `${MON[Number(bm[0].slice(5)) - 1]} ${bm[0].slice(0, 4)}`),
      streak && rec('Longest streak', `${streak}<small>week${streak === 1 ? '' : 's'}</small>`, `with a run every week, to ${fmtDate(iso(addDays(streakEnd, 6)))}`),
      climb && climb.elev && rec('Most climbing', `${Math.round(climb.elev)}<small>m</small>`, `${fmtDate(climb.d)} · ${esc(climb.name)}`),
    ].filter(Boolean).join('')}</div>`;
  }

  // Activity log: the table view of everything above, newest first, filtered by type.
  {
    const types = [...new Set(acts.map(r => lower(r.type)))].sort();
    if (histType !== 'all' && !types.includes(histType)) histType = 'all';
    const rows = [...acts].reverse().filter(r => histType === 'all' || lower(r.type) === histType);
    const shown = histAll ? rows : rows.slice(0, 15);
    $('histlog').innerHTML = `<div class="logbar"><label>Type <select id="hist-type"><option value="all">All (${acts.length})</option>${
      types.map(ty => `<option value="${esc(ty)}"${ty === histType ? ' selected' : ''}>${esc(ty)} (${acts.filter(r => lower(r.type) === ty).length})</option>`).join('')
    }</select></label><span class="cap">${rows.length} activit${rows.length === 1 ? 'y' : 'ies'} · ${kmFmt(sumBy(rows, 'km'))} · ${hoursFmt(sumBy(rows, 'min'))}</span></div>` +
      `<div class="tbl"><table><thead><tr><th>Date</th><th>Activity</th><th class="n">Distance</th><th class="n">Time</th><th class="n">Pace</th><th class="n">Avg HR</th><th class="n">Load</th><th class="n">Climb</th></tr></thead><tbody>${
        shown.map(r => `<tr><td>${dayName(r.d)} ${fmtDate(r.d)}</td><td>${esc(r.name)} <span class="eyebrow">${esc(lower(r.type))}</span></td><td class="n">${num(r.km) && r.km > 0 ? r.km.toFixed(1) + ' km' : '–'}</td><td class="n">${num(r.min) ? hms(r.min * 60) : '–'}</td><td class="n">${num(r.pace) && isRun(r.type) ? pace(r.pace) + ' /km' : '–'}</td><td class="n">${num(r.avg_hr) ? Math.round(r.avg_hr) : '–'}</td><td class="n">${num(r.load) ? Math.round(r.load) : '–'}</td><td class="n">${num(r.elev) && r.elev > 0 ? Math.round(r.elev) + ' m' : '–'}</td></tr>`).join('') || '<tr><td colspan="8">No activities.</td></tr>'
      }</tbody></table></div>${rows.length > 15 ? `<button type="button" class="livebtn" id="hist-more">${histAll ? 'Show the latest 15' : `Show all ${rows.length}`}</button>` : ''}`;
    $('hist-type').onchange = e => { histType = e.target.value; histAll = false; renderHistory(D); };
    const more = $('hist-more');
    if (more) more.onclick = () => { histAll = !histAll; renderHistory(D); };
  }
}

bindTips($('panel-history'));
bindTips($('panel-training'));
bindTips($('panel-today'));
// Redraw when the window crosses the phone width, so the wide charts switch drawing width.
{
  let narrow = innerWidth < 700;
  addEventListener('resize', () => { if ((innerWidth < 700) !== narrow) { narrow = !narrow; rerender(); } });
}
