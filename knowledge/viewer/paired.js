/* Operator intent is signed by the service; only the detached engine runs SQL. */
(() => {
  const controls = document.getElementById('campaign-controls');
  const node = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  };
  let token = null, proposed = null, sequence = 0, pendingRequest = null, pendingPayload = null;
  async function api(path, body) {
    const headers = { Accept: 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(`/api/campaign/${path}`, { method: body === undefined ? 'GET' : 'POST', headers,
      body: body === undefined ? undefined : JSON.stringify(body), credentials: 'omit', cache: 'no-store' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Campaign service unavailable');
    return result;
  }
  async function loadControls() {
    const request = ++sequence;
    controls.hidden = window.LightyearContext.state.campaignId === 'retained';
    if (controls.hidden) return;
    // A context refresh must not discard an operator's partly written decision.
    if (controls.querySelector('form')) return;
    controls.replaceChildren(node('h2', 'Authorize this campaign'), node('p', 'Reading the exact execution terms…'));
    try {
      const status = await api('status');
      if (request !== sequence) return;
      controls.replaceChildren(node('h2', 'Authorize this campaign'));
      if (!status.enabled || !status.plan) { controls.append(node('p', status.reason)); return; }
      proposed = status.plan;
      const terms = node('section', undefined, 'paired-terms');
      const cost = proposed.profile;
      terms.append(node('p', `20 Oracle cases + 20 AlloyDB cases · Estimated budget $${cost.budget_usd} · Maximum active runtime ${cost.max_seconds / 60} minutes`));
      for (const key of ['resource_policy', 'data_policy', 'identity_policy', 'comparison_policy', 'cost_policy', 'interruption_policy', 'qualification']) terms.append(node('p', proposed[key]));
      terms.append(node('p', `Project: ${proposed.project} · Region: ${proposed.region}`));
      const details = node('details'); details.append(node('summary', 'Inspect the exact plan and SQL bindings'), node('pre', JSON.stringify(proposed, null, 2))); terms.append(details);
      controls.append(terms);
      const form = node('form');
      const credentialLabel = node('label', 'Campaign operator credential');
      const credential = node('input'); credential.type = 'password'; credential.autocomplete = 'off'; credential.required = !token; credentialLabel.append(credential);
      const reasonLabel = node('label', 'Why is this run authorized?');
      const reason = node('textarea'); reason.required = true; reason.minLength = 10; reason.maxLength = 2000; reasonLabel.append(reason);
      const acceptedLabel = node('label', undefined, 'paired-accept');
      const accepted = node('input'); accepted.type = 'checkbox'; accepted.required = true;
      acceptedLabel.append(accepted, node('span', 'I accept these exact cases, targets, diagnostic mapping, estimated spending and cleanup terms.'));
      const start = node('button', 'Authorize and start paired run'); start.type = 'submit';
      const message = node('p'); message.setAttribute('role', 'status');
      form.append(credentialLabel, reasonLabel, acceptedLabel, start, message); controls.append(form);
      form.addEventListener('submit', async event => {
        event.preventDefault(); start.disabled = true;
        try {
          if (window.LightyearContext.state.campaignId === 'retained') throw new Error('Select the NUMBER campaign before authorizing.');
          if (!token) {
            const session = await api('session', { credential: credential.value }); token = session.token;
            credential.value = ''; credential.required = false;
          }
          // Keep the same request and terms on an uncertain response. A double
          // click or retry must not create a second resource-consuming run.
          pendingRequest ||= crypto.randomUUID();
          pendingPayload ||= { plan_sha256: proposed.plan_sha256, request_id: pendingRequest, accept_terms: accepted.checked, reason: reason.value };
          const result = await api('start', pendingPayload);
          message.textContent = `${result.status} · ${result.run_id}. Open The run to observe the engine.`;
          start.textContent = 'Authorization recorded';
          await window.LightyearContext.refresh();
          window.LightyearContext.setRun(result.run_id);
          window.controlTowerDecisions.showPanel('run');
        } catch (error) { message.textContent = error.message; start.disabled = false; }
      });
    } catch (error) {
      if (request === sequence) controls.replaceChildren(node('p', `Campaign authorization unavailable. ${error.message}`));
    }
  }
  function renderRun(host, value) {
    const opened = new Set([...host.querySelectorAll('details[open]')].map(el => el.querySelector('summary')?.textContent.split(' · ')[0]));
    host.replaceChildren(node('h1', 'Oracle 26ai → AlloyDB · NUMBER run'));
    if (['invalid', 'unavailable'].includes(value.status)) { host.append(node('p', value.reason)); return; }
    window.LightyearContext.updatePairedRun(value);
    host.append(node('p', `${value.status} · ${value.run_id}`, 'run-note'));
    const stage = [...value.events].reverse().find(event => event.type === 'stage');
    if (stage && ['running', 'queued'].includes(value.status)) host.append(node('p', stage.payload.message, 'run-note'));
    host.append(node('p', `Evidence: ${value.evidence_class} · ${value.activity || 'Terminal journal'} · ${value.last_event_at ? new Date(value.last_event_at).toLocaleString() : 'Worker has not published an event yet'}`, 'run-note'));
    host.append(node('p', 'Updates every 3 seconds. Closing this browser does not stop the detached engine. Figures are completed observations, not estimates.', 'run-note'));
    const figures = node('div', undefined, 'run-figures');
    for (const [label, number] of [['Oracle observations', value.source_completed], ['AlloyDB observations', value.target_completed], ['Comparisons completed', value.comparisons_completed], ['Equivalent pairs', value.matched]]) {
      const figure = node('div', undefined, 'run-card'); figure.append(node('strong', `${number} / 20`, 'run-figure'), node('p', label)); figures.append(figure);
    }
    host.append(figures);
    const authorization = node('details');
    authorization.append(node('summary', 'Signed campaign authorization'),
      node('p', `${value.authorization.actor.name} · ${new Date(value.authorization.authorized_at).toLocaleString()}`),
      node('p', value.authorization.reason), node('pre', JSON.stringify(value.authorization, null, 2)));
    host.append(authorization);
    if (value.error) host.append(node('p', `Engine error: ${value.error}`, 'decision-error'));
    host.append(node('h2', 'Cleanup'), node('p', value.cleanup ? `${value.cleanup.complete ? 'Confirmed' : 'Action required'} · ${Object.entries(value.cleanup.resources).map(([k, v]) => `${k}: ${v}`).join(' · ')}` : 'Not yet recorded'));
    if (value.recovery) host.append(node('p', `Later recovery: ${value.recovery.cleanup.complete ? 'Cleanup confirmed' : 'Still requires attention'} · ${new Date(value.recovery.at).toLocaleString()}. Original run verdict is retained.`));
    const identities = node('details'); identities.append(node('summary', 'Observed database identities'), node('pre', JSON.stringify(value.identities, null, 2))); host.append(identities);
    host.append(node('h2', 'Case evidence'));
    for (const item of value.case_results) {
      const detail = node('details', undefined, 'paired-case');
      const status = item.comparison ? item.comparison.equivalent ? 'Equivalent under the approved contract' : 'Difference / expectation failure' : item.oracle || item.alloydb ? 'Waiting for comparison' : 'Not observed';
      detail.append(node('summary', `${item.case_id} · ${status}`), node('pre', JSON.stringify(item, null, 2))); host.append(detail);
    }
    const timeline = node('details'); timeline.append(node('summary', `${value.events.length} verified journal events`));
    const list = node('ol');
    for (const event of value.events) list.append(node('li', `${new Date(event.at).toLocaleTimeString()} · ${event.type} · ${event.payload.message || event.payload.case_id || event.payload.status || ''}`));
    timeline.append(list); host.append(timeline);
    host.querySelectorAll('details').forEach(el => { el.open = opened.has(el.querySelector('summary')?.textContent.split(' · ')[0]); });
  }
  function renderHistory(host, value) {
    host.replaceChildren();
    if (value.reason === 'invalid-run-index') { host.append(node('p', 'Campaign history could not be verified.')); return; }
    if (!value.runs.length) { host.append(node('p', 'No completed runs recorded yet. NUMBER campaign has no indexed runs.')); return; }
    host.append(node('p', value.note));
    for (const run of value.runs) {
      const row = node('section', undefined, 'convergence-card');
      row.append(node('h3', run.status), node('p', `${run.run_id} · ${new Date(run.at).toLocaleString()}`),
        node('p', `${run.source_completed} Oracle observations · ${run.target_completed} AlloyDB observations · ${run.matched} equivalent pairs · ${run.evidence_class}`),
        node('p', `Original cleanup ${run.cleanup.complete ? 'confirmed' : 'requires attention'}`));
      const recovery = value.recoveries?.[run.run_id];
      if (recovery) row.append(node('p', `Later recovery: ${recovery.cleanup.complete ? 'cleanup confirmed' : 'action required'}. Original verdict retained.`));
      host.append(row);
    }
  }
  document.addEventListener('tower-context-change', loadControls);
  window.LightyearPaired = { renderRun, renderHistory };
})();
