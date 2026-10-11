// Events on the trend charts: races from the data, plus illness, injury, travel and other notes kept
// in the artifact's database (settings/events, one list), so a dip in a chart has its reason beside
// it. A one-day event is a dashed line, a span a band. The notes box sits in the History tab and
// renders on its own (like the race form), so a re-render never wipes a note being typed.
const EVENTS_DOC = 'settings/events';
const EVENTS_MAX = 200;
const EVENT_KINDS = { illness: ['Illness', 'crit'], injury: ['Injury', 'crit'], travel: ['Travel', 'c5'], other: ['Note', 'muted'] };
const evs = { ref: null, canWrite: false, items: [], loaded: false, busy: false, msg: '' };

// The events between x0 and x1 (ms), races included unless `races` is false: [{s, e, color, value, label}].
function chartEvents(D, x0, x1, { races = true } = {}) {
  const out = [];
  for (const n of evs.items) {
    const s = t(n.from), e = n.to && n.to > n.from ? t(n.to) : s, [name, color] = EVENT_KINDS[n.kind] || EVENT_KINDS.other;
    if (e < x0 || s > x1) continue;
    out.push({ s, e, color, value: name, label: `${fmtDate(n.from)}${e > s ? ` to ${fmtDate(n.to)}` : ''}${n.note ? ` · ${n.note}` : ''}` });
  }
  if (races) for (const r of D.races || []) {
    const s = t(r.race_date);
    if (s >= x0 && s <= x1) out.push({ s, e: s, color: 'c3', value: 'Race', label: `${fmtDate(r.race_date)} · ${r.activity_name} · ${hms(r.finish_time_s)}` });
  }
  return out;
}

// The events as SVG on a frame() chart, drawn under the data; each carries a hover and focus tooltip.
function eventMarks(f, list) {
  let s = '';
  for (const ev of list) {
    const a = f.X(ev.s), b = ev.e > ev.s ? f.X(ev.e + DAY) : a, c = css(ev.color), top = f.T, h = f.ih;
    s += b > a
      ? `<rect x="${a}" y="${top}" width="${b - a}" height="${h}" fill="color-mix(in srgb, ${c} 12%, transparent)"/>`
      : `<line x1="${a}" x2="${a}" y1="${top}" y2="${top + h}" stroke="${c}" stroke-width="1.2" stroke-dasharray="3 3"/>`;
    s += `<circle cx="${(a + b) / 2}" cy="${top + 3}" r="3" fill="${c}"/>`;
    s += `<rect class="mark" x="${Math.min(a, (a + b) / 2 - 6)}" y="${top - 4}" width="${Math.max(12, b - a)}" height="14" fill="transparent" tabindex="0"${tipAttr(ev.value, ev.label)}/>`;
  }
  return s;
}

// The events within `days` days of a date (ms), as text, for a chart's tooltip or a coach card.
function eventsNear(x, days = 3) {
  return evs.items.filter(n => {
    const s = t(n.from), e = n.to && n.to > n.from ? t(n.to) : s;
    return x >= s - days * DAY && x <= e + days * DAY;
  }).map(n => `${(EVENT_KINDS[n.kind] || EVENT_KINDS.other)[0].toLowerCase()}${n.note ? ` (${n.note})` : ''}, ${fmtDate(n.from)}${n.to && n.to > n.from ? ` to ${fmtDate(n.to)}` : ''}`);
}

// The key under the charts that carry events, shown once there is something to mark.
function eventKey(D, x0, x1) {
  const list = chartEvents(D, x0, x1);
  if (!list.length) return '';
  const kinds = [...new Map(list.map(e => [e.value, e.color])).entries()];
  return `<div class="legend">${kinds.map(([name, c]) => `<span><b style="background:none;border-left:2px dashed var(--${c});height:12px;width:0;border-radius:0"></b>${name}</span>`).join('')}<span class="cap">Add illness, injury or travel under History → Events.</span></div>`;
}

function renderEventBox() {
  const box = $('events');
  if (!box) return;
  if (!evs.ref) {
    box.innerHTML = '<p class="cap">Open the page on claude.ai to note illness, injury or travel. Races show on the charts from the data.</p>';
    return;
  }
  const items = [...evs.items].sort((a, b) => a.from < b.from ? 1 : -1);
  const list = items.length
    ? `<div class="evlist">${items.map(n => {
      const [name, c] = EVENT_KINDS[n.kind] || EVENT_KINDS.other;
      return `<div class="ev"><i style="background:var(--${c})"></i><span class="d">${fmtDate(n.from)}${n.to && n.to > n.from ? `–${fmtDate(n.to)}` : ''} ${n.from.slice(0, 4)}</span><b>${name}</b><span>${esc(n.note || '')}</span>${evs.canWrite ? `<button type="button" class="livebtn" data-del="${esc(n.id)}" aria-label="Remove ${name} of ${fmtDate(n.from)}">Remove</button>` : ''}</div>`;
    }).join('')}</div>`
    : '<p class="cap">No events yet. A note on a cold, a niggle or a trip explains the dip it causes in the charts.</p>';
  const form = evs.canWrite ? `<form id="ev-f" class="evform" novalidate>
      <label>What<select name="kind">${Object.entries(EVENT_KINDS).map(([k, [n]]) => `<option value="${k}">${n}</option>`).join('')}</select></label>
      <label>From<input name="from" type="date" required value="${iso(new Date())}"></label>
      <label>To (optional)<input name="to" type="date"></label>
      <label class="wide">Note (optional)<input name="note" maxlength="80" placeholder="e.g. cold, calf niggle, trip to Lisbon"></label>
      <div class="btns"><button type="submit" class="primary"${evs.busy ? ' disabled' : ''}>Add event</button></div>
    </form>` : '';
  box.innerHTML = `${form}${evs.msg ? `<p class="msg">${esc(evs.msg)}</p>` : ''}${list}`;
  const f = $('ev-f');
  if (f) f.onsubmit = e => {
    e.preventDefault();
    const v = Object.fromEntries(new FormData(f));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v.from)) { evs.msg = 'Pick the day it started.'; renderEventBox(); return; }
    if (v.to && v.to < v.from) { evs.msg = 'The end comes after the start.'; renderEventBox(); return; }
    const item = { id: Date.now().toString(36), kind: EVENT_KINDS[v.kind] ? v.kind : 'other', from: v.from, to: v.to || '', note: v.note.trim() };
    saveEvents([...evs.items, item].slice(-EVENTS_MAX));
  };
  for (const b of box.querySelectorAll('[data-del]')) b.onclick = () => saveEvents(evs.items.filter(n => n.id !== b.dataset.del));
}

async function saveEvents(items) {
  if (evs.busy) return;
  evs.busy = true;
  evs.msg = '';
  try {
    await evs.ref.set({ items, updated_at: new Date().toISOString() });
  } catch (err) {
    if (err.code === 'invalid_argument') evs.canWrite = false;
    evs.msg = err.code === 'quota_exceeded' ? 'The page storage is full.' : 'Saving failed; try again in a moment.';
  } finally {
    evs.busy = false;
    renderEventBox();
  }
}

async function startEvents() {
  renderEventBox();
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  if (typeof db?.doc !== 'function') return;
  try { user = await window.claude.use('user'); } catch { user = null; }
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  evs.canWrite = canWrite !== false;
  evs.ref = db.doc(EVENTS_DOC);
  evs.ref.onSnapshot(snap => {
    const raw = snap.exists ? snap.data().items : null;
    const items = Array.isArray(raw) ? raw.filter(n => n && /^\d{4}-\d{2}-\d{2}$/.test(n.from || '')) : [];
    // Snapshots also arrive while nothing changed: keep a note being typed.
    if (evs.loaded && JSON.stringify(items) === JSON.stringify(evs.items)) return;
    evs.items = items;
    evs.loaded = true;
    renderEventBox();
    rerender();
  }, () => { evs.ref = null; evs.items = []; renderEventBox(); rerender(); });
}

startEvents();
