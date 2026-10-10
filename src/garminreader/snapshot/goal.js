// The race goal form. The race lives in the artifact's own database (the `db` capability, document
// settings/race), so it survives reloads and new versions of the page; every change re-renders the
// page through rerender(). Without the capability (a local snapshot file) the form stays hidden and
// the dashboard's goal file, if any, is used.
const GOAL_DOC = 'settings/race';

async function startGoal() {
  const box = $('goalform');
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  if (typeof db?.doc !== 'function') return;
  try { user = await window.claude.use('user'); } catch { user = null; }
  // The page's rules let editors and the owner write the race; others see it read-only.
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  const ref = db.doc(GOAL_DOC);
  let current = null, editing = false, readOnly = canWrite === false;

  const summary = () => {
    const g = current, r = g && RACES[g.distance];
    if (!g) {
      box.innerHTML = readOnly ? '<p class="cap">No race set yet.</p>' : '<p class="cap">No race set yet.</p><div class="btns"><button type="button" class="primary" id="goal-edit">Set your race</button></div>';
    } else {
      box.innerHTML = `<span class="eyebrow">Your race</span><h3>${esc(g.race || r?.label || 'Race')}</h3>` +
        `<p>${[r?.label, g.event_date && `${fmtDate(g.event_date)} ${new Date(t(g.event_date)).getFullYear()}`, g.target && `target ${esc(g.target)}`].filter(Boolean).join(' · ')}</p>` +
        (readOnly ? '' : '<div class="btns"><button type="button" id="goal-edit">Change race</button></div>');
    }
    const edit = $('goal-edit');
    if (edit) edit.onclick = () => { editing = true; form(); };
  };

  const form = (msg = '') => {
    const g = current || {};
    const opts = Object.entries(RACES).map(([k, r]) => `<option value="${k}"${(g.distance || 'half') === k ? ' selected' : ''}>${r.label}</option>`).join('');
    box.innerHTML = `<span class="eyebrow">${current ? 'Change your race' : 'Set your race'}</span><form id="goal-f" novalidate>
      <label>Race<input name="race" maxlength="60" placeholder="e.g. Rotterdam Half" value="${esc(g.race || '')}"></label>
      <label>Distance<select name="distance">${opts}</select></label>
      <label>Race day<input name="event_date" type="date" required value="${esc(g.event_date || '')}"></label>
      <label>Target time (optional)<input name="target" inputmode="numeric" placeholder="h:mm:ss" value="${esc(g.target || '')}"></label>
      <div class="btns"><button type="submit" class="primary">Save</button>${current ? '<button type="button" id="goal-cancel">Cancel</button><button type="button" id="goal-clear">Remove race</button>' : ''}</div>
    </form>${msg ? `<p class="msg">${esc(msg)}</p>` : ''}`;
    const f = $('goal-f');
    f.onsubmit = async e => {
      e.preventDefault();
      const v = Object.fromEntries(new FormData(f));
      const race = v.race.trim(), target = v.target.trim();
      if (!/^\d{4}-\d{2}-\d{2}$/.test(v.event_date)) { form('Pick the race day.'); return; }
      if (target && parseTarget(target, v.distance) === null) { form('Write the target as h:mm:ss, for example 1:45:00.'); return; }
      f.querySelector('button[type=submit]').disabled = true;
      try {
        await ref.set({ race, distance: v.distance, event_date: v.event_date, target, updated_at: new Date().toISOString() });
        editing = false;
        summary();
      } catch (err) {
        if (err.code === 'invalid_argument') { readOnly = true; editing = false; summary(); return; }
        form(err.code === 'quota_exceeded' ? 'The page storage is full.' : 'Saving failed; try again in a moment.');
      }
    };
    const cancel = $('goal-cancel'), clear = $('goal-clear');
    if (cancel) cancel.onclick = () => { editing = false; summary(); };
    if (clear) clear.onclick = async () => {
      clear.disabled = true;
      try { await ref.delete(); editing = false; summary(); } catch { form('Removing failed; try again in a moment.'); }
    };
  };

  ref.onSnapshot(snap => {
    current = snap.exists ? snap.data() : null;
    pageGoal = current;
    // Keep a form that is being filled in: snapshots also arrive while nothing changed.
    if (!editing) { if (current || readOnly) summary(); else { editing = true; form(); } }
    rerender();
  }, () => { box.innerHTML = '<p class="cap">The saved race could not be loaded on this view.</p>'; });
}

startGoal();
