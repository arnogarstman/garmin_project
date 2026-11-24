// Energy balance (Nutrition tab): Garmin's measured burn against the intake the weight trend implies.
// D.balance (marts.fct_energy_balance) holds, per week, the 28-day average burn, the weight trend
// over the same days and burn plus the trend at 7700 kcal per kg: what you must have eaten if
// Garmin's burn is right. Garmin does not log what you eat, so the page asks: what you say you eat
// on a typical day (settings/energy) turns the trend into your real burn, and so into how far off
// Garmin's figure is for you. That correction can feed the meal plan's rest-day burn (meals.js
// calls energyCorrection()). renderPage() calls renderEnergy().
const ENERGY_DOC = 'settings/energy';
const MAX_CORRECTION = 0.2; // the largest share of Garmin's burn a correction may move it
let energySetting = null;
const energy = { canWrite: false, ready: false };

// The latest week with an implied intake, or null.
const latestBalance = D => [...(D.balance || [])].reverse().find(r => num(r.intake) && num(r.burn)) || null;

// What the stated intake says about Garmin's burn: kcal a day to add to it (clamped), and whether
// the meal plan should use it. Null without a stated intake or a weight trend.
function energyCorrection(D) {
  const b = latestBalance(D), s = energySetting;
  if (!b || !s || !num(s.intake_kcal)) return null;
  const actual = s.intake_kcal - b.bal, raw = actual - b.burn, cap = b.burn * MAX_CORRECTION;
  const offset = Math.max(-cap, Math.min(cap, raw));
  return { actual, raw, offset, clamped: offset !== raw, pct: raw / b.burn, apply: !!s.apply, b };
}

function renderEnergy(D) {
  const rows = (D.balance || []).map(r => ({ ...r, d: dayIso(r.d) })), b = latestBalance(D);
  const tile = (k, v, s) => `<div class="tile"><span class="eyebrow">${k}</span><span class="v">${v}</span><span class="s">${s}</span></div>`;
  if (!b) {
    empty('energykpis', 'Needs 3 weeks of Garmin burn and 6 weigh-ins spread over at least 2 of the last 4 weeks.');
    for (const id of ['ch-energy', 'cap-energy', 'leg-energy']) $(id).textContent = '';
    renderEnergyForm(D);
    return;
  }
  const c = energyCorrection(D);
  $('energykpis').innerHTML = `<div class="tiles">${[
    tile('Garmin burn', `${kcalFmt(b.burn)}<small>kcal/day</small>`, 'Average of the last 4 weeks'),
    tile('Weight trend', `${signed(b.kg_wk, 2)}<small>kg/wk</small>`, `${b.weigh_ins} weigh-ins in 4 weeks`),
    tile('Balance', `${signed(b.bal, 0)}<small>kcal/day</small>`, b.bal < 0 ? 'A deficit, from the weight trend' : 'A surplus, from the weight trend'),
    tile('Implied intake', `${kcalFmt(b.intake)}<small>kcal/day</small>`, 'If Garmin\'s burn is right'),
    c ? tile('Real burn', `${kcalFmt(c.actual)}<small>kcal/day</small>`, `From what you eat: Garmin ${c.raw >= 0 ? 'under' : 'over'}counts by ${kcalFmt(Math.abs(c.raw))} (${Math.abs(c.pct * 100).toFixed(0)}%)`) : '',
  ].join('')}</div>`;

  // Burn and implied intake per week.
  const P = rows.filter(r => num(r.burn));
  if (P.length >= 2) {
    const ys = P.flatMap(r => [r.burn, r.intake]).concat(c ? [energySetting.intake_kcal] : []).filter(num);
    const f = frame({ x0: t(P[0].d), x1: t(P[P.length - 1].d), yTicks: niceTicks(Math.min(...ys) - 100, Math.max(...ys) + 100, 4), fmtY: v => v.toLocaleString('en-GB'), W: wideW(), H: 240 });
    const burnPts = P.map(r => [t(r.d), r.burn]), inPts = P.map(r => [t(r.d), r.intake]);
    let s = f.s;
    if (c) s += `<line x1="${f.L}" x2="${f.W - f.R}" y1="${f.Y(energySetting.intake_kcal)}" y2="${f.Y(energySetting.intake_kcal)}" stroke="${css('c5')}" stroke-dasharray="5 4"/>`;
    s += `<path d="${path(burnPts, f.X, f.Y)}" fill="none" stroke="${css('c1')}" stroke-width="2"/><path d="${path(inPts, f.X, f.Y)}" fill="none" stroke="${css('c3')}" stroke-width="2"/>`;
    for (const r of P) {
      s += `<circle class="mark" cx="${f.X(t(r.d))}" cy="${f.Y(r.burn)}" r="3" fill="${css('c1')}" tabindex="0"${tipAttr(`${kcalFmt(r.burn)} kcal burned`, `4 weeks to ${fmtDate(r.d)}, Garmin`)}/>`;
      if (num(r.intake)) s += `<circle class="mark" cx="${f.X(t(r.d))}" cy="${f.Y(r.intake)}" r="3" fill="${css('c3')}" tabindex="0"${tipAttr(`${kcalFmt(r.intake)} kcal eaten`, `4 weeks to ${fmtDate(r.d)}, implied by ${signed(r.kg_wk, 2)} kg a week`)}/>`;
    }
    $('ch-energy').innerHTML = s + '</svg>';
    bindTips($('ch-energy'));
  } else empty('ch-energy', 'Needs two weeks of data.');
  $('leg-energy').innerHTML = `<span><b style="background:var(--c1)"></b>Garmin burn</span><span><b style="background:var(--c3)"></b>Intake the weight trend implies</span>${c ? '<span><b style="background:var(--c5)"></b>What you say you eat</span>' : ''}`;
  $('cap-energy').textContent = `Each point covers the 4 weeks up to it. Where the orange line sits below the blue, the scale says you ate less than Garmin says you burned. If you eat close to the same every day and the gap stays put while Garmin's burn moves, Garmin's estimate is what is off. 7700 kcal per kg is an average: early in a diet, water makes the weight trend overstate the deficit.`;
  renderEnergyForm(D);
}

// What you eat: shown and edited by whoever may write settings; read-only otherwise.
let energyEditing = false;
function renderEnergyForm(D) {
  const box = $('energyform'), s = energySetting, c = energyCorrection(D);
  if (!energy.ready) { box.innerHTML = '<p class="cap">On the published page you can enter what you eat on a typical day, to see how far off Garmin\'s burn is and correct the meal plan with it.</p>'; return; }
  if (!energyEditing) {
    const edit = energy.canWrite ? `<div class="btns"><button type="button" id="energy-edit">${s ? 'Change' : 'Enter what you eat'}</button></div>` : '';
    box.innerHTML = s && num(s.intake_kcal)
      ? `<span class="eyebrow">What you eat</span><h3>About ${kcalFmt(s.intake_kcal)} kcal a day</h3>` +
        (c ? `<p>With your weight at ${signed(c.b.kg_wk, 2)} kg a week, you burn about ${kcalFmt(c.actual)} kcal a day: Garmin's ${kcalFmt(c.b.burn)} is ${kcalFmt(Math.abs(c.raw))} kcal ${c.raw >= 0 ? 'low' : 'high'}. ${c.apply ? `The meal plan adds ${signed(c.offset, 0)} kcal to Garmin's rest-day burn${c.clamped ? ` (held to ${MAX_CORRECTION * 100}% of it)` : ''}.` : 'The meal plan still uses Garmin\'s burn as is.'}</p>` : '<p>Needs a weight trend before it says anything about Garmin\'s burn.</p>') + edit
      : `<p class="cap">Garmin does not know what you eat. Enter a typical day's intake to see how far off its burn is for you.</p>${edit}`;
    const btn = $('energy-edit');
    if (btn) btn.onclick = () => { energyEditing = true; renderEnergyForm(D); };
    return;
  }
  box.innerHTML = `<span class="eyebrow">What you eat on a typical day</span><form id="energy-f" novalidate>
    <label>Intake (kcal a day)<input name="intake_kcal" type="number" step="10" min="1000" max="6000" required value="${num(s?.intake_kcal) ? s.intake_kcal : ''}"></label>
    <label style="flex-direction:row;align-items:center;gap:8px;grid-column:1/-1;text-transform:none;letter-spacing:0;font:.9rem var(--body);color:var(--ink2)"><input name="apply" type="checkbox" style="width:auto"${s?.apply ? ' checked' : ''}> Correct the meal plan's burn with it</label>
    <div class="btns"><button type="submit" class="primary">Save</button><button type="button" id="energy-cancel">Cancel</button>${s ? '<button type="button" id="energy-clear">Remove</button>' : ''}</div>
  </form><p class="cap">Your average over the last 4 weeks, as honestly as you can; a food log for a week or two gives the best number.</p>`;
  const f = $('energy-f');
  f.onsubmit = async e => {
    e.preventDefault();
    const kcal = Number(new FormData(f).get('intake_kcal'));
    if (!(kcal >= 1000 && kcal <= 6000)) { f.querySelector('input').setCustomValidity('Between 1000 and 6000'); f.reportValidity(); return; }
    f.querySelector('button[type=submit]').disabled = true;
    try {
      await energy.ref.set({ intake_kcal: Math.round(kcal), apply: f.elements.apply.checked, updated_at: new Date().toISOString() });
      energyEditing = false;
    } catch (err) {
      if (err.code === 'invalid_argument' || err.code === 'permission_denied') energy.canWrite = false;
      energyEditing = false;
    }
    rerender();
  };
  $('energy-cancel').onclick = () => { energyEditing = false; renderEnergyForm(D); };
  const clear = $('energy-clear');
  if (clear) clear.onclick = async () => { clear.disabled = true; try { await energy.ref.delete(); } catch { /* shown as it was */ } energyEditing = false; rerender(); };
}

async function startEnergy() {
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  if (typeof db?.doc !== 'function') return;
  try { user = await window.claude.use('user'); } catch { user = null; }
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  energy.canWrite = canWrite !== false;
  energy.ref = db.doc(ENERGY_DOC);
  energy.ready = true;
  energy.ref.onSnapshot(snap => {
    const v = snap.exists ? snap.data() : null;
    energySetting = v && num(v.intake_kcal) ? v : null;
    rerender();
  }, () => { energy.ready = false; rerender(); });
}

startEnergy();
