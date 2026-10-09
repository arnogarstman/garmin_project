// Live mode: window.__LIVE__ = {server, tool, database, sql, goal, profile} (written by snapshot/render.py).
// Instead of embedded data, the page runs data.live_sql() through the viewer's MotherDuck connector
// (the `mcp` capability of a claude.ai artifact) and renders each result with renderPage().
const REFRESH_MS = 15 * 60e3;

// Codes that mean this viewer may not see the data (any more): drop what is on screen.
const RETRACT = new Set(['needs_reauth', 'server_not_connected', 'selection_required', 'not_in_manifest', 'blocked_by_policy', 'approval_required', 'not_granted', 'capability_disabled', 'capability_removed']);
const NO_CONNECTORS = 'This view cannot reach connectors. Open the page on claude.ai, signed in with MotherDuck connected.';

function liveMessage(code, server) {
  return {
    needs_reauth: `Reconnect ${server} in claude.ai Settings → Connectors to load the data.`,
    server_not_connected: `Add the ${server} connector in claude.ai Settings → Connectors to load the data.`,
    selection_required: `Choose which ${server} connector this page should use.`,
    not_in_manifest: `${server} is not allowed for this page. Allow it from the page's Permissions menu.`,
    blocked_by_policy: `Your organization does not allow this page to query ${server}.`,
    approval_required: `The query needs your approval before it runs.`,
    not_granted: NO_CONNECTORS,
    capability_disabled: NO_CONNECTORS,
    capability_removed: NO_CONNECTORS,
  }[code];
}

// The connector answers {success, columns, rows}; the statement returns one row with one JSON column.
function livePayload(result) {
  const p = result.payload;
  if (!p || p.success === false || !Array.isArray(p.rows) || !p.rows.length) throw new Error(p?.error || 'no rows returned');
  const v = p.rows[0][0];
  return typeof v === 'string' ? JSON.parse(v) : v;
}

function clearPage() {
  for (const id of ['tiles', 'ch-pred', 'cap-pred', 'ch-km', 'cap-km', 'ch-vo2', 'cap-vo2', 'ch-load', 'cap-load', 'ch-zones', 'cal', 'health', 'built']) $(id).textContent = '';
  $('recent').querySelector('tbody').textContent = '';
}

async function startLive(cfg) {
  const state = $('livestate'), btn = $('livebtn');
  const say = (msg, isErr = false) => { state.hidden = !msg; state.textContent = msg || ''; state.classList.toggle('err', isErr); };
  const input = { database: cfg.database, sql: cfg.sql };
  const footer = `Personal Garmin data, queried live from the ${cfg.database} database on ${cfg.server} through your connector. Refreshes every 15 minutes while the page is open.`;
  let shown = false;

  $('builtlbl').textContent = 'queried';
  $('footer').textContent = footer;
  say(`Loading the marts from ${cfg.server}…`);

  const show = result => {
    let D;
    try { D = livePayload(result); } catch (e) { say(`${cfg.server} returned an unexpected result: ${e.message}`, true); return; }
    renderPage({ ...D, goal: cfg.goal, profile: cfg.profile });
    $('footer').textContent = footer;
    shown = true;
    btn.hidden = true;
    say(result.cache?.revalidating ? 'Showing the last result while it refreshes…' : '');
  };

  let mcp = null;
  try { mcp = window.claude ? await window.claude.use('mcp') : null; } catch { mcp = null; }
  if (!mcp) { say(NO_CONNECTORS, true); return; }

  // A watch never asks for approval; this button makes the one call that may.
  btn.onclick = async () => {
    btn.disabled = true;
    try { show(await mcp.callTool(cfg.server, cfg.tool, input)); }
    catch (e) { say(liveMessage(e.code, cfg.server) || `The query failed (${e.code}): ${e.message}`, true); }
    finally { btn.disabled = false; }
  };

  mcp.watchTool(cfg.server, cfg.tool, input, ev => {
    if (ev.type === 'data') { show(ev.result); return; }
    const { code, message } = ev.error;
    if (RETRACT.has(code)) { clearPage(); shown = false; }
    btn.hidden = code !== 'approval_required';
    if (code === 'tool_error') say(`The query failed in ${cfg.server}: ${message}`, true);
    else say(liveMessage(code, cfg.server) || (shown ? `Refresh failed (${code}); showing the last result.` : `Could not load the marts (${code}): ${message}`), true);
  }, { cache: { staleTime: 5 * 60e3, gcTime: 24 * 3600e3 }, refetchInterval: REFRESH_MS });
}

if (window.__LIVE__) startLive(window.__LIVE__);
