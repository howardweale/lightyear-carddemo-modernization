/* One estate/run selection for every report. Selection never dispatches work. */
(() => {
  const state = { estate: null, name: 'Selected estate', runId: 'current', campaignId: 'retained', runs: [] };
  const remembered = new Map();
  const campaigns = document.getElementById('workflow-campaign');
  const select = document.getElementById('workflow-run');
  const note = document.getElementById('workflow-context-note');
  let sequence = 0;
  const emit = () => document.dispatchEvent(new CustomEvent('tower-context-change'));
  const option = (value, text) => { const el = document.createElement('option'); el.value = value; el.textContent = text; return el; };
  const query = () => new URLSearchParams({ estate: state.estate || 'carddemo', run_id: state.runId, campaign_id: state.campaignId }).toString();
  function setRun(id) {
    if (id !== 'current' && !state.runs.some(run => run.run_id === id)) return;
    state.runId = id; select.value = id; remembered.set(`${state.estate}/${state.campaignId}`, id); emit();
  }
  function updatePairedRun(value) {
    if (state.campaignId !== value.campaign_id || state.runId !== value.run_id) return;
    const row = state.runs.find(run => run.run_id === value.run_id);
    const item = [...select.options].find(option => option.value === value.run_id);
    if (!row || !item) return;
    row.actions_completed = value.matched; row.terminal = value.status;
    item.textContent = `${new Date(row.started_at).toLocaleString()} · ${value.matched} equivalent pairs · ${value.status}`;
  }
  async function refresh() {
    const request = ++sequence;
    select.disabled = true;
    select.replaceChildren(option('current', 'Reading recorded runs…'));
    try {
      const response = await fetch(`/api/workflow/runs?${query()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error('Run list unavailable');
      const payload = await response.json();
      if (request !== sequence) return;
      if (payload.reason === 'invalid-run-index' || !Array.isArray(payload.runs)) throw new Error('Run index unavailable');
      state.runs = payload.runs;
      select.replaceChildren();
      if (state.estate === 'cloudbank' && state.campaignId === 'retained') select.append(option('current', 'Current journal / recorded example'));
      for (const run of state.runs) {
        select.append(option(run.run_id, `${new Date(run.started_at).toLocaleString()} · ${run.actions_completed ?? 'Not recorded'} ${state.campaignId === 'retained' ? 'actions' : 'equivalent pairs'} · ${run.terminal}${run.journal_pruned_at ? ' · pruned' : ''}`));
      }
      if (!select.options.length) select.append(option('current', 'No runs recorded for this campaign'));
      const previous = remembered.get(`${state.estate}/${state.campaignId}`);
      state.runId = [...select.options].some(item => item.value === previous) ? previous : state.runs[0]?.run_id || 'current';
      select.value = state.runId; select.disabled = select.options.length < 2;
      note.textContent = state.campaignId !== 'retained' ? `${state.campaignId === 'oracle26ai-alloydb-core100' ? 'Five datatype families · 100' : 'NUMBER catalog pilot · 20'} cases on each database. Run figures come from the selected engine journal. Discovery shows the selected estate workload, not the datatype test cases.` : `${state.name} · ${state.estate === 'cloudbank' ? 'Run evidence covers all eight services; Discovery shows the chosen workload. ' : ''}Convergence covers all indexed runs in this estate. ${state.runs.length ? 'Latest 100 runs available in the selector.' : 'No indexed history yet.'}`;
      emit();
    } catch (error) {
      if (request !== sequence) return;
      state.runs = []; state.runId = 'current';
      select.replaceChildren(option('current', 'Run history unavailable'));
      note.textContent = `${state.name} · ${error.message}. No history totals are assumed.`;
      emit();
    }
  }
  function setEstate(company) {
    const estate = ({ 'cloudbank-reference': 'cloudbank', 'carddemo-reference': 'carddemo', 'oracle-customer-large': 'idempiere' })[company.id] || 'oracle';
    if (state.estate === estate) return;
    state.campaignId = 'retained';
    campaigns.replaceChildren(option('retained', 'Retained estate evidence'));
    if (estate === 'cloudbank') campaigns.append(option('oracle26ai-alloydb-number', 'Oracle 26ai → AlloyDB · NUMBER pilot'), option('oracle26ai-alloydb-core100', 'Oracle 26ai → AlloyDB · 100 datatype pairs'));
    state.estate = estate; state.name = company.name; state.runId = 'current'; state.runs = [];
    note.textContent = `${state.name} · Reading history…`;
    document.querySelector('.legacy-workflow').hidden = estate !== 'idempiere';
    visibility();
    emit(); refresh();
  }
  function visibility() {
    document.getElementById('cloudbank-execution').hidden = state.estate !== 'cloudbank' || state.campaignId !== 'retained';
    document.getElementById('campaign-view').hidden = state.campaignId === 'retained';
  }
  campaigns.addEventListener('change', () => {
    state.campaignId = campaigns.value; state.runId = 'current'; state.runs = [];
    visibility(); emit(); refresh();
  });
  select.addEventListener('change', () => setRun(select.value));
  document.getElementById('refresh-run-list').addEventListener('click', refresh);
  window.LightyearContext = { state, query, setEstate, setRun, refresh, updatePairedRun };
})();
