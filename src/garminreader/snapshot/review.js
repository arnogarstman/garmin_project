// Latest workout: Claude's review of each new workout (marts.fct_workout_reviews, written by the
// coach source in the refresh after a workout). The newest in full, the ones before it folded.
const REVIEW_TONE = { good: 'good', watch: 'warn', concern: 'crit' };
// The lists arrive as JSON text (to_json in the query), from the snapshot and the connector alike.
const reviewList = v => {
  if (Array.isArray(v)) return v;
  try { const a = JSON.parse(v ?? '[]'); return Array.isArray(a) ? a : []; } catch { return []; }
};

function renderReviews(rows) {
  const el = $('wreview');
  if (!rows || !rows.length) {
    el.innerHTML = '<p class="cap">No workout reviews yet. A review appears here after the refresh that follows a workout.</p>';
    return;
  }
  const tone = r => REVIEW_TONE[r.status] || 'warn';
  const statusPill = r => `<span class="pill ${tone(r)}">${esc(r.status)}</span>`;
  const meta = r => [fmtDate(r.activity_date), r.activity_name, lower(r.session_type) !== lower(r.activity_name) && r.session_type]
    .filter(Boolean).map(esc).join(' · ');
  const items = (title, list) => list.length ? `<div><h4>${title}</h4><ul>${list.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : '';
  const advice = r => `<p><b>Recovery.</b> ${esc(r.recovery)}</p><p><b>Next session.</b> ${esc(r.next_session)}</p>`;

  const [r, ...older] = rows;
  let html = `<div class="card ${tone(r)}"><div class="head"><span class="eyebrow">${meta(r)}</span>${statusPill(r)}</div>` +
    `<h3>${esc(r.headline)}</h3><p class="why">${esc(r.summary)}</p>` +
    `<div class="wlist">${items('Went well', reviewList(r.went_well))}${items('To watch', reviewList(r.watch_out))}</div>${advice(r)}</div>`;
  if (older.length) {
    html += '<div class="wolder">' + older.map(o =>
      `<details><summary><span class="d">${fmtDate(o.activity_date)}</span><h3>${esc(o.headline)}</h3>${statusPill(o)}</summary>` +
      `<div class="body"><span class="eyebrow">${meta(o)}</span><p>${esc(o.summary)}</p>${advice(o)}</div></details>`).join('') + '</div>';
  }
  el.innerHTML = html;
}
