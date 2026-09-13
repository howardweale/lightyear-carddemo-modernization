/* Read-only engine projection. No browser-owned execution or receipt creation. */
(() => {
  const $ = (id) => document.getElementById(id);
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const names = { account: 'Account', 'azn-server': 'Authorization', chatbot: 'Chatbot', checks: 'Checks', creditscore: 'Credit score', customer: 'Customer', testrunner: 'Test runner', transfer: 'Transfer' };
  const labels = { unobserved: 'Awaiting observation', unavailable: 'Evidence unavailable', 'contract-verified': 'Contract verified', 'retained-evidence-verified': 'Retained evidence verified', divergent: 'Evidence differs' };
  let sequence = 0;
  let currentResult;
  function render(result) {
    const expanded = new Set([...$('execution-services').querySelectorAll('details[open]')].map((n) => n.dataset.service));
    $('execution-services').replaceChildren();
    $('execution-counts').replaceChildren();
    $('execution-details').replaceChildren();
    $('execution-actions').replaceChildren();
    if (!result.summary) {
      $('execution-status').textContent = `${result.status === 'invalid' ? 'Evidence cannot be verified' : 'Awaiting engine output'} · ${result.reason}`;
      $('execution-provenance').hidden = true;
      return;
    }
    $('execution-provenance').hidden = false;
    const source = result.source === 'recorded-example' ? 'Recorded demonstration' : 'Engine journal';
    const state = { completed: 'Completed within declared scope', paused: 'Paused at a durable checkpoint', halted: result.halt_reason === 'human-decision-required' ? 'Evidence checks passed · Human decision required' : `Stopped · ${result.halt_reason}`, running: result.activity === 'recent-engine-activity' ? 'Recent engine activity' : 'Engine activity is unobserved; resume from the checkpoint' }[result.status] || result.status;
    $('execution-status').textContent = `${source} · ${state} · ${new Date(result.last_event_at).toLocaleString()}`;
    const s = result.summary;
    for (const [title, count] of [['Verified service evidence', `${s.resolved} / ${s.services}`], ['Action kinds executed', `${s.action_kinds_executed} / ${s.action_kinds_supported}`], ['Actions executed', s.actions_executed], ['Iterations', s.iterations]]) {
      const card = element('article', undefined, 'workflow-metric');
      card.append(element('strong', String(count)), element('span', title));
      $('execution-counts').append(card);
    }
    const actionNames = { 'widen-observation': 'Widen observation', 'escalate-lane': 'Escalate lane', reparse: 'Reparse evidence', 'extend-corpus': 'Extend corpus', rerun: 'Rerun checks', 'apply-ledger-entry': 'Apply ledger entry' };
    for (const action of result.action_kinds || []) {
      const card = element('details', undefined, 'execution-action');
      card.dataset.kind = action.kind;
      const heading = element('summary');
      const status = action.status === 'blocked' ? 'Human decision required' : action.status === 'divergent' ? 'Evidence differs' : action.status === 'unavailable' ? 'Evidence unavailable' : action.verified ? `${action.verified} verified` : 'Awaiting prerequisite';
      heading.append(element('strong', actionNames[action.kind]), element('span', status));
      card.append(heading);
      if (action.reason) card.append(element('p', action.reason));
      card.append(element('p', `Requires: ${(action.preconditions || []).join(', ')}.`));
      const block = (result.blocks || []).find((b) => b.action.kind === action.kind);
      if (block) card.append(element('p', block.reason));
      if (action.kind === 'apply-ledger-entry') {
        const gate = result.current_ledger_approval;
        card.append(element('p', gate?.status === 'approved' ? 'Current human approval is valid.' : `Current approval: ${gate?.reason || 'not recorded'}`));
        if (action.executed && gate?.status !== 'approved') card.append(element('p', 'The historical application is retained. Its approval is no longer valid for use.', 'decision-error'));
      }
      for (const receipt of action.receipts) {
        const row = element('div', undefined, 'execution-receipt');
        row.append(element('small', receipt.action.service === 'estate' ? 'Estate evidence receipt' : names[receipt.action.service]), element('code', receipt.content_sha256));
        const artifact = receipt.observation.artifact;
        if (artifact) {
          const detail = element('details');
          detail.append(element('summary', 'Inspect derived evidence and original bindings'), element('pre', JSON.stringify(artifact, null, 2)));
          row.append(detail);
        }
        if (receipt.human_approval) {
          const decision = receipt.human_approval.decision;
          row.append(element('p', `Approved by ${decision.actor.name}; owner: ${decision.payload.owner}; review by ${decision.payload.review_after}.`), element('p', decision.payload.reason), element('code', decision.content_sha256));
        }
        card.append(row);
      }
      $('execution-actions').append(card);
    }
    const filter = $('execution-filter').value;
    const items = result.items.filter((item) => filter === 'all' || (filter === 'resolved') === (item.status === 'retained-evidence-verified'));
    for (const item of items) {
      const card = element('details', undefined, 'execution-service');
      card.dataset.service = item.service;
      card.open = expanded.has(item.service);
      const heading = element('summary');
      heading.append(element('strong', names[item.service] || item.service), element('span', labels[item.status] || item.status, `decision-badge ${item.status === 'retained-evidence-verified' ? 'approved' : item.status === 'divergent' ? 'rejected' : ''}`));
      card.append(heading);
      if (item.reason) card.append(element('p', item.reason));
      if (item.next_action) card.append(element('p', `Next permitted observation: ${item.next_action.lane}. Execution remains with the headless engine.`));
      for (const receipt of item.receipts) {
        const row = element('div', undefined, 'execution-receipt');
        row.append(element('h3', receipt.action.lane === 'contract' ? 'Service contract check' : 'Retained execution check'));
        row.append(element('p', `${receipt.observation.errors.length ? 'Evidence mismatch' : 'Evidence verified'} · Attempt ${receipt.attempt}`));
        for (const error of receipt.observation.errors) row.append(element('p', error, 'decision-error'));
        row.append(element('small', 'Receipt'), element('code', receipt.content_sha256));
        const refs = element('details');
        refs.append(element('summary', `${receipt.observation.evidence.length} evidence files`));
        for (const path of receipt.observation.evidence) refs.append(element('code', path));
        row.append(refs); card.append(row);
      }
      $('execution-services').append(card);
    }
    if (!items.length) $('execution-services').append(element('p', 'No services match this filter.', 'decision-empty'));
    for (const [key, value] of [['Bounded scope', 'Service contracts, typed retained scenarios, expanded corpus checks and approved ledger projection'], ['Original cloud run', result.source_run_id], ['Plan', result.plan_sha256], ['Journal head', result.journal_head_sha256], ['Elapsed budget', `${result.budgets.max_seconds} seconds, including restart downtime`], ['Action limits', `${result.budgets.max_actions} attempts; ${result.budgets.max_attempts} per action; ${result.budgets.max_iterations} iterations`], ['Claim boundary', `${result.boundary.ledger_entries_applied} ledger applications recorded; no fresh cloud execution, changed source verdicts or engine-created human decisions`]]) {
      const row = element('div'); row.append(element('dt', key), element('dd', value)); $('execution-details').append(row);
    }
  }
  async function refresh() {
    const request = ++sequence;
    try {
      const response = await fetch('/api/workflow/execution', { cache: 'no-store', credentials: 'omit' });
      if (!response.ok || !(response.headers.get('content-type') || '').includes('application/json')) throw new Error('Engine evidence service unavailable');
      const result = await response.json();
      if (request !== sequence) return;
      currentResult = result; render(result);
    } catch (error) {
      if (request !== sequence) return;
      currentResult = null;
      render({ status: 'invalid', reason: `Disconnected · ${error.message}. Reconnect to verify the engine journal.` });
    }
  }
  $('execution-refresh').addEventListener('click', refresh);
  $('execution-filter').addEventListener('change', () => { if (currentResult) render(currentResult); });
  refresh();
  setInterval(refresh, 15000);
})();
