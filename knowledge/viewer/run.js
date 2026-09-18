/* Read projection only. The browser never emits plans, runs actions, or creates receipts. */
(() => {
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const number = (value) => value === null ? 'Not recorded' : value.toLocaleString();
  const count = (values) => {
    const counts = new Map();
    values.forEach((value) => counts.set(value, (counts.get(value) || 0) + 1));
    return [...counts];
  };
  const table = (rows, label) => {
    const element = node('table');
    element.append(node('caption', label));
    rows.forEach(([name, value]) => {
      const row = element.insertRow();
      const term = node('th', name); term.scope = 'row';
      row.append(term, node('td', number(value), 'run-number'));
    });
    return element;
  };
  const card = (title) => {
    const element = node('section', undefined, 'run-card');
    element.append(node('h2', title));
    return element;
  };
  function blockStep(detail) {
    const step = node('li', undefined, 'run-step blocked');
    const button = node('button', 'Go to the decision'); button.type = 'button';
    button.addEventListener('click', () => {
      window.controlTowerDecisions.showPanel('queue');
      document.getElementById('show-queue').focus();
    });
    step.append(node('h3', `Blocked · ${detail.action.kind}`), node('p', detail.reason), button);
    return step;
  }
  function render(payload) {
    const host = document.getElementById('run-view');
    if (['oracle26ai-alloydb-number', 'oracle26ai-alloydb-core100', 'oracle26ai-alloydb-types260'].includes(payload.campaign_id)) { window.LightyearPaired.renderRun(host, payload); return; }
    host.replaceChildren();
    if (payload.status === 'unavailable') {
      host.append(node('p', payload.reason || 'No run recorded yet. No journal is available for the selected estate.', 'run-note'));
      return;
    }
    if (payload.status === 'invalid') throw new Error('The execution journal could not be verified.');
    if (!['engine-journal', 'recorded-example'].includes(payload.source) || !Array.isArray(payload.action_kinds)) {
      throw new Error('The execution response is incomplete.');
    }
    const events = payload.events;
    const receipts = Array.isArray(events) ? events.filter((event) => event.type === 'result').map((event) => event.payload) : payload.action_kinds.flatMap((kind) => kind.receipts);
    const boundary = new Map();
    receipts.forEach((receipt) => {
      if (!receipt?.action?.kind || typeof receipt.before !== 'string' || typeof receipt.after !== 'string' || !receipt.boundary) {
        throw new Error('An action receipt is incomplete.');
      }
      Object.entries(receipt.boundary).forEach(([key, value]) => {
        if (typeof value !== 'boolean' && (!Number.isSafeInteger(value) || value < 0)) throw new Error('An action boundary is invalid.');
        boundary.set(key, (boundary.get(key) || 0) + Number(value));
      });
    });
    if (receipts.some((receipt) => [...boundary.keys()].some((key) => !Object.hasOwn(receipt.boundary, key)))) {
      throw new Error('An action boundary is incomplete.');
    }
    if (!Number.isSafeInteger(payload.summary?.iterations) || !Array.isArray(payload.blocks)) throw new Error('The run summary is incomplete.');
    host.append(node('p', `${payload.estate_name || 'CloudBank'} · ${payload.run_id || 'current'} · ${payload.source === 'recorded-example' ? 'Recorded example journal' : 'Engine journal'} · ${payload.activity === 'historical' ? 'Historical evidence' : 'Current observation'}`, 'run-eyebrow'), node('h1', 'The run'));
    host.append(node('p', `Started ${payload.started_at} · last event ${payload.last_event_at} · ${payload.status}${payload.halt_reason ? ' · ' + payload.halt_reason : ''}`, 'run-note'));
    if (events) host.append(node('p', `Hash-chained journal · ${number(events.length)} events · replay verified by the evidence service`, 'run-note'));
    const figures = node('div', undefined, 'run-figures');
    [[receipts.length, 'Actions completed', 'ok'], [Array.isArray(events) ? events.filter((event) => event.type === 'round').length : payload.summary.iterations, 'Rounds', ''],
      [Array.isArray(events) ? events.filter((event) => event.type === 'blocked').length : payload.blocks.length, 'Blocked events', 'blocked'], [boundary.get('model_calls') ?? null, 'Model calls in the verdict path', '']]
      .forEach(([value, label, tone]) => {
        const figure = node('div', undefined, `run-card ${tone}`);
        figure.append(node('div', number(value), 'run-figure'), node('div', label, 'run-label'));
        figures.append(figure);
      });
    host.append(figures, node('p', 'Completed actions count result receipts, not distinct resolved findings. Blocked events record what this run encountered; the work queue holds current decisions.', 'run-note'));
    const columns = node('div', undefined, 'run-columns');
    const timeline = card('What happened, in order');
    if (!Array.isArray(events)) {
      timeline.append(node('p', 'The exact round timeline is unavailable. The recorded block events are shown below.', 'run-note'));
      const blocks = node('ol', undefined, 'run-steps');
      payload.blocks.forEach((block) => blocks.append(blockStep(block)));
      timeline.append(blocks);
    } else {
      const steps = node('ol', undefined, 'run-steps');
      let round = 0;
      events.forEach((event) => {
        if (!['round', 'blocked', 'failed', 'paused', 'halted'].includes(event.type)) return;
        const detail = event.payload;
        if (event.type === 'blocked') { steps.append(blockStep(detail)); return; }
        const step = node('li', undefined, `run-step ${event.type}`);
        if (event.type === 'round') {
          step.append(node('h3', `Round ${++round}`), node('p', count(detail.actions.map((action) => action.kind)).map(([kind, n]) => `${number(n)} × ${kind}`).join(', ')));
        } else {
          step.append(node('h3', event.type === 'halted' ? 'Run halted' : event.type === 'failed' ? 'Action failed' : 'Run paused'), node('p', detail.reason || 'Checkpoint recorded'));
        }
        steps.append(step);
      });
      timeline.append(steps);
    }
    const side = node('div', undefined, 'run-side');
    const work = card('Work by kind');
    work.append(table(count(receipts.map((receipt) => receipt.action.kind)), 'Completed result receipts'));
    const transitions = card('State transitions');
    transitions.append(table(count(receipts.map((receipt) => `${receipt.before} → ${receipt.after}`)), 'Recorded before and after states'));
    transitions.append(node('p', 'These are the transitions asserted in result receipts. Verified retained evidence does not establish fresh execution or broader equivalence.', 'run-note'));
    side.append(work, transitions); columns.append(timeline, side); host.append(columns);
    const limits = card('Boundary — what this run was not allowed to do');
    if (boundary.size) limits.append(table([...boundary].map(([key, value]) => [key.replaceAll('_', ' '), value]), 'Sum of every boundary field across result receipts'));
    else limits.append(node('p', 'No result boundaries recorded.', 'run-note'));
    limits.append(node('p', 'Asserted in the receipt, not inferred from the log. Values are recorded totals, including any permitted ledger applications; they are not a new qualification.', 'run-note'));
    host.append(limits);
  }
  let sequence = 0, previousContext = null;
  async function reload() {
    const host = document.getElementById('run-view');
    if (!host) return;
    const request = ++sequence;
    const selectedContext = window.LightyearContext.query();
    if (previousContext !== selectedContext || window.LightyearContext.state.campaignId === 'retained') host.replaceChildren(node('p', 'Reading the execution journal…', 'run-note'));
    previousContext = selectedContext;
    try {
      const response = await fetch(`/api/workflow/execution?${window.LightyearContext.query()}`, { cache: 'no-store', credentials: 'omit' });
      if (!response.ok || !(response.headers.get('content-type') || '').includes('application/json')) throw new Error('The evidence service could not be reached.');
      const payload = await response.json();
      if (request === sequence) render(payload);
    } catch (error) {
      if (request === sequence) host.replaceChildren(node('p', `The run is unavailable. ${error.message}`, 'run-note'));
    }
  }
  document.addEventListener('tower-context-change', reload);
  setInterval(() => { if (window.LightyearContext.state.campaignId !== 'retained' && !document.getElementById('run-workspace').hidden) reload(); }, 3000);
  window.LightyearRun = { reload };
})();
