// Live mode: window.__LIVE__ = {server, tool, database, queries, single_row, goal, profile} (written by
// snapshot/render.py). Instead of embedded data, the page runs each of data.live_queries() through the
// viewer's MotherDuck connector (the `mcp` capability of a claude.ai artifact), one call per query
// because the connector caps the size of a result, and renders with renderPage() once all have answered.
const REFRESH_MS = 15 * 60e3;

// Codes that mean this viewer may not see the data (any more): drop what is on screen.
const RETRACT = new Set(['needs_reauth', 'server_not_connected', 'selection_required', 'not_in_manifest', 'blocked_by_policy', 'approval_required', 'not_granted', 'capability_disabled', 'capability_removed']);
const NO_CONNECTORS = 'This view cannot reach connectors. Open the page on claude.ai, signed in with MotherDuck connected.';
// The connector sends BIGINT, HUGEINT and DECIMAL values as strings.
const NUMERIC = /^(TINYINT|SMALLINT|INTEGER|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT|FLOAT|REAL|DOUBLE|DECIMAL)/;

function liveMessage(code, server) {
  return {
    needs_reauth: `Reconnect ${server} in claude.ai Settings → Connectors to load the data.`,
    server_not_connected: `Add the ${server} connector in claude.ai Settings → Connectors to load the data.`,
    selection_required: `Choose which ${server} connector this page should use.`,
    not_in_manifest: `${server} is not allowed for this page. Allow it from the page's Permissions menu.`,
    blocked_by_policy: `Your organization does not allow this page to query ${server}.`,
    approval_required: `The queries need your approval before they run.`,
    not_granted: NO_CONNECTORS,
    capability_disabled: NO_CONNECTORS,
    capability_removed: NO_CONNECTORS,
  }[code];
}

// The connector answers {success, columns, columnTypes, rows, truncated?}: rows become objects.
function liveRows(result) {
  const p = result.payload;
  if (!p || p.success === false || !Array.isArray(p.rows) || !Array.isArray(p.columns)) throw new Error(p?.error || 'no result table');
  if (p.truncated) throw new Error(`the result was cut off (${p.warning || 'over the connector size limit'})`);
  const types = p.columnTypes || [];
  return p.rows.map(row => Object.fromEntries(p.columns.map((c, i) =>
    [c, row[i] !== null && typeof row[i] === 'string' && NUMERIC.test(types[i] || '') ? Number(row[i]) : row[i]])));
}

function clearPage() {
  for (const id of ['tiles', 'review', 'race', 'coach', 'ch-pred', 'cap-pred', 'ch-km', 'cap-km', 'ch-vo2', 'cap-vo2', 'ch-load', 'cap-load', 'ch-zones', 'cal', 'calkeys', 'health', 'built']) $(id).textContent = '';
  $('recent').querySelector('tbody').textContent = '';
}

async function startLive(cfg) {
  const state = $('livestate'), btn = $('livebtn');
  const say = (msg, isErr = false) => { state.hidden = !msg; state.textContent = msg || ''; state.classList.toggle('err', isErr); };
  const keys = Object.keys(cfg.queries), single = new Set(cfg.single_row);
  const input = key => ({ database: cfg.database, sql: cfg.queries[key] });
  const footer = `Personal Garmin data, queried live from the ${cfg.database} database on ${cfg.server} through your connector. Refreshes every 15 minutes while the page is open.`;
  const parts = {}, stamps = {}, failed = {};
  let shown = false, pending = 0;

  $('builtlbl').textContent = 'queried';
  $('footer').textContent = footer;
  say(`Loading the marts from ${cfg.server}…`);

  // Render once every query has answered, then again on each refresh (batched per frame).
  const render = () => {
    if (pending) return;
    pending = requestAnimationFrame(() => {
      pending = 0;
      if (keys.some(k => !(k in parts))) return;
      const builtAt = new Date(Math.min(...keys.map(k => stamps[k]))).toISOString();
      renderPage({ ...parts, built_at: builtAt, goal: cfg.goal, profile: cfg.profile });
      $('footer').textContent = footer;
      shown = true;
      btn.hidden = true;
      const bad = Object.keys(failed);
      say(bad.length ? `Refresh failed for ${bad.join(', ')}; showing the last result.` : '', !!bad.length);
    });
  };

  const accept = (key, result) => {
    let rows;
    try { rows = liveRows(result); } catch (e) { failed[key] = true; say(`${cfg.server} returned an unusable result for ${key}: ${e.message}`, true); return; }
    parts[key] = single.has(key) ? rows[0] ?? null : rows;
    stamps[key] = result.cache?.storedAt ?? Date.now();
    delete failed[key];
    render();
  };

  let mcp = null;
  try { mcp = window.claude ? await window.claude.use('mcp') : null; } catch { mcp = null; }
  if (!mcp) { say(NO_CONNECTORS, true); return; }

  // A watch never asks for approval; this button makes the calls that may.
  btn.onclick = async () => {
    btn.disabled = true;
    try { for (const key of keys) accept(key, await mcp.callTool(cfg.server, cfg.tool, input(key))); }
    catch (e) { say(liveMessage(e.code, cfg.server) || `A query failed (${e.code}): ${e.message}`, true); }
    finally { btn.disabled = false; }
  };

  for (const key of keys) {
    mcp.watchTool(cfg.server, cfg.tool, input(key), ev => {
      if (ev.type === 'data') { accept(key, ev.result); return; }
      const { code, message } = ev.error;
      if (RETRACT.has(code)) { clearPage(); shown = false; for (const k of keys) delete parts[k]; }
      else failed[key] = true;
      btn.hidden = code !== 'approval_required';
      if (code === 'tool_error') say(`The ${key} query failed in ${cfg.server}: ${message}`, true);
      else say(liveMessage(code, cfg.server) || (shown ? `Refresh failed (${code}); showing the last result.` : `Could not load the marts (${code}): ${message}`), true);
    }, { cache: { staleTime: 5 * 60e3, gcTime: 24 * 3600e3 }, refetchInterval: REFRESH_MS });
  }
}

if (window.__LIVE__) startLive(window.__LIVE__);
