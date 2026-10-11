// Tabs: the sections grouped by what you come for (today, training, nutrition, history, about).
// Every tab renders all the time, so switching only shows another panel. The open tab is in the
// address (#training) and remembered in this browser, for a reload or the next visit.
const TAB_KEY = 'garminreader.tab';

function startTabs() {
  const tabs = [...document.querySelectorAll('.tabs [role=tab]')];
  const names = tabs.map(b => b.dataset.tab);
  const show = (name, focus = false) => {
    if (!names.includes(name)) name = names[0];
    for (const b of tabs) {
      const on = b.dataset.tab === name;
      b.setAttribute('aria-selected', on);
      b.tabIndex = on ? 0 : -1;
      $(b.getAttribute('aria-controls')).hidden = !on;
      if (on && focus) b.focus();
    }
    try { localStorage.setItem(TAB_KEY, name); } catch { /* storage blocked: the hash still works */ }
    if (location.hash.slice(1) !== name) history.replaceState(null, '', `#${name}`);
  };
  for (const b of tabs) b.onclick = () => { show(b.dataset.tab); scrollTo({ top: 0 }); };
  // Arrow keys move between tabs, as in any tab list.
  document.querySelector('.tabs').onkeydown = e => {
    const i = tabs.indexOf(document.activeElement), step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (i < 0 || !step) return;
    e.preventDefault();
    show(names[(i + step + names.length) % names.length], true);
  };
  addEventListener('hashchange', () => show(location.hash.slice(1)));
  let saved = null;
  try { saved = localStorage.getItem(TAB_KEY); } catch { saved = null; }
  show(location.hash.slice(1) || saved || names[0]);
}

startTabs();
