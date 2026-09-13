/* Read projection only. The browser never emits plans, runs actions, or creates receipts. */
(() => {
  const $ = (id) => document.getElementById(id);
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const human = (text) => text.replaceAll('-', ' ');
  let offset = 0;
  let sequence = 0;
  async function refresh() {
    const current = ++sequence;
    const params = new URLSearchParams({ offset, limit: 20 });
    const filter = $('workflow-filter').value;
    if (filter === 'parser') params.set('kind', 'require-parser-work');
    else if (filter) params.set('class', filter);
    try {
      const response = await fetch(`/api/workflow/plan?${params}`, { cache: 'no-store', credentials: 'omit' });
      if (!response.ok || !(response.headers.get('content-type') || '').includes('application/json')) throw new Error('Plan service unavailable. Open the live Control Tower to read the engine snapshot.');
      const result = await response.json();
      if (current !== sequence) return;
      $('workflow-counts').replaceChildren(); $('workflow-actions').replaceChildren();
      $('workflow-count-note').textContent = '';
      $('workflow-previous').disabled = offset === 0;
      $('workflow-next').disabled = offset + 20 >= result.total;
      if (!result.summary) {
        $('workflow-status').textContent = `${human(result.status)} · ${result.reason}`;
        $('workflow-page').textContent = 'No verified plan available';
        return;
      }
      $('workflow-status').textContent = `${result.status === 'stale' ? 'Stale snapshot' : 'Planning snapshot'} · emitted ${new Date(result.emitted_at).toLocaleString()} · No actions executed; no executor is deployed.`;
      const s = result.summary;
      for (const [label, count] of [['Resolved autonomously', s.resolved_autonomously], ['Needs decision design', s.awaiting_decision_design], ['Blocked on access', s.blocked_on_access], ['Our parser backlog', s.blocked_on_parser]]) {
        const card = node('article', undefined, 'workflow-metric');
        card.append(node('strong', count.toLocaleString()), node('span', label)); $('workflow-counts').append(card);
      }
      $('workflow-count-note').textContent = `${s.entities.toLocaleString()} pairs · ${s.actions.toLocaleString()} proposed actions. Counts are actions and can overlap pairs. ${s.owner_assignment_required.toLocaleString()} actions need an accountable owner. Convergence has not been measured.`;
      for (const action of result.items) {
        const card = node('details', undefined, 'workflow-action');
        const summary = node('summary');
        const label = action.evidence[0]?.path.split('/').pop() || action.entity_id;
        summary.append(node('span', human(action.class), 'decision-badge'), node('strong', human(action.kind)), node('span', label, 'workflow-file'));
        card.append(summary);
        card.append(node('p', `Owner: ${action.owner || `Unassigned · ${human(action.owner_role)}`}. Source verdict: ${action.source_verdict}. Action proposed; not executed.`));
        if (action.question) {
          card.append(node('p', action.question), node('p', `If approved: ${action.if_approved}`), node('p', `If refused: ${action.if_refused}`));
          card.append(node('p', action.signature_blocker, 'decision-signing-note'));
        }
        card.append(node('p', `Observed scope: ${action.impact.sql_units.toLocaleString()} SQL units across ${action.impact.files} files. Suppressed comparisons: 0; proposed suppression has not been assessed.`));
        card.append(node('small', `Reasons: ${action.reason_codes.join(', ')}`));
        const evidence = node('details'); evidence.append(node('summary', `${action.evidence.length} evidence ranges · source and provenance`));
        evidence.append(node('p', `Original verdict receipt: ${action.source_verdict_sha256}`));
        evidence.append(node('p', 'No ledger entry has been applied by this action. No human decision or verdict transition is attributed to it.'));
        for (const ref of action.evidence.slice(0, 20)) {
          const link = node('a', `${ref.dialect}: ${ref.path}, lines ${ref.start_line}–${ref.end_line}`);
          link.href = `https://github.com/idempiere/idempiere/blob/${encodeURIComponent(result.bindings.source_commit)}/${ref.path.split('/').map(encodeURIComponent).join('/')}#L${ref.start_line}-L${ref.end_line}`;
          link.target = '_blank'; link.rel = 'noopener noreferrer'; evidence.append(link);
        }
        if (action.evidence.length > 20) evidence.append(node('small', 'First 20 ranges shown. The headless JSON plan retains every range.'));
        card.append(evidence); $('workflow-actions').append(card);
      }
      if (!result.total) $('workflow-actions').append(node('p', 'No proposed actions match this filter.'));
      $('workflow-page').textContent = result.total ? `${offset + 1}–${Math.min(offset + 20, result.total)} of ${result.total.toLocaleString()} actions` : '0 actions';
    } catch (error) {
      if (current !== sequence) return;
      $('workflow-status').textContent = `Disconnected · ${error.message} Any displayed data is the last snapshot and cannot be verified as current.`;
      $('workflow-previous').disabled = true; $('workflow-next').disabled = true;
    }
  }
  $('workflow-refresh').addEventListener('click', refresh);
  $('workflow-filter').addEventListener('change', () => { offset = 0; refresh(); });
  $('workflow-previous').addEventListener('click', () => { offset = Math.max(0, offset - 20); refresh(); });
  $('workflow-next').addEventListener('click', () => { offset += 20; refresh(); });
  refresh();
  setInterval(refresh, 60000);
})();
