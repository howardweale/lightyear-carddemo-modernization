/* Read projection only. The browser never emits plans, runs actions, or creates receipts. */
(() => {
  const $ = (id) => document.getElementById(id);
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const number = (value) => Number(value || 0).toLocaleString();
  const bytes = (value) => {
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = Number(value || 0), unit = 0;
    while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
    return `${size < 10 && unit > 0 ? size.toFixed(1) : Math.round(size)} ${units[unit]}`;
  };

  /* The four categories, in the order they are read: what the engine did,
     what it needs from a person, what nobody here can unblock, and what is
     ours. The last one is published because a coverage figure that hides our
     own backlog is not a coverage figure. */
  const CATEGORIES = [
    { key: 'actions_completed', label: 'Completed actions',          tone: 'ok' },
    { key: 'awaiting_human',   label: 'Human block events',      tone: 'ask' },
    { key: 'blocked_access',   label: 'Access block events',  tone: 'flat' },
    { key: 'blocked_internal', label: 'Internal block events', tone: 'no' },
  ];

  function headline(weeks) {
    const box = node('div', undefined, 'convergence-headline');
    if (!weeks.length) return box;
    const latest = weeks[weeks.length - 1];
    const first = weeks[0];

    CATEGORIES.forEach((category) => {
      const current = Number(latest[category.key] || 0);
      const earliest = Number(first[category.key] || 0);
      const card = node('div', undefined, `convergence-card tone-${category.tone}`);
      card.appendChild(node('div', number(current), 'convergence-figure'));
      card.appendChild(node('div', category.label, 'convergence-label'));

      if (weeks.length > 1 && current !== earliest) {
        const direction = current < earliest ? 'down from' : 'up from';
        card.appendChild(node('div', `${direction} ${number(earliest)}`, 'convergence-delta'));
      } else if (weeks.length > 1) {
        card.appendChild(node('div', `unchanged across ${weeks.length} recorded weeks`, 'convergence-delta'));
      }
      card.appendChild(spark(weeks, category.key));
      box.appendChild(card);
    });
    return box;
  }

  function spark(weeks, key) {
    const values = weeks.map((week) => Number(week[key] || 0));
    const peak = Math.max(1, ...values);
    const strip = node('div', undefined, 'convergence-spark');
    values.forEach((value, index) => {
      const bar = node('i');
      bar.style.height = `${Math.max(4, (value / peak) * 100)}%`;
      bar.title = `${weeks[index].week}: ${number(value)}`;
      strip.appendChild(bar);
    });
    return strip;
  }

  function table(weeks) {
    const element = node('table', undefined, 'convergence-table');
    const head = element.insertRow();
    ['Week', 'Runs', ...CATEGORIES.map((c) => c.label), ''].forEach((title) => {
      head.appendChild(node('th', title));
    });

    weeks.forEach((week) => {
      const row = element.insertRow();
      row.appendChild(node('td', week.week, 'mono'));
      row.appendChild(node('td', number(week.runs), 'mono right'));
      const total = CATEGORIES.reduce((sum, c) => sum + Number(week[c.key] || 0), 0) || 1;
      CATEGORIES.forEach((category) => {
        row.appendChild(node('td', number(week[category.key]), `mono right tone-${category.tone}`));
      });
      const barCell = node('td');
      const bar = node('div', undefined, 'convergence-bar');
      CATEGORIES.forEach((category) => {
        const segment = node('i', undefined, `tone-${category.tone}`);
        segment.style.width = `${(Number(week[category.key] || 0) / total) * 100}%`;
        bar.appendChild(segment);
      });
      barCell.appendChild(bar);
      row.appendChild(barCell);
    });
    return element;
  }

  function storage(summary) {
    const box = node('div', undefined, 'convergence-storage');
    box.appendChild(node('div', 'Storage · all estates', 'convergence-eyebrow'));
    const pairs = [
      ['Runs recorded', number(summary.runs)],
      ['Journals held', bytes(summary.journal_bytes)],
      ['Index', bytes(summary.index_bytes)],
      ['Journals pruned', number(summary.pruned_runs)],
      ['Oldest run', summary.oldest_run ? summary.oldest_run.slice(0, 10) : '—'],
    ];
    const list = node('dl');
    pairs.forEach(([term, value]) => {
      const pair = node('div');
      pair.appendChild(node('dt', term));
      pair.appendChild(node('dd', value, 'mono'));
      list.appendChild(pair);
    });
    box.appendChild(list);
    if (summary.pruned_runs) {
      box.appendChild(node('p',
        `${number(summary.pruned_runs)} journals have passed the retention policy and been removed. `
        + 'Their index rows and content hashes remain, so a pruned run is a recorded gap rather '
        + 'than a silent one.', 'convergence-note'));
    }
    return box;
  }

  function render(payload) {
    const host = $('convergence');
    if (!host) return;
    host.replaceChildren();

    if (payload.reason && payload.reason !== 'no-runs-recorded') {
      host.appendChild(node('p', 'Run history is unavailable. The run index could not be verified.', 'convergence-note'));
      return;
    }
    if (payload.metric_unit === 'paired-cases') { window.LightyearPaired.renderHistory(host, payload); return; }
    const weeks = payload.weeks || [];
    if (!weeks.length) {
      host.appendChild(node('p',
        `No completed runs recorded yet. ${window.LightyearContext.state.campaignId === 'retained' ? window.LightyearContext.state.name : 'NUMBER campaign'} has no indexed runs. Verified terminal runs are recorded by the engine; this is not a measurement of zero activity.`,
        'convergence-note'));
      return;
    }

    if (payload.metric_unit !== 'action-events') {
      host.appendChild(node('p', 'Run history is unavailable: unsupported measurement unit.', 'convergence-note'));
      return;
    }
    host.appendChild(node('p', `${window.LightyearContext.state.name} action activity · latest recorded week: ${weeks[weeks.length - 1].week}`, 'convergence-note'));
    host.appendChild(headline(weeks));
    const scroll = node('div', undefined, 'convergence-table-scroll');
    scroll.tabIndex = 0;
    scroll.setAttribute('role', 'region');
    scroll.setAttribute('aria-label', 'Weekly action activity');
    scroll.appendChild(table(weeks));
    host.appendChild(scroll);
    host.appendChild(node('p',
      'Counts describe action and block events across recorded runs, not distinct resolved findings '
      + 'or the current backlog. The same service may contribute several actions. Changes in run volume '
      + 'or scope can change these totals; they do not establish improved equivalence.',
      'convergence-note'));
    if (payload.storage) host.appendChild(storage(payload.storage));
  }

  let sequence = 0;
  async function load() {
    const request = ++sequence;
    const host = $('convergence');
    if (!host) return;
    host.replaceChildren(node('p', 'Reading selected estate history…'));
    try {
      const response = await fetch(`/api/workflow/convergence?${window.LightyearContext.query()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(String(response.status));
      const payload = await response.json();
      if (request !== sequence) return;
      render(payload);
    } catch (error) {
      if (request !== sequence) return;
      host.replaceChildren(node('p',
        'Convergence is unavailable. The run index could not be read; the engine is unaffected.',
        'convergence-note'));
    }
  }

  document.addEventListener('tower-context-change', load);
  document.addEventListener('DOMContentLoaded', load);
  window.LightyearConvergence = { reload: load };
})();
