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
// Average pace (min:ss per km) of a half marathon finished in s seconds.
const HM_KM = 21.0975;
const hmPace = s => `${pace(s / 60 / HM_KM)} /km`;
const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
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
    tile('Half marathon', num(st.predicted_half_marathon_s) ? hms(st.predicted_half_marathon_s) : '–', [num(st.predicted_half_marathon_s) && hmPace(st.predicted_half_marathon_s), num(st.predicted_10k_s) && `10K ${hms(st.predicted_10k_s)}`].filter(Boolean).join(' · ') || 'Predicted'),
    tile('Weight', num(st.weight_kg) ? `${st.weight_kg.toFixed(1)}<small>kg</small>` : '–', num(st.body_fat_pct) ? `Body fat ${st.body_fat_pct}%` : ''),
  ].join('');

  // Coach's read: five checks a coach makes on this data, each with a verdict, the numbers behind
  // it and the next step. Status is good, warn or crit; the pill always carries its word too.
  {
    const DAYS28 = 28 * DAY, mean = a => a.length ? a.reduce((s, v) => s + v, 0) / a.length : null;
    const sd = a => { const m = mean(a); return a.length > 1 ? Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / (a.length - 1)) : null; };
    const signed = (v, d = 0) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(d)}`;
    const runs = (D.runs || []).filter(r => num(r.km) && r.km > 0);
    const recent = runs.filter(r => t(r.activity_date) > x1 - DAYS28);
    const card = (topic, status, label, verdict, body, extra = '') =>
      `<div class="card ${status}"><div class="head"><span class="eyebrow">${topic}</span><span class="pill ${status === 'good' ? 'good' : status === 'warn' ? 'warn' : 'crit'}">${label}</span></div><h3>${verdict}</h3>${extra}<p>${body}</p></div>`;
    const none = (topic, msg) => `<div class="card"><div class="head"><span class="eyebrow">${topic}</span></div><p>${msg}</p></div>`;
    const kv = rows => `<div class="kv">${rows.map(([k, v, d]) => `<span>${k}</span><b>${v}</b><i>${d}</i>`).join('')}</div>`;
    const cards = [];
    const weekStart = d => { const x = new Date(t(d)); return t(iso(new Date(x.getFullYear(), x.getMonth(), x.getDate() - (x.getDay() + 6) % 7))); };

    // 1. Recovery: last night against the athlete's own 28-day baseline (the night itself excluded).
    {
      const lastDay = days[days.length - 1], base = days.slice(-29, -1);
      const hrvB = base.map(r => r.hrv).filter(num), rhrB = base.map(r => r.rhr).filter(num);
      const sleep7 = mean(days.slice(-7).map(r => r.sleep).filter(num)), sleepB = mean(base.map(r => r.sleep).filter(num));
      if (!lastDay || hrvB.length < 7 || rhrB.length < 7) cards.push(none('Recovery today', 'Needs a week of HRV and resting heart rate readings to set a baseline.'));
      else {
        const hrvM = mean(hrvB), hrvS = sd(hrvB) || 1, rhrM = mean(rhrB);
        const flags = [];
        if (num(lastDay.hrv) && lastDay.hrv < hrvM - hrvS) flags.push('HRV is below your normal range');
        if (num(lastDay.rhr) && lastDay.rhr > rhrM + 3) flags.push('resting HR is up');
        if (num(sleep7) && num(sleepB) && sleep7 < sleepB - 5) flags.push('sleep has dipped this week');
        const [status, label, verdict, advice] = !flags.length
          ? ['good', 'recovered', 'Ready to train as planned', 'HRV, resting HR and sleep all sit in your normal range, so the planned session can go ahead.']
          : flags.length === 1
            ? ['warn', 'watch', 'Some fatigue showing', `${flags[0][0].toUpperCase() + flags[0].slice(1)}. Keep hard work short today or swap it for an easy run.`]
            : ['crit', 'fatigued', 'Under-recovered', `${flags.join(' and ').replace(/^./, c => c.toUpperCase())}. Take a rest day or a very easy 30 minutes.`];
        cards.push(card('Recovery today', status, label, verdict, advice, kv([
          ['HRV last night', num(lastDay.hrv) ? `${lastDay.hrv} ms` : '–', num(lastDay.hrv) ? `${signed(lastDay.hrv - hrvM)} vs ${hrvM.toFixed(0)}` : ''],
          ['Resting HR', num(lastDay.rhr) ? `${lastDay.rhr} bpm` : '–', num(lastDay.rhr) ? `${signed(lastDay.rhr - rhrM)} vs ${rhrM.toFixed(0)}` : ''],
          ['Sleep, 7-day avg', num(sleep7) ? sleep7.toFixed(0) : '–', num(sleep7) && num(sleepB) ? `${signed(sleep7 - sleepB)} vs ${sleepB.toFixed(0)}` : ''],
        ])));
      }
    }

    // 2. Intensity balance over 4 weeks of running: about 80% easy (zones 1-2) is the endurance norm;
    // a large zone 3 share is the "grey zone" that tires without building much.
    {
      const sum = k => recent.reduce((s, r) => s + (num(r[k]) ? r[k] : 0), 0);
      const easy = sum('z1') + sum('z2'), mod = sum('z3'), hard = sum('z4') + sum('z5'), tot = easy + mod + hard;
      if (tot < 60) cards.push(none('Intensity balance', 'Needs heart rate zone data from at least an hour of running in the last 4 weeks.'));
      else {
        const pe = easy / tot * 100, pm = mod / tot * 100, ph = hard / tot * 100;
        const [status, label, verdict, advice] = pe >= 75
          ? ['good', 'balanced', 'Mostly easy, as it should be', `${pe.toFixed(0)}% of your running time was easy. That base lets the hard sessions count.`]
          : pm > ph
            ? ['warn', 'grey zone', 'Too much moderate running', `Only ${pe.toFixed(0)}% was easy and ${pm.toFixed(0)}% sat in zone 3. Slow the easy runs down until they stay in zones 1 and 2, and keep the hard days hard.`]
            : ['warn', 'too hard', 'Too much hard running', `${ph.toFixed(0)}% was in zones 4 and 5. Cap hard work at two sessions a week and run the rest easy.`];
        const W = 1000, seg = [[pe, 'c2', 'Easy Z1–2'], [pm, 'c3', 'Moderate Z3'], [ph, 'c6', 'Hard Z4–5']];
        let x = 0, svg = `<svg viewBox="0 0 ${W} 40" preserveAspectRatio="none" style="height:28px" role="img" aria-label="Easy ${pe.toFixed(0)}%, moderate ${pm.toFixed(0)}%, hard ${ph.toFixed(0)}%">`;
        for (const [p, c, name] of seg) {
          const w = p / 100 * W;
          if (w > 0) svg += `<rect x="${x}" y="8" width="${Math.max(w - 3, 0)}" height="22" rx="3" fill="${css(c)}"><title>${name}: ${p.toFixed(0)}%</title></rect>`;
          x += w;
        }
        svg += `<line x1="${0.8 * W}" x2="${0.8 * W}" y1="2" y2="38" stroke="${css('ink')}" stroke-width="2" stroke-dasharray="3 3"/></svg>`;
        svg += '<div class="legend">' + seg.map(([p, c, name]) => `<span><b style="background:${css(c)};height:8px;border-radius:2px"></b>${name} ${p.toFixed(0)}%</span>`).join('') + '<span><b style="background:none;border-left:2px dashed var(--ink);height:12px;width:0;border-radius:0"></b>80% easy target</span></div>';
        cards.push(card('Intensity balance · 4 weeks', status, label, verdict, advice, svg));
      }
    }

    // 3. Aerobic efficiency: metres per heartbeat on the easier half of the runs (by average HR).
    // Rising means the same effort carries you further: aerobic fitness is building.
    {
      const pts = runs.filter(r => num(r.avg_hr) && num(r.pace) && r.pace > 0 && num(r.min) && r.min >= 20);
      const cut = median(pts.map(r => r.avg_hr));
      const easy = pts.filter(r => r.avg_hr <= cut).map(r => [t(r.activity_date), 1000 / r.pace / r.avg_hr, r]);
      if (easy.length < 4) cards.push(none('Aerobic efficiency', 'Needs at least 4 easy runs of 20 minutes or more with heart rate.'));
      else {
        const xs = easy.map(p => p[0]), ys = easy.map(p => p[1]), mx = mean(xs), my = mean(ys);
        const slope = xs.reduce((s, x, i) => s + (x - mx) * (ys[i] - my), 0) / (xs.reduce((s, x) => s + (x - mx) ** 2, 0) || 1);
        const fit = x => my + slope * (x - mx), a = xs[0], b = xs[xs.length - 1], chg = (fit(b) / fit(a) - 1) * 100;
        const [status, label, verdict] = chg >= 2 ? ['good', 'improving', 'Easy pace is getting cheaper'] : chg > -2 ? ['warn', 'flat', 'Efficiency is holding steady'] : ['crit', 'declining', 'Easy runs cost more than before'];
        const advice = chg >= 2
          ? `You cover ${chg.toFixed(0)}% more ground per heartbeat than at the start of the period. The easy volume is working.`
          : chg > -2
            ? 'No clear change yet. Consistent easy volume over several weeks is what moves this.'
            : `Down ${Math.abs(chg).toFixed(0)}%. Heat, fatigue or illness raise heart rate at the same pace; check recovery before adding load.`;
        const f = frame({ x0: a, x1: Math.max(b, a + DAY), yTicks: niceTicks(Math.min(...ys) * 0.97, Math.max(...ys) * 1.03, 3), fmtY: v => v.toFixed(2), W: 520, H: 150 });
        let svg = f.s + `<path d="M${f.X(a)},${f.Y(fit(a))}L${f.X(b)},${f.Y(fit(b))}" stroke="${css('ink2')}" stroke-width="1.5" stroke-dasharray="5 4" fill="none"/>`;
        for (const [x, y, r] of easy) svg += `<circle cx="${f.X(x)}" cy="${f.Y(y)}" r="4.5" fill="${css('c1')}" stroke="${css('bg')}" stroke-width="2"><title>${esc(r.activity_name)} ${fmtDate(r.activity_date)}: ${pace(r.pace)} /km at ${Math.round(r.avg_hr)} bpm, ${y.toFixed(2)} m per beat</title></circle>`;
        cards.push(card('Aerobic efficiency', status, label, verdict, advice + ' Metres per heartbeat on your easier runs; dashed line is the trend.', svg + '</svg>'));
      }
    }

    // 4. Load progression: last complete week against up to three before it, plus the 7:28-day load ratio.
    {
      const kmByWeek = new Map();
      for (const r of runs) kmByWeek.set(weekStart(r.activity_date), (kmByWeek.get(weekStart(r.activity_date)) || 0) + r.km);
      const thisWeek = weekStart(iso(new Date(x1))), wk = i => kmByWeek.get(thisWeek - i * 7 * DAY) || 0;
      // Only weeks fully inside the data count: the week of the first run may be cut off.
      const covered = runs.length ? weekStart(runs[0].activity_date) + 7 * DAY : Infinity;
      const before = [2, 3, 4].filter(i => thisWeek - i * 7 * DAY >= covered);
      const last = wk(1), prev = mean(before.map(wk));
      if (!before.length || !prev) cards.push(none('Load progression', 'Needs at least two complete weeks of running to compare.'));
      else {
        const chg = (last / prev - 1) * 100, acwr = num(st.acwr) ? st.acwr : null;
        const [status, label, verdict, advice] = chg > 25 || (acwr && acwr > 1.5)
          ? ['crit', 'spike', 'Load jumped sharply', 'A jump this size is when injuries start. Hold this week at or below last week, then build by about 10% at a time.']
          : chg > 10 || (acwr && acwr > 1.3)
            ? ['warn', 'building fast', 'Building faster than 10% a week', 'Fine for a week, but plan a lighter week soon so the body catches up.']
            : chg < -30
              ? ['warn', 'down week', 'A clear step down', 'Good as a planned recovery week. If it was not planned, pick volume back up gradually.']
              : ['good', 'steady', 'A sustainable build', 'Volume is moving in steps the body can absorb. Keep every third or fourth week lighter.'];
        cards.push(card('Load progression', status, label, verdict, advice, kv([
          ['Last full week', `${last.toFixed(1)} km`, `${signed(chg)}%`],
          [`${before.length} week${before.length === 1 ? '' : 's'} before, avg`, `${prev.toFixed(1)} km`, ''],
          ['Acute : chronic load', acwr ? acwr.toFixed(2) : '–', acwr ? lower(st.acwr_status) : ''],
        ])));
      }
    }

    // 5. Long run: the longest run of the last 4 weeks and its share of its week's (Monday to Sunday) volume.
    {
      if (!recent.length) cards.push(none('Long run', 'No runs in the last 4 weeks.'));
      else {
        const lr = recent.reduce((a, r) => r.km > a.km ? r : a), lrWeek = weekStart(lr.activity_date);
        const weekKm = runs.filter(r => weekStart(r.activity_date) === lrWeek).reduce((s, r) => s + r.km, 0);
        const share = weekKm ? lr.km / weekKm * 100 : 0, perWeek = recent.length / 4;
        const [status, label, verdict, advice] = lr.km < 14
          ? ['warn', 'short', 'Long run is short for a half', `Your longest run in 4 weeks is ${lr.km.toFixed(1)} km. Add 1 to 2 km a week until it reaches 16 to 18 km, run at easy pace.`]
          : share > 40
            ? ['warn', 'lopsided', 'Too much of the week in one run', `That run was ${share.toFixed(0)}% of its week. Spread volume so the long run is about 30%; it recovers faster and injures less.`]
            : ['good', 'on track', lr.km >= 18 ? 'Half marathon distance is covered' : 'Long run is building well', `Your longest run is ${lr.km.toFixed(1)} km, ${share.toFixed(0)}% of its week. ${lr.km >= 18 ? 'Hold it here and add some race-pace kilometres late in the run.' : 'Keep extending it gradually toward 16 to 18 km.'}`];
        cards.push(card('Long run · 4 weeks', status, label, verdict, advice, kv([
          ['Longest run', `${lr.km.toFixed(1)} km`, fmtDate(lr.activity_date)],
          ['Share of its week', `${share.toFixed(0)}%`, `of ${weekKm.toFixed(0)} km`],
          ['Runs per week', perWeek.toFixed(1), `${recent.length} in 4 weeks`],
        ])));
      }
    }

    $('coach').innerHTML = cards.join('');
  }

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
      for (const r of races) if (t(r.race_date) >= x0) s += `<circle cx="${f.X(t(r.race_date))}" cy="${f.Y(r.finish_time_s)}" r="5" fill="${css('c3')}" stroke="${css('bg')}" stroke-width="2"><title>${esc(r.activity_name)} ${fmtDate(r.race_date)}: ${hms(r.finish_time_s)} (${hmPace(r.finish_time_s)})</title></circle>`;
      const last = P[P.length - 1];
      $('ch-pred').innerHTML = s + endDot(last, f.X, f.Y, css('c1'), `${hms(last[1])} · ${hmPace(last[1])}`, 16) + '</svg>';
      const parts = [`Prediction moved ${hms(Math.abs(P[0][1] - last[1]))} ${last[1] <= P[0][1] ? 'faster' : 'slower'} since ${fmtDate(new Date(P[0][0]).toISOString())}, from an average pace of ${hmPace(P[0][1])} to ${hmPace(last[1])}`];
      if (targetS) parts.push(`it sits ${hms(Math.abs(last[1] - targetS))} ${last[1] > targetS ? 'above' : 'below'} the target (${hmPace(targetS)})`);
      let cap = parts.join(' and ') + '.';
      if (races.length) cap += ' Race times: ' + races.map(r => `${hms(r.finish_time_s)} (${hmPace(r.finish_time_s)}) on ${fmtDate(r.race_date)}`).join(', ') + '.';
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
