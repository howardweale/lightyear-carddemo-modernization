/* Preparation and saved observations only. Never creates a run or verdict. */
(() => {
  const host = document.getElementById('campaign-view');
  const node = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  let sequence = 0;
  function render(value) {
    if (value.campaign_id !== window.LightyearContext.state.campaignId || value.status !== 'planned') throw new Error('Unexpected campaign response');
    host.replaceChildren(node('p', 'Campaign preparation · Not run', 'campaign-eyebrow'), node('h2', value.name), node('p', value.scope));
    const figures = node('div', undefined, 'campaign-figures');
    for (const [label, count] of [['Cases planned', value.planned_cases], ['Source SQL files verified', value.source_prepared_cases], ['Native executions', value.native_executed_cases], ['Target equivalents', value.target_equivalent_cases]]) {
      const card = node('div', undefined, 'campaign-card');
      card.append(node('strong', count === null ? 'Not recorded' : String(count)), node('span', label)); figures.append(card);
    }
    host.append(figures);
    const lanes = node('section'); lanes.append(node('h3', 'Proposed test lanes'), node('p', `Source: ${value.source}`), node('p', `Target: ${value.target}`), node('p', `${value.project} · ${value.region} · ${value.topic_family} · ${value.planned_behaviors} behaviours`));
    const readiness = node('section'); readiness.append(node('h3', 'Environment readback'));
    const observation = value.readiness;
    readiness.append(node('p', `${observation.status.toUpperCase()} · ${observation.observed_at ? new Date(observation.observed_at).toLocaleString() : 'No timestamp recorded'}`, 'campaign-readiness-status'));
    readiness.append(node('p', 'Saved, unsigned operational observation. Becomes stale after 15 minutes. Refresh view rereads this file; it does not contact GCP.'));
    if (observation.reason) readiness.append(node('p', observation.reason));
    const names = { alloydb: 'AlloyDB primary', cloud_sql: 'Cloud SQL baseline', gke: 'GKE control plane' };
    for (const row of observation.observations) readiness.append(node('p', `${names[row.resource]}: ${row.status === 'observed' ? row.state : 'Unknown — readback failed'}`));
    readiness.append(node('p', 'Oracle runtime, worker capacity, application health and database connectivity have not been checked. A READY or RUNNING resource is not permission to run.'));
    const instruction = node('details'); instruction.append(node('summary', 'Collect a fresh readback from the project terminal'));
    instruction.append(node('p', 'With the project Python environment and gcloud configured, run this read-only command, then Refresh view:'));
    instruction.append(node('code', 'python -m lightyear_workflow.campaigns collect --root .'));
    instruction.append(node('p', 'The saved hash detects file damage; it is not a signature or qualification receipt. No cloud resources are started or stopped.'));
    readiness.append(instruction);
    const next = node('section'); next.append(node('h3', 'What must happen before execution'));
    const blockers = node('ul'); value.blockers.forEach(text => blockers.append(node('li', text))); next.append(blockers);
    next.append(node('p', 'The factory prepares the code. The engine executes and compares observations. A person must accept the exact scope, risk and spending terms before a future campaign can start.'));
    const cases = node('details'); cases.append(node('summary', `${value.cases.length} verified case bindings · inspect scope`));
    if (value.preparation !== 'verified-files') cases.append(node('p', 'Source preparation could not be verified. Expected counts are not treated as prepared files.'));
    const list = node('ul'); value.cases.forEach(item => list.append(node('li', `${item.id} · ${item.focus} · ${item.dimension}`))); cases.append(list);
    host.append(lanes, readiness, next, cases);
  }
  async function reload() {
    const request = ++sequence;
    host.replaceChildren();
    if (window.LightyearContext.state.campaignId === 'retained') return;
    host.append(node('p', 'Reading campaign preparation…'));
    try {
      const response = await fetch(`/api/workflow/campaign?${window.LightyearContext.query()}`, { cache: 'no-store', credentials: 'omit' });
      if (!response.ok) throw new Error('Campaign service unavailable');
      const value = await response.json();
      if (request === sequence) render(value);
    } catch (error) {
      if (request === sequence) host.replaceChildren(node('p', `Campaign unavailable. ${error.message}`));
    }
  }
  document.addEventListener('tower-context-change', reload);
  setInterval(() => { if (window.LightyearContext.state.campaignId !== 'retained') reload(); }, 60000);
})();
