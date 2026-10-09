// Renders the page from a payload (snapshot/data.py): window.__SNAPSHOT__ when the data is
// embedded, or each result of the live query (live.js). Every section tolerates missing data:
// a fresh or partial warehouse still renders, and rendering again replaces the previous output.
const $ = id => document.getElementById(id);
const css = n => `var(--${n})`;
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const DAY = 864e5;
const t = d => new Date(d.slice(0, 10) + 'T00:00:00').getTime();
const fmtDate = d => { const x = new Date(t(d)); return `${x.getDate()} ${MON[x.getMonth()]}`; };
const hms = s => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };
const pace = p => { let m = Math.floor(p), s = Math.round((p - m) * 60); if (s === 60) { m += 1; s = 0; } return `${m}:${String(s).padStart(2, '0')}`; };
const num = v => typeof v === 'number' && isFinite(v);
const lower = v => (v ?? '').toString().toLowerCase().replaceAll('_', ' ');
const median = a => { const b = a.filter(num).sort((x, y) => x - y); return b.length ? b[b.length >> 1] : null; };
const rolling = (rows, i, n, k) => { const w = rows.slice(Math.max(0, i - n + 1), i + 1).map(r => r[k]).filter(num); return w.length ? w.reduce((s, v) => s + v, 0) / w.length : null; };
const esc = v => String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const empty = (id, msg) => { $(id).innerHTML = `<p class="cap">${msg}</p>`; };
const goodLevels = ['productive', 'peaking', 'optimal', 'high', 'prime', 'maintaining'];
const pill = v => v ? `<span class="pill ${goodLevels.includes(lower(v)) ? 'good' : 'warn'}">${lower(v)}</span>` : '–';

function niceTicks(lo, hi, n = 4) {
  if (hi <= lo) hi = lo + 1;
  const step0 = (hi - lo) / n, mag = 10 ** Math.floor(Math.log10(step0)), r = step0 / mag;
  const step = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag;
  const out = [];
  for (let v = Math.floor(lo / step) * step; v <= Math.ceil(hi / step) * step + step / 2; v += step) out.push(+v.toFixed(6));
  return out;
}

// One frame for every time chart: dates on x, its own scale on y.
function frame({ x0, x1, yTicks, fmtY, W = 520, H = 210 }) {
  const L = 48, R = 10, T = 8, B = 24, iw = W - L - R, ih = H - T - B;
  const y0 = yTicks[0], y1 = yTicks[yTicks.length - 1];
  const X = v => L + (v - x0) / (x1 - x0 || 1) * iw, Y = v => T + ih - (v - y0) / (y1 - y0) * ih;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
  for (const v of yTicks) s += `<line x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="${css('grid')}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${fmtY(v)}</text>`;
  const months = (x1 - x0) / (30 * DAY), every = months > 8 ? 2 : 1;
  const d = new Date(x0); d.setDate(1); d.setMonth(d.getMonth() + 1);
  for (let i = 0; d.getTime() <= x1; d.setMonth(d.getMonth() + 1), i++) {
    if (i % every) continue;
    const xx = X(d.getTime());
    s += `<line x1="${xx}" x2="${xx}" y1="${T + ih}" y2="${T + ih + 4}" stroke="${css('muted')}"/><text x="${xx}" y="${H - 6}" text-anchor="middle">${MON[d.getMonth()]}</text>`;
  }
  return { s, X, Y, L, R, T, W, ih };
}
const path = (pts, X, Y) => pts.filter(p => num(p[1])).map((p, i) => (i ? 'L' : 'M') + X(p[0]).toFixed(1) + ',' + Y(p[1]).toFixed(1)).join('');
const endDot = (p, X, Y, c, label, dy = -8) => `<circle cx="${X(p[0])}" cy="${Y(p[1])}" r="3.5" fill="${c}"/><text x="${X(p[0]) - 6}" y="${Y(p[1]) + dy}" text-anchor="end" style="fill:${c};font-weight:500">${label}</text>`;
const lastValid = pts => [...pts].reverse().find(p => num(p[1]));

const INTRO = document.getElementById('intro').textContent;

function renderPage(D) {
  // Header
  const demo = D.profile === 'demo';
  $('built').textContent = new Date(D.built_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  $('profile').textContent = demo ? 'Synthetic demo athlete' : 'Live Garmin data';
  $('intro').textContent = INTRO + (demo ? ' The numbers below come from the synthetic athlete, rendered as real Garmin API responses and run through the unchanged pipeline.' : '');
  $('footer').textContent = demo
    ? 'Synthetic data only; no personal Garmin data is included.'
    : 'Personal Garmin data. Snapshot of the marts at build time; refreshed by the daily run.';

  const days = D.daily, st = D.status || {};
  const x1 = days.length ? t(days[days.length - 1].d) : Date.now(), x0 = days.length ? t(days[0].d) : x1 - 365 * DAY;

  // A device can report a stale first VO2 max reading; ignore leading values far from the 2-week median.
  const vo2Base = median(days.slice(0, 14).map(r => r.vo2max));
  for (const r of days.slice(0, 3)) if (num(r.vo2max) && num(vo2Base) && Math.abs(r.vo2max - vo2Base) > 3) r.vo2max = null;

  // Tiles
  const tile = (k, v, s) => `<div class="tile"><span class="eyebrow">${k}</span><span class="v">${v}</span><span class="s">${s}</span></div>`;
  const vo2Delta = num(st.vo2max) && num(vo2Base) ? st.vo2max - vo2Base : null;
  $('tiles').innerHTML = [
    tile('Training status', pill(st.training_status), num(st.acwr) ? `Load ratio ${st.acwr.toFixed(1)} · ${lower(st.acwr_status)}` : ''),
    tile('Readiness', num(st.readiness_score) ? `${st.readiness_score}<small>/100</small>` : '–', pill(st.readiness_level)),
    tile('VO2 max', num(st.vo2max) ? `${st.vo2max.toFixed(1)}<small>ml/kg/min</small>` : '–', num(vo2Delta) ? `${vo2Delta >= 0 ? '+' : ''}${vo2Delta.toFixed(1)} since ${fmtDate(days[0].d)}` : ''),
    tile('Resting HR', num(st.resting_hr) ? `${st.resting_hr}<small>bpm</small>` : '–', num(st.body_battery_current) ? `Body battery ${st.body_battery_current}` : ''),
    tile('Half marathon', num(st.predicted_half_marathon_s) ? hms(st.predicted_half_marathon_s) : '–', num(st.predicted_10k_s) ? `Predicted · 10K ${hms(st.predicted_10k_s)}` : 'Predicted'),
    tile('Weight', num(st.weight_kg) ? `${st.weight_kg.toFixed(1)}<small>kg</small>` : '–', num(st.body_fat_pct) ? `Body fat ${st.body_fat_pct}%` : ''),
  ].join('');

  // Goal: a half marathon target such as "under 1:40" becomes a reference line.
  const G = D.goal;
  const targetMatch = G && /half/i.test(G.goal) && /(\d+):(\d{2})(?::(\d{2}))?/.exec(G.target || '');
  const targetS = targetMatch ? (+targetMatch[1]) * 3600 + (+targetMatch[2]) * 60 + (+(targetMatch[3] || 0)) : null;
  $('goaleb').textContent = G
    ? [G.goal, G.target, G.event_date && `${fmtDate(G.event_date)} · ${Math.round((t(G.event_date) - x1) / DAY)} days out`].filter(Boolean).join(' · ')
    : 'No goal set in the dashboard';
  $('lg-target').hidden = !targetS;

  // Half marathon prediction
  {
    const P = D.pred.map(r => [t(r.d), r.phm]).filter(p => num(p[1]));
    const races = D.races.filter(r => /half/i.test(r.race_distance || ''));
    if (P.length < 2) empty('ch-pred', 'No race predictions in the warehouse yet.');
    else {
      const ys = [...P.map(p => p[1]), ...races.map(r => r.finish_time_s), ...(targetS ? [targetS] : [])];
      const a = Math.floor((Math.min(...ys) - 60) / 300) * 300, b = Math.ceil((Math.max(...ys) + 60) / 300) * 300;
      const step = (b - a) / 300 > 8 ? 600 : 300, ticks = [];
      for (let v = a; v <= b; v += step) ticks.push(v);
      const f = frame({ x0: Math.min(x0, P[0][0]), x1, yTicks: ticks, fmtY: v => hms(v).replace(/:00$/, '') });
      let s = f.s;
      if (targetS) s += `<line x1="${f.L}" x2="${f.W - f.R}" y1="${f.Y(targetS)}" y2="${f.Y(targetS)}" stroke="${css('c6')}" stroke-dasharray="5 4" stroke-width="1.5"/>`;
      s += `<path d="${path(P, f.X, f.Y)}" fill="none" stroke="${css('c1')}" stroke-width="2.2"/>`;
      for (const r of races) if (t(r.race_date) >= x0) s += `<circle cx="${f.X(t(r.race_date))}" cy="${f.Y(r.finish_time_s)}" r="5" fill="${css('c3')}" stroke="${css('bg')}" stroke-width="2"><title>${esc(r.activity_name)} ${fmtDate(r.race_date)}: ${hms(r.finish_time_s)}</title></circle>`;
      const last = P[P.length - 1];
      $('ch-pred').innerHTML = s + endDot(last, f.X, f.Y, css('c1'), hms(last[1]), 16) + '</svg>';
      const parts = [`Prediction moved ${hms(Math.abs(P[0][1] - last[1]))} ${last[1] <= P[0][1] ? 'faster' : 'slower'} since ${fmtDate(new Date(P[0][0]).toISOString())}`];
      if (targetS) parts.push(`it sits ${hms(Math.abs(last[1] - targetS))} ${last[1] > targetS ? 'above' : 'below'} the target`);
      let cap = parts.join(' and ') + '.';
      if (races.length) cap += ' Race times: ' + races.map(r => `${hms(r.finish_time_s)} on ${fmtDate(r.race_date)}`).join(', ') + '.';
      $('cap-pred').textContent = cap;
    }
  }

  // Weekly running volume
  {
    const Wk = D.weekly.filter(r => t(r.wk) >= x0 - 6 * DAY);
    if (!Wk.length) empty('ch-km', 'No activities in this period.');
    else {
      const last = Wk[Wk.length - 1], partial = t(last.wk) + 7 * DAY > x1 + DAY;
      const full = partial ? Wk.slice(0, -1) : Wk;
      const f = frame({ x0: t(Wk[0].wk), x1: t(last.wk) + 7 * DAY, yTicks: niceTicks(0, Math.max(...Wk.map(r => r.run_km), 1), 4), fmtY: v => v });
      const bw = Math.max((f.X(t(Wk[0].wk) + 7 * DAY) - f.X(t(Wk[0].wk))) * 0.72, 1);
      let s = f.s;
      for (const r of Wk) { const x = f.X(t(r.wk)), y = f.Y(r.run_km); s += `<rect x="${x + 1}" y="${y}" width="${bw}" height="${f.Y(0) - y}" fill="${css('c1')}" opacity="${partial && r === last ? 0.4 : 0.85}" rx="1.5"><title>Week of ${fmtDate(r.wk)}: ${r.run_km} km</title></rect>`; }
      const m = full.map((r, i) => [t(r.wk) + 3.5 * DAY, rolling(full, i, 4, 'run_km')]);
      $('ch-km').innerHTML = s + `<path d="${path(m, f.X, f.Y)}" fill="none" stroke="${css('ink2')}" stroke-width="1.6"/></svg>`;
      const run = D.types.find(r => r.activity_type === 'running');
      const latest = lastValid(m);
      $('cap-km').textContent = [run && `${run.n} runs, ${Math.round(run.km).toLocaleString('en')} km in this period.`, latest && `Recent 4-week average ${latest[1].toFixed(0)} km.`, partial && 'The faded bar is the current, unfinished week.'].filter(Boolean).join(' ');
    }
  }

  // VO2 max
  {
    const P = days.map(r => [t(r.d), r.vo2max]), v = P.map(p => p[1]).filter(num);
    if (v.length < 2) empty('ch-vo2', 'No VO2 max readings yet.');
    else {
      const f = frame({ x0, x1, yTicks: niceTicks(Math.min(...v) - 0.5, Math.max(...v) + 0.5, 4), fmtY: x => x, H: 180 });
      const line = path(P, f.X, f.Y), first = P.find(p => num(p[1])), last = lastValid(P);
      let s = f.s + `<path d="${line}L${f.X(last[0])},${f.T + f.ih}L${f.X(first[0])},${f.T + f.ih}Z" fill="${css('c2')}" opacity=".12"/><path d="${line}" fill="none" stroke="${css('c2')}" stroke-width="2.2"/>`;
      $('ch-vo2').innerHTML = s + endDot(last, f.X, f.Y, css('c2'), last[1].toFixed(1)) + '</svg>';
      const r0 = rolling(days, 6, 7, 'rhr'), r1 = rolling(days, days.length - 1, 7, 'rhr');
      $('cap-vo2').textContent = `From ${(vo2Base ?? v[0]).toFixed(1)} to ${last[1].toFixed(1)} ml/kg/min.` + (num(r0) && num(r1) ? ` Resting HR 7-day average went from ${r0.toFixed(0)} to ${r1.toFixed(0)} bpm.` : '');
    }
  }

  // Training load
  {
    const A = days.map(r => [t(r.d), r.acute]), C = days.map(r => [t(r.d), r.chronic]);
    const v = [...A, ...C].map(p => p[1]).filter(num);
    if (v.length < 2) empty('ch-load', 'No training load data yet.');
    else {
      const f = frame({ x0, x1, yTicks: niceTicks(0, Math.max(...v), 4), fmtY: x => x, H: 180 });
      $('ch-load').innerHTML = f.s + `<path d="${path(C, f.X, f.Y)}" fill="none" stroke="${css('c2')}" stroke-width="2.2"/><path d="${path(A, f.X, f.Y)}" fill="none" stroke="${css('c5')}" stroke-width="1.4"/></svg>`;
      $('cap-load').textContent = num(st.acwr) ? `Acute to chronic ratio is ${st.acwr.toFixed(1)} today (${lower(st.acwr_status)}). Above 1.5 the dashboard flags injury risk.` : '';
    }
  }

  // Heart rate zones
  {
    const z = D.zones || {}, keys = ['z1', 'z2', 'z3', 'z4', 'z5'], cols = ['muted', 'c1', 'c2', 'c3', 'c6'];
    const tot = keys.reduce((s, k) => s + (z[k] || 0), 0);
    if (!tot) empty('ch-zones', 'No heart rate zone data yet.');
    else {
      const W = 1000; let x = 0, s = `<svg viewBox="0 0 ${W} 58" role="img">`;
      keys.forEach((k, i) => {
        const w = (z[k] || 0) / tot * W, pct = Math.round((z[k] || 0) / tot * 100), h = Math.round((z[k] || 0) / 60);
        s += `<rect x="${x}" y="0" width="${Math.max(w - 2, 0)}" height="26" fill="${css(cols[i])}" opacity="${i ? 0.9 : 0.5}"><title>Zone ${i + 1}: ${h} h</title></rect>`;
        if (w > 60) s += `<text x="${x}" y="44">Z${i + 1} ${pct}%</text><text x="${x}" y="58">${h} h</text>`;
        else if (w > 0) s += `<text x="${x + w}" y="44" text-anchor="end">Z${i + 1} ${pct}%</text>`;
        x += w;
      });
      $('ch-zones').innerHTML = s + '</svg>';
    }
  }

  // Run calendar: one continuous grid of weeks, Monday to Sunday, newest week on top, so the
  // last day of a month and the first of the next sit side by side in the week they share. Each
  // month is headed above its own days in its topmost week, alternates in tint and marks its 1st. Each run
  // is a bubble whose area is proportional to its distance (diameter grows with the square root),
  // on one fixed scale.
  {
    const runs = D.runs || [], byDay = new Map(), totals = new Map();
    const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    for (const r of runs) {
      const k = r.activity_date.slice(0, 10), m = k.slice(0, 7);
      if (!byDay.has(k)) byDay.set(k, []);
      byDay.get(k).push(r);
      const tot = totals.get(m) || { n: 0, km: 0 };
      totals.set(m, { n: tot.n + 1, km: tot.km + (r.km || 0) });
    }
    const bubble = km => `<span class="bub" style="--r:${Math.sqrt(Math.max(km || 0, 0.25)).toFixed(3)}"></span>`;
    const monday = d => new Date(d.getFullYear(), d.getMonth(), d.getDate() - (d.getDay() + 6) % 7);
    // Every month of the past year, with or without runs, and further back when runs go further back.
    const last = new Date(x1), today = iso(last), yearAgo = new Date(last.getFullYear(), last.getMonth() - 11, 1);
    const firstRun = runs.length ? new Date(t(runs[0].activity_date)) : yearAgo;
    const start = firstRun < yearAgo ? new Date(firstRun.getFullYear(), firstRun.getMonth(), 1) : yearAgo;
    $('calkeys').innerHTML = runs.length ? 'Bubble area is proportional to distance:' + [5, 10, 21.1].map(km => `<span>${bubble(km)}${km} km</span>`).join('') : '';
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
          html += `<div class="mhead" style="grid-column:${a + 1} / span ${b - a + 1}"><h3>${MON[mo - 1]} ${y}</h3><span class="tot">${tot.n} run${tot.n === 1 ? '' : 's'} · ${tot.km.toFixed(1)} km</span></div>`;
          col = b + 1;
        }
        if (col < 7) html += `<span class="mgap" style="grid-column:span ${7 - col}"></span>`;
      }
      for (const d of week) {
        if (d < start || d > last) { html += '<span class="day pad"></span>'; continue; }
        const key = iso(d), rs = byDay.get(key) || [];
        const tip = rs.map(r => `${r.activity_name}: ${num(r.km) ? r.km.toFixed(1) + ' km' : ''}${num(r.min) ? ' in ' + hms(r.min * 60) : ''}${num(r.pace) ? ', ' + pace(r.pace) + ' /km' : ''}`).join('\n');
        const cls = ['day', d.getMonth() % 2 ? 'alt' : '', d.getDate() === 1 ? 'first' : '', key === today ? 'today' : ''].filter(Boolean).join(' ');
        html += `<div class="${cls}"${tip ? ` title="${esc(tip)}"` : ''}><span class="dn">${d.getDate() === 1 ? `1 ${MON[d.getMonth()]}` : d.getDate()}</span>` +
          (rs.length ? '<div class="runs">' + rs.map(r => `<div class="run">${bubble(r.km)}<span class="km">${num(r.km) ? r.km.toFixed(1) : '–'}<small>km</small></span><span class="nm">${esc(r.activity_name)}</span></div>`).join('') + '</div>' : '') + '</div>';
      }
    }
    $('cal').innerHTML = `<div class="mgrid">${html}</div>`;
  }

  // Recent activities
  $('recent').querySelector('tbody').innerHTML = D.recent.map(r => `<tr><td>${fmtDate(r.activity_date)}</td><td>${esc(r.activity_name)} <span class="eyebrow">${esc(lower(r.activity_type))}</span></td><td class="n">${num(r.km) && r.km > 0 ? r.km.toFixed(1) + ' km' : '–'}</td><td class="n">${num(r.min) ? hms(r.min * 60) : '–'}</td><td class="n">${num(r.pace) && /run/.test(r.activity_type || '') ? pace(r.pace) + ' /km' : '–'}</td><td class="n">${num(r.avg_hr) ? Math.round(r.avg_hr) : '–'}</td></tr>`).join('') || '<tr><td colspan="6">No activities yet.</td></tr>';

  // Data health
  $('health').innerHTML = D.lag.map(r => `<div><i style="background:${r.days_behind > 1 ? css('warn') : css('good')}"></i>${esc(lower(r.metric))} <span class="eyebrow">${r.days_behind}d behind · ${r.completeness_pct}%</span></div>`).join('');
}

if (!window.__LIVE__) renderPage(window.__SNAPSHOT__);
