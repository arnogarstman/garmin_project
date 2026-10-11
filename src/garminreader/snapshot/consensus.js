// Consensus: Claude weighs this page's plan against Garmin Coach's for the coming days and says, per
// day, which session to do and why, from the athlete's own data. Asked on a click (the `sample`
// capability) and kept in the artifact's database (settings/consensus) with the inputs it answered,
// so it is never asked again on a visit, and marked out of date when either plan or the data changes.
// plan.js gathers the inputs (consensusInput) and draws the column (consensusCell).
const CONSENSUS_DOC = 'settings/consensus';
const PICKS = { garmin: ['Garmin Coach', 'c3'], page: ['This page', 'c1'], blend: ['Blend', 'c5'], rest: ['Rest', 'muted'] };
const cons = { sample: null, ref: null, canWrite: false, saved: null, busy: null, error: '', input: null, ctl: null };

// What the consensus answers: today on, every day Garmin Coach has scheduled (it shares one week),
// each with both sessions, plus the numbers a coach would weigh. `key` identifies the question.
function consensusInput(plan, ctx, planDay) {
  const { G, st, sig } = ctx, today = iso(new Date(sig.x1));
  const coachDays = [...new Set((lastD?.coach || []).map(c => String(c.d).slice(0, 10)).filter(d => d >= today))].sort();
  if (!coachDays.length) return null;
  const last = coachDays[coachDays.length - 1], days = [];
  for (let d = new Date(t(today)); iso(d) <= last && days.length < 8; d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1)) {
    const date = iso(d), s = planDay(date);
    const garmin = coachOn(date).map(c => [c.name, num(c.min) && c.min > 0 ? `${Math.round(c.min)} min` : '', c.description, lower(c.effect)].filter(Boolean).join(', '));
    days.push({ date, weekday: DOW[(d.getDay() + 6) % 7], page: s ? `${s.title}, ${Math.round(s.km)} km: ${s.detail}` : 'Rest', garmin: garmin.join('; ') || 'Rest' });
  }
  const fmt = (v, dgt = 0) => num(v) ? v.toFixed(dgt) : 'unknown';
  const context = {
    goal: G ? `${G.name}${G.date ? ` on ${G.date}` : ''}${G.target ? `, target ${G.target}` : ''}` : 'no race set',
    predictedHalf: num(st.predicted_half_marathon_s) ? hms(st.predicted_half_marathon_s) : 'unknown',
    recoveryToday: sig.recovery || 'unknown',
    hrv: num(sig.hrvToday) ? `${sig.hrvToday} ms last night against a normal of ${fmt(sig.hrvNormal)}` : 'unknown',
    loadRatio: num(st.acwr) ? `${st.acwr.toFixed(2)} (acute to chronic)` : 'unknown',
    lastWeekKm: fmt(sig.wk ? sig.wk(1) : null, 1),
    longestRecentRunKm: fmt(sig.longest, 1),
    runsPerWeek: fmt(sig.runsPerWeek, 1),
    easyShare: num(sig.easyShare) ? `${sig.easyShare.toFixed(0)}% of running time in zones 1-2 over 4 weeks` : 'unknown',
  };
  return { days, context, key: JSON.stringify({ days, context }) };
}

function consensusPrompt(input) {
  const lines = input.days.map(d => `- ${d.date} ${d.weekday}\n  This page's plan: ${d.page}\n  Garmin Coach: ${d.garmin}`).join('\n');
  const ctx = Object.entries(input.context).map(([k, v]) => `- ${k}: ${v}`).join('\n');
  return `You are an experienced running coach settling the differences between two training plans for the same athlete, day by day.

"This page's plan" is rule-based: built from the athlete's recent weekly volume, runs per week, longest run and Garmin's race predictions, in phases toward the goal. "Garmin Coach" is Garmin's adaptive plan, which adjusts to the athlete's runs and recovery. Neither is right by default.

For each day, choose what the athlete should do: "garmin" (Garmin Coach's session), "page" (this page's session), "blend" (a session that combines them, say exactly what), or "rest". Agree with both plans where they agree. Where they differ, decide on what serves the goal and the athlete's current state: recovery today, the load ratio, the week's balance of hard and easy days (no two hard days in a row, long run protected), and volume close to recent weeks. Argue each choice in one or two sentences, citing the numbers below. Write plainly, no jargon.

The athlete:
${ctx}

The days:
${lines}

Reply with only JSON in this shape:
{"summary":"Two sentences on how the plans differ this week and what the consensus does about it.","days":[{"date":"YYYY-MM-DD","pick":"garmin","workout":"The session to do, concrete: distance or time and pace.","why":"One or two sentences."}]}
One entry in "days" for each day above, in order.`;
}

// The bar above the week: the button, progress, errors, and how current the saved answer is.
function consensusBar(input) {
  const saved = cons.saved, current = saved && input && saved.key === input.key;
  const can = cons.sample && cons.canWrite && input;
  if (cons.busy) return `<div class="cbar"><p class="livestate" role="status">${esc(cons.busy)}</p><button type="button" class="livebtn" id="cons-stop">Stop</button></div>`;
  const msg = !input ? 'The consensus needs Garmin Coach workouts from today on.'
    : !saved ? 'Let Claude compare both coaches for the coming days and pick per day.'
      : current ? `Consensus from ${fmtDate(saved.generated_at)} at ${new Date(saved.generated_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}.`
        : 'A plan or your data changed since the last consensus; ask again for days that match.';
  const summary = current && saved.result?.summary ? `<p class="csum">${esc(saved.result.summary)}</p>` : '';
  const btn = can ? `<button type="button" class="livebtn" id="cons-make">${saved ? 'Ask Claude again' : 'Ask Claude for a consensus'}</button>` : '';
  const err = cons.error ? `<p class="mmsg">${esc(cons.error)}</p>` : '';
  return `<div class="cbar">${summary}<p class="cap">${msg}${saved && !current && input ? ' <span class="pill warn">out of date</span>' : ''}</p>${btn}${err}</div>`;
}

// One day's verdict, from the saved answer; marked when it answered a different question.
function consensusCell(date) {
  const saved = cons.saved, day = saved?.result?.days?.find(d => d?.date === date);
  if (!day) return '<p class="cap">–</p>';
  const [label, color] = PICKS[day.pick] || ['Pick', 'muted'];
  const stale = cons.input && saved.key !== cons.input.key;
  return `<div class="cday${stale ? ' stale' : ''}"><span class="pill" style="color:var(--ink);background:color-mix(in srgb,var(--${color}) 22%,transparent)">${esc(label)}</span>` +
    `<p class="cwork">${esc(day.workout)}</p><p>${esc(day.why)}</p></div>`;
}

function bindConsensus() {
  const make = $('cons-make'), stop = $('cons-stop');
  if (make) make.onclick = makeConsensus;
  if (stop) stop.onclick = () => cons.ctl?.abort();
}

async function makeConsensus() {
  const input = cons.input;
  if (!input || !cons.sample) return;
  cons.ctl = new AbortController();
  cons.error = '';
  cons.busy = 'Claude is comparing both coaches. This usually takes under a minute.';
  rerender();
  try {
    const result = await cons.sample.json(consensusPrompt(input), { signal: cons.ctl.signal, cache: false });
    if (!Array.isArray(result?.days) || !result.days.every(d => typeof d?.date === 'string' && typeof d.workout === 'string')) throw { code: 'invalid_json' };
    const doc = { generated_at: new Date().toISOString(), key: input.key, result };
    cons.saved = doc;
    try { await cons.ref.set(doc); } catch (e) { cons.error = e.code === 'quota_exceeded' ? 'The page storage is full; the consensus is shown but not saved.' : 'The consensus could not be saved; it is shown until you leave the page.'; }
  } catch (e) {
    cons.error = {
      cancelled: '',
      not_granted: 'Claude is not allowed for this page; allow it from the page\'s Permissions menu.',
      rate_limited: 'Claude is busy or your usage limit is reached; try again later.',
      invalid_json: 'Claude\'s answer was not usable; try again.',
      refused: 'Claude declined to answer; try again later.',
    }[e.code] ?? 'Asking Claude failed; try again in a moment.';
    if (['not_granted', 'sampling_disabled', 'not_declared', 'capability_disabled', 'capability_removed'].includes(e.code)) cons.sample = null;
  } finally {
    cons.busy = null;
    rerender();
  }
}

async function startConsensus() {
  let db = null, user = null;
  try { db = window.claude ? await window.claude.use('db') : null; } catch { db = null; }
  try { cons.sample = window.claude ? await window.claude.use('sample') : null; } catch { cons.sample = null; }
  if (typeof db?.doc !== 'function') { cons.sample = null; return; }
  try { user = await window.claude.use('user'); } catch { user = null; }
  const canWrite = typeof user?.canEdit === 'function' ? await user.canEdit().catch(() => null) : null;
  cons.canWrite = canWrite !== false;
  cons.ref = db.doc(CONSENSUS_DOC);
  cons.ref.onSnapshot(snap => {
    if (cons.busy) return;
    cons.saved = snap.exists ? snap.data() : null;
    rerender();
  }, () => { cons.error = 'The saved consensus could not be loaded on this view.'; rerender(); });
}

startConsensus();
