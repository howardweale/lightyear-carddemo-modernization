/* Human decision surface. Credentials stay in memory, never browser storage. */
(() => {
  const byId = (id) => document.getElementById(id);
  const state = { token: null, session: null, items: [], runs: [], selected: null, enabled: false, busy: false, pendingWorkload: null };
  const node = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  const estateFor = (workload) => workload?.startsWith('cloudbank:') ? 'cloudbank' : workload?.startsWith('workload:carddemo-') ? 'carddemo' : null;
  const matchesEstate = (item) => window.LightyearContext.state.campaignId === 'retained' && estateFor(item.workload_id) === window.LightyearContext.state.estate;
  let authorityWorkload = null;
  const title = (value) => value.replaceAll('-', ' ').replace(/^./, (letter) => letter.toUpperCase());
  const message = (text, error = false) => {
    byId('decision-message').textContent = text;
    byId('decision-message').classList.toggle('decision-error', error);
  };
  async function request(path, payload) {
    const headers = { Accept: 'application/json' };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    if (payload !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(`/api/decisions/${path}`, { method: payload === undefined ? 'GET' : 'POST', headers, body: payload === undefined ? undefined : JSON.stringify(payload), cache: 'no-store', credentials: 'omit' });
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) throw new Error('Open the live Control Tower to use decisions. This copy has no decision API.');
    const result = await response.json();
    if (!response.ok) {
      if (response.status === 401 && path !== 'session') clearSession();
      throw new Error(result.error || 'The request could not be completed. Refresh before retrying.');
    }
    return result;
  }
  const PANELS = ['queue', 'run', 'convergence', 'discovery'];
  const WORKSPACES = { queue: 'decision-workspace', run: 'run-workspace', convergence: 'convergence-workspace', discovery: 'discovery-workspace' };
  function showPanel(panel = 'queue') {
    if (!PANELS.includes(panel)) panel = 'queue';
    PANELS.forEach((name) => {
      byId(WORKSPACES[name]).hidden = name !== panel;
      byId(`show-${name}`).setAttribute('aria-pressed', String(name === panel));
    });
    document.body.classList.toggle('decision-mode', panel === 'queue');
    document.body.classList.toggle('report-mode', panel === 'run' || panel === 'convergence');
    if (typeof window.updateGraphPresentation === 'function') window.updateGraphPresentation();
    if (panel === 'discovery' && typeof window.fitGraph === 'function') requestAnimationFrame(window.fitGraph);
    if (panel === 'run' && window.LightyearRun) window.LightyearRun.reload();
    if (panel === 'convergence' && window.LightyearConvergence) window.LightyearConvergence.reload();
  }
  function showQueue(show = true) { showPanel(show ? 'queue' : 'discovery'); }
  function sessionChrome() {
    byId('operator-session-label').textContent = state.session ? `${state.session.actor.name} · session ends ${new Date(state.session.expires_at).toLocaleTimeString()}` : 'No operator session';
    byId('operator-sign-in').hidden = !!state.session;
    byId('operator-sign-out').hidden = !state.session;
    byId('download-session').disabled = !state.session;
  }
  function clearSession() {
    state.token = null; state.session = null; state.selected = null; state.items = []; state.runs = [];
    byId('decision-items').replaceChildren(); byId('decision-runs').replaceChildren(); byId('decision-events').replaceChildren();
    byId('decision-detail').replaceChildren(node('h2', 'Sign in to review and decide'));
    byId('decision-count').textContent = ''; sessionChrome();
  }
  function renderItems() {
    if (window.LightyearContext.state.campaignId !== 'retained') {
      byId('decision-count').textContent = '';
      byId('decision-items').replaceChildren(node('p', 'Use the campaign authorization above to accept database execution terms. Normalization approvals belong to the retained estate workflow.', 'decision-empty'));
      return;
    }
    const scoped = state.items.filter(matchesEstate);
    const pending = scoped.filter((item) => item.status !== 'approved');
    byId('decision-count').textContent = String(pending.length);
    const filter = byId('decision-filter').value;
    const items = scoped.filter((item) => filter === 'all' || (filter === 'approved' ? item.status === 'approved' : item.status !== 'approved'));
    const container = byId('decision-items'); container.replaceChildren();
    if (!items.length) container.append(node('p', filter === 'pending' ? 'No normalization decisions are waiting. Approved entries remain available under All normalizations.' : 'No entries match this view.', 'decision-empty'));
    for (const item of items) {
      const button = node('button', undefined, 'decision-card'); button.type = 'button';
      button.classList.toggle('selected', state.selected?.id === item.id);
      button.setAttribute('aria-pressed', String(state.selected?.id === item.id));
      button.append(node('span', title(item.status), `decision-badge ${item.status}`), node('strong', title(item.id)), node('span', item.workload_name), node('small', `Review by ${item.rule.review_after}`));
      button.addEventListener('click', () => review(item.id)); container.append(button);
    }
  }
  function detailField(list, label, text) {
    const row = node('div'); row.append(node('dt', label), node('dd', text)); list.append(row);
  }
  function decisionTrace(record, status) {
    const section = node('section', undefined, 'decision-trace');
    section.append(node('h3', `Recorded decision · ${title(status)}`));
    const list = node('dl');
    detailField(list, 'Decided by', record.actor.name);
    detailField(list, 'When', new Date(record.occurred_at).toLocaleString());
    detailField(list, 'Owner', record.payload.owner);
    detailField(list, 'Reason', record.payload.reason);
    detailField(list, 'Review date', record.payload.review_after || 'Rejected — no approval granted');
    section.append(list, node('small', `Signed record ${record.content_sha256.slice(0, 16)}…`)); return section;
  }
  async function review(id) {
    const estate = window.LightyearContext.state.estate;
    try {
      const item = await request('review', { entry_id: id });
      if (estate !== window.LightyearContext.state.estate || !matchesEstate(item)) return;
      state.selected = item; renderItems(); renderDetail(item);
      message(`Reviewing ${title(item.id)}. This evidence view is recorded in your session.`);
    } catch (error) { message(error.message, true); }
  }
  function renderDetail(item) {
    const container = byId('decision-detail'); container.replaceChildren();
    container.append(node('p', item.workload_name, 'decision-eyebrow'), node('h2', title(item.id)));
    const evidence = node('dl', undefined, 'decision-evidence');
    detailField(evidence, 'Scope', item.rule.scope);
    detailField(evidence, 'Allowed difference', item.rule.behavior);
    detailField(evidence, 'Ledger rationale', item.rule.reason);
    detailField(evidence, 'Current ledger owner', item.rule.owner);
    detailField(evidence, 'Ledger review date', item.rule.review_after);
    container.append(evidence);
    const binding = node('details'); binding.append(node('summary', 'Evidence binding'));
    binding.append(node('p', item.ledger_path || 'spec/comparison-normalizations.json'), node('code', `Entry ${item.entry_sha256}`), node('code', `Ledger ${item.ledger_sha256}`)); binding.append(node('pre', JSON.stringify(item.rule, null, 2))); container.append(binding);
    if (item.latest_decision) container.append(decisionTrace(item.latest_decision, item.status));
    const form = node('form', undefined, 'normalization-form');
    form.append(node('h3', item.latest_decision ? 'Record a new decision' : 'Own the decision'));
    const reasonLabel = node('label', 'Why is this acceptable, or why should it be rejected?'); reasonLabel.htmlFor = 'normalization-reason';
    const reason = node('textarea'); reason.id = 'normalization-reason'; reason.required = true; reason.maxLength = 2000; reason.rows = 3;
    const ownerLabel = node('label', 'Named owner'); ownerLabel.htmlFor = 'normalization-owner';
    const owner = node('input'); owner.id = 'normalization-owner'; owner.required = true; owner.maxLength = 200; owner.value = state.session.actor.name;
    const dateLabel = node('label', 'Review date (approval expires at 00:00 UTC)'); dateLabel.htmlFor = 'normalization-review-date';
    const expiry = node('input'); expiry.id = 'normalization-review-date'; expiry.type = 'date';
    const tomorrow = new Date(); tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
    expiry.min = tomorrow.toISOString().slice(0, 10);
    const max = new Date(); max.setUTCDate(max.getUTCDate() + 366); expiry.max = [max.toISOString().slice(0, 10), item.rule.review_after].sort()[0];
    const buttons = node('div', undefined, 'decision-actions');
    const approve = node('button', 'Approve and sign', 'primary-button'); approve.type = 'submit'; approve.value = 'approved';
    const reject = node('button', 'Reject and sign', 'secondary-button'); reject.type = 'submit'; reject.value = 'rejected';
    buttons.append(approve, reject); form.append(reasonLabel, reason, ownerLabel, owner, dateLabel, expiry, node('p', `Signed for ${state.session.actor.name} by the Control Tower decision service.`, 'decision-signing-note'), buttons);
    if (!state.session.roles.includes('normalization-approver')) { approve.disabled = true; reject.disabled = true; }
    let retryPayload = null;
    form.addEventListener('submit', async (event) => {
      event.preventDefault(); if (state.busy) return;
      if (!matchesEstate(item)) { message('The selected estate changed. Review its decision before signing.', true); return; }
      const outcome = event.submitter?.value || 'approved';
      if (outcome === 'approved' && !expiry.value) { expiry.focus(); message('Choose a review date before approving.', true); return; }
      const values = { entry_id: item.id, entry_sha256: item.entry_sha256, ledger_sha256: item.ledger_sha256, previous_decision_sha256: item.latest_decision?.content_sha256 || null, outcome, reason: reason.value, owner: owner.value, review_after: expiry.value || null };
      const payload = retryPayload && JSON.stringify(retryPayload.values) === JSON.stringify(values) ? retryPayload.payload : { ...values, request_id: crypto.randomUUID() };
      retryPayload = { values, payload };
      state.busy = true; approve.disabled = true; reject.disabled = true;
      try {
        const record = await request('approve', payload);
        await refresh(); await review(item.id);
        message(`${title(outcome)} by ${record.actor.name}. The signed decision is now in the audit trail.`);
      } catch (error) { message(error.message, true); approve.disabled = false; reject.disabled = false; }
      finally { state.busy = false; }
    });
    container.append(form);
  }
  function download(value, filename) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + '\n'], { type: 'application/json' }));
    const anchor = node('a'); anchor.href = url; anchor.download = filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function renderRuns() {
    const container = byId('decision-runs'); container.replaceChildren();
    if (window.LightyearContext.state.estate !== 'carddemo') return;
    if (!state.runs.length) container.append(node('p', 'No historical proof is recorded here. The headless engine owns new proof runs.', 'decision-empty'));
    for (const run of state.runs.slice(0, 10)) {
      const card = node('article', undefined, 'decision-run');
      card.append(node('strong', `INTCALC · ${title(run.status)}`), node('small', `${run.run_id} · Local reference proof`));
      card.append(node('p', 'Historical journal state. Current execution health and qualification must be checked against engine receipts.'));
      container.append(card);
    }
  }
  function renderEvents(events) {
    const container = byId('decision-events'); container.replaceChildren();
    for (const event of [...events].reverse().filter(event => window.LightyearContext.state.campaignId === 'retained' && estateFor(event.payload.workload_id || authorityWorkload) === window.LightyearContext.state.estate)) {
      const line = node('article', undefined, 'decision-event');
      line.append(node('strong', `${event.actor.name} · ${title(event.kind.replaceAll('_', '-'))}`), node('span', new Date(event.occurred_at).toLocaleString()));
      if (event.payload.entry_id) line.append(node('span', title(event.payload.entry_id)));
      if (event.payload.reason) line.append(node('p', event.payload.reason));
      container.append(line);
    }
  }
  let refreshing = false;
  async function refresh() {
    if (!state.token || refreshing) return;
    refreshing = true;
    const estate = window.LightyearContext.state.estate;
    try {
      const result = await request('queue');
      if (estate !== window.LightyearContext.state.estate) return;
      state.items = result.items; state.runs = result.runs;
      renderItems(); renderEvents(result.events); await renderRuns();
    } catch (error) { message(error.message, true); }
    finally {
      refreshing = false;
      if (estate !== window.LightyearContext.state.estate) refresh();
    }
  }
  async function openProof(workloadId) {
    showQueue();
    if (!state.enabled) { message('Start the local decision service to view the decision journal.', true); return; }
    if (workloadId !== 'workload:carddemo-intcalc') { message('This journal has historical INTCALC proofs only. See the engine action plan for other estates.'); return; }
    if (!state.token) { state.pendingWorkload = workloadId; byId('operator-dialog').showModal(); return; }
    await refresh(); byId('decision-runs').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    message('Viewing historical proofs. The Control Tower cannot dispatch work.');
  }
  window.controlTowerDecisions = { openProof, showQueue, showPanel };
  PANELS.forEach((panel) => byId(`show-${panel}`).addEventListener('click', () => showPanel(panel)));
  byId('refresh-decisions').addEventListener('click', refresh);
  byId('decision-filter').addEventListener('change', renderItems);
  byId('operator-sign-in').addEventListener('click', () => { byId('operator-error').textContent = ''; byId('operator-dialog').showModal(); });
  byId('cancel-operator').addEventListener('click', () => { state.pendingWorkload = null; byId('operator-dialog').close(); byId('operator-credential').value = ''; });
  byId('operator-dialog').addEventListener('cancel', () => { state.pendingWorkload = null; byId('operator-credential').value = ''; });
  byId('operator-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = event.submitter; button.disabled = true;
    try {
      const session = await request('session', { credential: byId('operator-credential').value });
      state.token = session.token; delete session.token; state.session = session;
      byId('operator-credential').value = ''; byId('operator-dialog').close(); sessionChrome();
      message(`Signed in as ${session.actor.name}. Select an entry to review the evidence.`); await refresh();
      if (state.pendingWorkload) { const workload = state.pendingWorkload; state.pendingWorkload = null; await openProof(workload); }
    } catch (error) { byId('operator-error').textContent = error.message; }
    finally { button.disabled = false; }
  });
  byId('operator-sign-out').addEventListener('click', async () => {
    try { await request('logout', {}); clearSession(); message('Session ended. Its signed audit trail is retained.'); }
    catch (error) { message(error.message, true); }
  });
  byId('download-session').addEventListener('click', async () => {
    try { download(await request('session-export'), `control-tower-session-${state.session.id}.json`); }
    catch (error) { message(error.message, true); }
  });
  function contextChanged() {
    state.selected = null;
    byId('decision-detail').replaceChildren(node('h2', 'Select and review a decision for this estate'));
    byId('decision-events').replaceChildren(); byId('decision-runs').replaceChildren();
    renderItems();
    byId('operator-sign-in').disabled = !state.enabled || (window.LightyearContext.state.campaignId !== 'retained' || estateFor(authorityWorkload) !== window.LightyearContext.state.estate);
    if (window.LightyearContext.state.campaignId !== 'retained') message('Campaign authorization uses its own operator credential above. Existing normalization approvals do not authorize database execution or spending.');
    else if (state.enabled && (window.LightyearContext.state.campaignId !== 'retained' || estateFor(authorityWorkload) !== window.LightyearContext.state.estate)) message('The configured decision authority belongs to another estate. Selecting an estate does not grant signing authority.');
    else if (state.enabled) message('Review the selected estate decision. Approvals are current authority, not a historical run status.');
    refresh();
  }
  document.addEventListener('tower-context-change', contextChanged);
  showQueue(); sessionChrome();
  request('status').then((status) => { state.enabled = status.enabled; authorityWorkload = status.workload_id; message(status.message, !status.enabled); contextChanged(); }).catch((error) => { byId('operator-sign-in').disabled = true; message(error.message, true); });
  setInterval(() => { if (state.token) refresh(); }, 30000);
})();
