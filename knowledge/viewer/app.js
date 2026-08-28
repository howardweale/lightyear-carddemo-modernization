"use strict";

const NS = "http://www.w3.org/2000/svg";
const state = {
  meta: null,
  chatStatus: null,
  chatHistory: [],
  factoryRuns: [],
  portfolio: null,
  recovery: null,
  evaluations: [],
  memorySummary: null,
  dataSummary: null,
  runtimeRuns: [],
  auditSummary: null,
  auditEvents: [],
  auditReleaseId: null,
  operations: null,
  eventStream: null,
  liveRefreshTimer: null,
  selection: null,
  selectedId: null,
  selectedEdgeId: null,
  edgeDetail: null,
  positions: new Map(),
  zoom: { x: 0, y: 0, scale: 1 },
  drag: null,
};

const colors = {
  program: "var(--program)",
  structure: "var(--structure)",
  data: "var(--data)",
  rule: "var(--rule)",
  modern: "var(--modern)",
  verify: "var(--verify)",
  other: "var(--other)",
};

const groups = {
  cobol_program: "program", cobol_paragraph: "program", jcl_job: "program",
  jcl_step: "program", jcl_procedure: "program", executable: "program",
  copybook: "structure", cobol_field: "structure", cobol_file_handle: "structure",
  jcl_dd_name: "structure", jcl_dd_allocation: "structure",
  dataset: "data", db2_table: "data", db2_column: "structure", db2_index: "data",
  db2_constraint: "structure", db2_dcl: "structure", db2_sql_statement: "program",
  business_rule: "rule", modernization_workload: "rule",
  java_type: "modern", java_method: "modern", software_dependency: "modern",
  test_case: "verify", verification_scenario: "verify",
};

const $ = (id) => document.getElementById(id);

async function api(path, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== undefined && value !== null) query.set(key, value);
  });
  const response = await fetch(`${path}?${query}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
  return payload;
}

async function apiPost(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed: ${response.status}`);
  return payload;
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value || 0);
}

function groupFor(kind) { return groups[kind] || "other"; }

async function initialize() {
  try {
    [state.meta, state.chatStatus] = await Promise.all([
      api("/api/meta"),
      api("/api/chat/status"),
    ]);
    const stats = state.meta.statistics;
    $("metric-nodes").textContent = formatNumber(stats.node_count);
    $("metric-edges").textContent = formatNumber(stats.edge_count);
    $("metric-rules").textContent = formatNumber(stats.nodes_by_kind.business_rule);
    $("metric-hash").textContent = state.meta.content_sha256.slice(0, 10);
    renderEstateBoundary();
    $("status-dot").classList.add("online");
    $("status-text").textContent = "Local control plane online";
    populatePerspectives();
    populateLegend();
    configureChat();
    bindControls();
    state.operations = state.meta.operations || await api("/api/operations/status");
    renderLiveStatus();
    connectLivePlane();
    await Promise.all([loadPerspective(), loadFactoryRuns(false), loadPortfolio(false), loadRecovery(false), loadEvaluations(false), loadMemory(false), loadData(false), loadRuntimeRuns(false), loadAudit(false)]);
  } catch (error) {
    setError(error);
  }
}

function renderEstateBoundary() {
  if (state.meta.projection_type !== "lightyear-composite-estate") return;
  const boundary = $("estate-boundary");
  boundary.hidden = false;
  const fragments = state.meta.fragments || [];
  $("estate-fragments").textContent = `${fragments.length} validated extension fragment${fragments.length === 1 ? "" : "s"}`;
  $("estate-base-hash").textContent = state.meta.canonical_content_sha256.slice(0, 10);
  $("estate-composite-hash").textContent = state.meta.content_sha256.slice(0, 10);
  $("estate-boundary-statement").textContent = state.meta.claim_boundary?.statement || "Read-only composition of separately governed evidence.";
}

function populatePerspectives() {
  const select = $("perspective");
  state.meta.perspectives.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.name;
    select.appendChild(option);
  });
}

function populateLegend() {
  const labels = { program: "Legacy flow", structure: "Data structure", data: "Dataset", rule: "Rule / workload", modern: "Modern code", verify: "Verification", other: "Other" };
  Object.entries(labels).forEach(([group, label]) => {
    const item = document.createElement("div");
    item.className = "legend-item";
    const dot = document.createElement("span");
    dot.className = "legend-dot";
    dot.style.background = colors[group];
    const text = document.createElement("span");
    text.textContent = label;
    item.append(dot, text);
    $("legend").appendChild(item);
  });
}

function bindControls() {
  $("perspective").addEventListener("change", loadPerspective);
  $("depth").addEventListener("change", () => {
    const root = state.selection?.root || selectedPerspective()?.root;
    if (root) loadNeighborhood(root, Number($("depth").value));
  });
  $("audience").addEventListener("change", async () => {
    $("search").value = "";
    $("search-results").replaceChildren();
    resetChat();
    await loadPerspective();
  });
  $("fit").addEventListener("click", fitGraph);
  $("focus-node").addEventListener("click", () => loadNeighborhood(state.selectedId));
  $("ask-node").addEventListener("click", () => {
    switchRightPanel("chat");
    $("chat-question").focus();
  });
  $("ask-edge").addEventListener("click", () => {
    switchRightPanel("chat");
    $("chat-question").value = "Why does this relationship exist?";
    $("chat-question").focus();
  });
  $("edge-source").addEventListener("click", () => inspectNode(state.edgeDetail.source));
  $("edge-target").addEventListener("click", () => inspectNode(state.edgeDetail.target));
  $("trace-edge").addEventListener("click", () => {
    document.querySelectorAll(".edge").forEach((item) => {
      item.classList.toggle("selected", item.dataset.id === state.selectedEdgeId);
    });
    fitGraph();
  });
  $("close-source").addEventListener("click", () => { $("source-drawer").hidden = true; });
  $("inspector-tab").addEventListener("click", () => switchRightPanel("inspector"));
  $("chat-tab").addEventListener("click", () => switchRightPanel("chat"));
  $("factory-tab").addEventListener("click", async () => {
    switchRightPanel("factory");
    await loadFactoryRuns(true);
  });
  $("portfolio-tab").addEventListener("click", async () => {
    switchRightPanel("portfolio");
    await loadPortfolio(true);
  });
  $("recovery-tab").addEventListener("click", async () => {
    switchRightPanel("recovery");
    await loadRecovery(true);
  });
  $("evaluation-tab").addEventListener("click", async () => {
    switchRightPanel("evaluation");
    await loadEvaluations(true);
  });
  $("memory-tab").addEventListener("click", async () => {
    switchRightPanel("memory");
    await loadMemory(true);
  });
  $("data-tab").addEventListener("click", async () => {
    switchRightPanel("data");
    await loadData(true);
  });
  $("runtime-tab").addEventListener("click", async () => {
    switchRightPanel("runtime");
    await loadRuntimeRuns(true);
  });
  $("audit-tab").addEventListener("click", async () => {
    switchRightPanel("audit");
    await loadAudit(true);
  });
  $("refresh-factory").addEventListener("click", () => loadFactoryRuns(true));
  $("refresh-portfolio").addEventListener("click", () => loadPortfolio(true));
  $("refresh-recovery").addEventListener("click", () => loadRecovery(true));
  $("refresh-evaluations").addEventListener("click", () => loadEvaluations(true));
  $("refresh-memory").addEventListener("click", () => loadMemory(true));
  $("refresh-data").addEventListener("click", () => loadData(true));
  $("refresh-runtime").addEventListener("click", () => loadRuntimeRuns(true));
  $("refresh-audit").addEventListener("click", () => loadAudit(true));
  $("view-audit-dossier").addEventListener("click", loadAuditDossier);
  $("live-alerts").addEventListener("click", async () => {
    switchRightPanel("recovery");
    await loadRecovery(true);
  });
  $("clear-chat").addEventListener("click", resetChat);
  $("chat-form").addEventListener("submit", submitChat);
  $("chat-suggestions").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    $("chat-question").value = button.textContent;
    $("chat-question").focus();
  });
  $("chat-question").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("chat-form").requestSubmit();
    }
  });
  let searchTimer;
  $("search").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, 180);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("source-drawer").hidden) {
      $("source-drawer").hidden = true;
      return;
    }
    if (event.key === "/" && document.activeElement !== $("search")) {
      event.preventDefault();
      $("search").focus();
    }
  });
  bindPanZoom();
}

function renderLiveStatus() {
  const status = state.operations;
  if (!status) return;
  const connection = $("live-connection");
  connection.textContent = status.connection === "live" ? "LIVE" : "RECONNECTING";
  connection.className = `live-connection ${status.connection || "connecting"}`;
  $("live-sequence").textContent = `sequence ${status.latest_sequence || 0}`;
  const sources = $("live-sources");
  sources.replaceChildren();
  (status.sources || []).forEach((source) => {
    const chip = document.createElement("span");
    chip.className = `live-source ${source.freshness}`;
    chip.dataset.source = source.source;
    chip.title = `${source.trust_class}; observed ${source.last_observed_at || "never"}`;
    const age = source.age_seconds === null ? "no signal" : source.age_seconds < 2 ? "now" : `${source.age_seconds}s`;
    const name = document.createElement("b");
    name.textContent = source.source;
    const detail = document.createElement("small");
    detail.textContent = `${source.freshness} · ${age}`;
    chip.append(name, detail);
    sources.appendChild(chip);
  });
  const alerts = status.alerts || [];
  const alertButton = $("live-alerts");
  alertButton.textContent = `${alerts.length} active alert${alerts.length === 1 ? "" : "s"}`;
  alertButton.className = `live-alerts ${alerts.some((item) => item.severity === "critical") ? "critical" : alerts.length ? "warning" : "healthy"}`;
  alertButton.title = alerts.map((item) => item.message).join("\n") || "No active operational alerts";
}

function connectLivePlane() {
  if (!window.EventSource) {
    state.operations.connection = "unavailable";
    renderLiveStatus();
    return;
  }
  if (state.eventStream) state.eventStream.close();
  const after = state.operations?.latest_sequence || 0;
  const stream = new EventSource(`/api/operations/stream?after=${after}`);
  state.eventStream = stream;
  stream.addEventListener("ready", () => {
    state.operations.connection = "live";
    renderLiveStatus();
  });
  stream.addEventListener("operational-event", (message) => {
    const event = JSON.parse(message.data);
    state.operations.latest_sequence = event.sequence;
    scheduleLiveRefresh(event.source, event.payload?.refresh_hint);
  });
  stream.onerror = () => {
    state.operations.connection = "reconnecting";
    renderLiveStatus();
  };
}

function scheduleLiveRefresh(source, hint) {
  clearTimeout(state.liveRefreshTimer);
  state.liveRefreshTimer = setTimeout(async () => {
    try {
      state.operations = await api("/api/operations/status");
      renderLiveStatus();
      const target = hint || source;
      const refreshers = {
        factory: () => loadFactoryRuns(false),
        portfolio: () => loadPortfolio(false),
        recovery: () => loadRecovery(false),
        quality: () => loadEvaluations(false),
        memory: () => loadMemory(false),
        runtime: () => loadRuntimeRuns(false),
        audit: () => loadAudit(false),
      };
      if (refreshers[target]) await refreshers[target]();
    } catch (error) {
      console.warn("Live projection refresh failed", error);
    }
  }, 180);
}

function selectedPerspective() {
  return state.meta.perspectives.find((item) => item.id === $("perspective").value);
}

async function loadPerspective() {
  const perspective = selectedPerspective();
  if (!perspective) return;
  $("depth").value = String(perspective.depth);
  $("perspective-description").textContent = perspective.description;
  $("graph-title").textContent = perspective.name;
  await loadNeighborhood(perspective.root, perspective.depth);
}

async function loadNeighborhood(nodeId, overrideDepth) {
  try {
    const depth = overrideDepth || Number($("depth").value);
    state.selection = await api("/api/neighborhood", {
      node: nodeId,
      depth,
      audience: $("audience").value,
      limit: 220,
    });
    state.selectedId = nodeId;
    state.selectedEdgeId = null;
    state.edgeDetail = null;
    $("selection-count").textContent = `${state.selection.nodes.length} nodes · ${state.selection.edges.length} links${state.selection.truncated ? " · bounded" : ""}`;
    renderGraph();
    await inspectNode(nodeId);
  } catch (error) {
    setError(error);
  }
}

async function runSearch() {
  const query = $("search").value.trim();
  const container = $("search-results");
  container.replaceChildren();
  if (query.length < 2) return;
  try {
    const payload = await api("/api/search", { q: query, audience: $("audience").value, limit: 30 });
    if (!payload.results.length) {
      container.textContent = "No matching entities";
      return;
    }
    payload.results.forEach((node) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "search-result";
      const name = document.createElement("strong");
      name.textContent = node.name;
      const kind = document.createElement("span");
      kind.textContent = node.kind.replaceAll("_", " ");
      button.append(name, kind);
      button.addEventListener("click", async () => {
        container.replaceChildren();
        $("search").value = node.name;
        $("graph-title").textContent = `Focused: ${node.name}`;
        await loadNeighborhood(node.id);
      });
      container.appendChild(button);
    });
  } catch (error) {
    setError(error);
  }
}

function renderGraph() {
  $("edges").replaceChildren();
  $("nodes").replaceChildren();
  state.positions.clear();
  const graph = $("graph");
  const width = graph.clientWidth || 800;
  const height = graph.clientHeight || 650;
  const nodes = state.selection.nodes;
  const rootIndex = nodes.findIndex((node) => node.id === state.selection.root);
  nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, nodes.length);
    const radius = rootIndex === index ? 0 : Math.min(width, height) * (0.18 + 0.22 * ((index % 5) / 5));
    state.positions.set(node.id, {
      x: width / 2 + Math.cos(angle) * radius,
      y: height / 2 + Math.sin(angle) * radius,
      vx: 0, vy: 0,
      fixed: rootIndex === index,
    });
  });

  state.selection.edges.forEach((edge) => {
    const line = document.createElementNS(NS, "line");
    line.classList.add("edge");
    line.dataset.id = edge.id;
    line.dataset.source = edge.source;
    line.dataset.target = edge.target;
    const title = document.createElementNS(NS, "title");
    title.textContent = edge.relation;
    line.appendChild(title);
    $("edges").appendChild(line);
    const hit = document.createElementNS(NS, "line");
    hit.classList.add("edge-hit");
    hit.dataset.id = edge.id;
    hit.dataset.source = edge.source;
    hit.dataset.target = edge.target;
    hit.addEventListener("click", (event) => {
      event.stopPropagation();
      inspectEdge(edge.id);
    });
    $("edges").appendChild(hit);
  });

  nodes.forEach((node) => {
    const group = document.createElementNS(NS, "g");
    group.classList.add("node");
    if (node.id === state.selection.root) group.classList.add("root");
    group.dataset.id = node.id;
    const circle = document.createElementNS(NS, "circle");
    circle.setAttribute("r", node.id === state.selection.root ? "10" : "7");
    circle.style.fill = colors[groupFor(node.kind)];
    const title = document.createElementNS(NS, "title");
    title.textContent = `${node.name}\n${node.kind}`;
    circle.appendChild(title);
    const label = document.createElementNS(NS, "text");
    label.setAttribute("x", "11");
    label.setAttribute("y", "3.5");
    label.textContent = shorten(node.name, 30);
    group.append(circle, label);
    group.addEventListener("click", (event) => {
      event.stopPropagation();
      inspectNode(node.id);
    });
    group.addEventListener("pointerdown", startNodeDrag);
    $("nodes").appendChild(group);
  });
  relaxLayout(0);
  setTimeout(fitGraph, 120);
}

function relaxLayout(iteration) {
  if (!state.selection || iteration > 150) return;
  const nodes = state.selection.nodes;
  const width = $("graph").clientWidth;
  const height = $("graph").clientHeight;
  for (let i = 0; i < nodes.length; i += 1) {
    const a = state.positions.get(nodes[i].id);
    if (a.fixed) continue;
    let fx = (width / 2 - a.x) * 0.0009;
    let fy = (height / 2 - a.y) * 0.0009;
    for (let j = 0; j < nodes.length; j += 1) {
      if (i === j) continue;
      const b = state.positions.get(nodes[j].id);
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const distance2 = Math.max(80, dx * dx + dy * dy);
      fx += (dx / Math.sqrt(distance2)) * (900 / distance2);
      fy += (dy / Math.sqrt(distance2)) * (900 / distance2);
    }
    a.vx = (a.vx + fx) * 0.85;
    a.vy = (a.vy + fy) * 0.85;
  }
  state.selection.edges.forEach((edge) => {
    const a = state.positions.get(edge.source);
    const b = state.positions.get(edge.target);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const distance = Math.max(1, Math.hypot(dx, dy));
    const pull = (distance - 90) * 0.015;
    if (!a.fixed) { a.vx += (dx / distance) * pull; a.vy += (dy / distance) * pull; }
    if (!b.fixed) { b.vx -= (dx / distance) * pull; b.vy -= (dy / distance) * pull; }
  });
  state.positions.forEach((position) => {
    if (!position.fixed) { position.x += position.vx; position.y += position.vy; }
  });
  updatePositions();
  requestAnimationFrame(() => relaxLayout(iteration + 1));
}

function updatePositions() {
  document.querySelectorAll(".node").forEach((element) => {
    const point = state.positions.get(element.dataset.id);
    element.setAttribute("transform", `translate(${point.x},${point.y})`);
  });
  document.querySelectorAll(".edge, .edge-hit").forEach((element) => {
    const source = state.positions.get(element.dataset.source);
    const target = state.positions.get(element.dataset.target);
    element.setAttribute("x1", source.x);
    element.setAttribute("y1", source.y);
    element.setAttribute("x2", target.x);
    element.setAttribute("y2", target.y);
  });
}

async function inspectNode(nodeId) {
  try {
    const node = await api("/api/node", { id: nodeId, audience: $("audience").value });
    state.selectedId = nodeId;
    state.selectedEdgeId = null;
    state.edgeDetail = null;
    document.querySelectorAll(".node").forEach((item) => item.classList.toggle("active", item.dataset.id === nodeId));
    document.querySelectorAll(".edge").forEach((item) => {
      item.classList.toggle("active", item.dataset.source === nodeId || item.dataset.target === nodeId);
      item.classList.remove("selected");
    });
    $("inspector-placeholder").hidden = true;
    $("inspector").hidden = false;
    $("edge-inspector").hidden = true;
    $("detail-kind").textContent = node.kind.replaceAll("_", " ");
    $("detail-kind").style.background = colors[groupFor(node.kind)];
    $("detail-name").textContent = node.name;
    $("detail-id").textContent = node.id;
    const statement = node.properties?.statement || "";
    $("detail-statement").textContent = statement;
    $("detail-statement").hidden = !statement;
    renderProperties(node.properties || {});
    renderEvidence(node.evidence || [], "node", node.id, $("detail-evidence"));
    renderRuntimeProjection(node.runtime, $("detail-runtime"));
    renderRelations(node);
    $("chat-focus").textContent = `${node.name} · ${node.kind.replaceAll("_", " ")}`;
  } catch (error) {
    setError(error);
  }
}

async function inspectEdge(edgeId) {
  try {
    const edge = await api("/api/edge", { id: edgeId, audience: $("audience").value });
    state.selectedId = null;
    state.selectedEdgeId = edgeId;
    state.edgeDetail = edge;
    document.querySelectorAll(".node").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".edge").forEach((item) => {
      item.classList.toggle("selected", item.dataset.id === edgeId);
      item.classList.remove("active");
    });
    $("inspector-placeholder").hidden = true;
    $("inspector").hidden = true;
    $("edge-inspector").hidden = false;
    $("edge-category").textContent = edge.definition.category.replaceAll("-", " ");
    $("edge-name").textContent = edge.definition.label;
    $("edge-id").textContent = edge.id;
    $("edge-purpose").textContent = edge.definition.purpose;
    $("edge-source").textContent = edge.source_node.name;
    $("edge-source").title = edge.source;
    $("edge-target").textContent = edge.target_node.name;
    $("edge-target").title = edge.target;
    $("edge-relation").textContent = `—${edge.relation}→`;
    renderDefinition(edge.definition);
    renderEdgeProperties(edge.properties || {});
    renderSupportingEvidence(edge.supporting_evidence || [], $("edge-evidence"));
    renderRuntimeProjection(edge.runtime, $("edge-runtime"));
    $("chat-focus").textContent = `${edge.source_node.name} —${edge.relation}→ ${edge.target_node.name}`;
    switchRightPanel("inspector");
  } catch (error) {
    setError(error);
  }
}

function renderProperties(properties) {
  const list = $("detail-properties");
  list.replaceChildren();
  const entries = Object.entries(properties).filter(([key]) => key !== "statement");
  $("properties-section").hidden = !entries.length;
  entries.forEach(([key, value]) => {
    const term = document.createElement("dt");
    term.textContent = key;
    const description = document.createElement("dd");
    description.textContent = typeof value === "object" ? JSON.stringify(value) : String(value);
    list.append(term, description);
  });
}

function renderEvidence(evidence, ownerType, ownerId, container) {
  container.replaceChildren();
  if (!evidence.length) {
    container.textContent = "No direct evidence; inspect the endpoints and connected derivation edges.";
    return;
  }
  evidence.forEach((item, evidenceIndex) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "evidence-card clickable";
    const label = document.createElement("strong");
    label.textContent = `${item.confidence || "unclassified"} · ${item.method || "source"}`;
    const path = document.createElement("code");
    const lines = item.line_start ? `:${item.line_start}${item.line_end && item.line_end !== item.line_start ? `–${item.line_end}` : ""}` : "";
    path.textContent = `${item.path || item.source_id || "unknown"}${lines}`;
    card.append(label, path);
    card.addEventListener("click", () => openEvidence(ownerType, ownerId, evidenceIndex));
    container.appendChild(card);
  });
}

function renderSupportingEvidence(records, container) {
  container.replaceChildren();
  if (!records.length) {
    container.textContent = "No source evidence is attached to the relationship or its endpoints.";
    return;
  }
  records.forEach((record) => {
    const item = record.evidence;
    const card = document.createElement("button");
    card.type = "button";
    card.className = "evidence-card clickable";
    const label = document.createElement("strong");
    label.textContent = `${record.role} · ${item.confidence || "unclassified"}`;
    const path = document.createElement("code");
    const lines = item.line_start
      ? `:${item.line_start}${item.line_end && item.line_end !== item.line_start ? `–${item.line_end}` : ""}`
      : "";
    path.textContent = `${item.path || item.source_id || "unknown"}${lines}`;
    card.append(label, path);
    card.addEventListener("click", () => openEvidence(
      record.owner_type,
      record.owner_id,
      record.evidence_index,
    ));
    container.appendChild(card);
  });
}

function renderRelations(node) {
  const container = $("detail-relations");
  container.replaceChildren();
  const relations = [
    ...node.incoming.map((edge) => ({ id: edge.id, relation: `← ${edge.relation}`, target: edge.source })),
    ...node.outgoing.map((edge) => ({ id: edge.id, relation: `${edge.relation} →`, target: edge.target })),
  ];
  if (!relations.length) {
    container.textContent = "No visible relationships.";
    return;
  }
  relations.slice(0, 80).forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "relation-button";
    const relation = document.createElement("span");
    relation.textContent = item.relation;
    const target = document.createElement("span");
    target.textContent = item.target;
    button.append(relation, target);
    button.title = "Inspect this relationship and its supporting source";
    button.addEventListener("click", () => inspectEdge(item.id));
    container.appendChild(button);
  });
}

function renderDefinition(definition) {
  const list = $("edge-semantics");
  list.replaceChildren();
  [
    ["Purpose", definition.purpose],
    ["Direction", definition.direction],
    ["Category", definition.category],
    ["Evidence", definition.evidence_policy],
  ].forEach(([key, value]) => {
    const term = document.createElement("dt");
    term.textContent = key;
    const description = document.createElement("dd");
    description.textContent = value;
    list.append(term, description);
  });
}

function renderEdgeProperties(properties) {
  const list = $("edge-properties");
  list.replaceChildren();
  const entries = Object.entries(properties);
  $("edge-properties-section").hidden = !entries.length;
  entries.forEach(([key, value]) => {
    const term = document.createElement("dt");
    term.textContent = key;
    const description = document.createElement("dd");
    description.textContent = typeof value === "object" ? JSON.stringify(value) : String(value);
    list.append(term, description);
  });
}

async function openEvidence(ownerType, ownerId, evidenceIndex) {
  try {
    const excerpt = await api("/api/evidence", {
      owner_type: ownerType,
      owner_id: ownerId,
      evidence_index: evidenceIndex,
      audience: $("audience").value,
    });
    $("source-title").textContent = `${excerpt.path}:${excerpt.line_start}–${excerpt.line_end}`;
    const meta = $("source-meta");
    meta.replaceChildren();
    [
      excerpt.source_id,
      excerpt.language,
      excerpt.confidence,
      excerpt.method,
      `file ${excerpt.file_sha256.slice(0, 12)}`,
      `capsule ${excerpt.capsule_id.slice(8, 20)}`,
    ].forEach((value) => {
      const item = document.createElement("span");
      item.textContent = value;
      meta.appendChild(item);
    });
    const code = $("source-code");
    code.replaceChildren();
    excerpt.lines.forEach((line) => {
      const row = document.createElement("span");
      row.className = `source-line${line.highlighted ? " highlighted" : ""}`;
      const number = document.createElement("span");
      number.className = "source-line-number";
      number.textContent = line.number;
      const text = document.createElement("span");
      text.className = "source-line-text";
      text.textContent = line.text || " ";
      row.append(number, text);
      code.appendChild(row);
    });
    $("source-drawer").hidden = false;
    code.focus();
  } catch (error) {
    setError(error);
  }
}

function fitGraph() {
  if (!state.positions.size) return;
  const points = [...state.positions.values()];
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs) - 45;
  const maxX = Math.max(...xs) + 120;
  const minY = Math.min(...ys) - 45;
  const maxY = Math.max(...ys) + 45;
  const width = $("graph").clientWidth;
  const height = $("graph").clientHeight;
  const scale = Math.min(1.6, Math.max(0.12, Math.min(width / (maxX - minX), height / (maxY - minY)) * 0.9));
  state.zoom = {
    scale,
    x: (width - (minX + maxX) * scale) / 2,
    y: (height - (minY + maxY) * scale) / 2,
  };
  applyZoom();
}

function bindPanZoom() {
  const graph = $("graph");
  graph.addEventListener("wheel", (event) => {
    event.preventDefault();
    const factor = event.deltaY < 0 ? 1.12 : 0.89;
    state.zoom.scale = Math.max(0.1, Math.min(4, state.zoom.scale * factor));
    applyZoom();
  }, { passive: false });
  graph.addEventListener("pointerdown", (event) => {
    if (event.target.closest?.(".node, .edge-hit")) return;
    state.drag = { type: "pan", x: event.clientX, y: event.clientY, originX: state.zoom.x, originY: state.zoom.y };
    graph.setPointerCapture(event.pointerId);
  });
  graph.addEventListener("pointermove", (event) => {
    if (!state.drag) return;
    if (state.drag.type === "pan") {
      state.zoom.x = state.drag.originX + event.clientX - state.drag.x;
      state.zoom.y = state.drag.originY + event.clientY - state.drag.y;
      applyZoom();
    } else {
      const point = state.positions.get(state.drag.nodeId);
      point.x = (event.offsetX - state.zoom.x) / state.zoom.scale;
      point.y = (event.offsetY - state.zoom.y) / state.zoom.scale;
      updatePositions();
    }
  });
  graph.addEventListener("pointerup", () => { state.drag = null; });
  graph.addEventListener("pointercancel", () => { state.drag = null; });
}

function startNodeDrag(event) {
  event.stopPropagation();
  const nodeId = event.currentTarget.dataset.id;
  state.positions.get(nodeId).fixed = true;
  state.drag = { type: "node", nodeId };
  $("graph").setPointerCapture(event.pointerId);
}

function applyZoom() {
  $("viewport").setAttribute("transform", `translate(${state.zoom.x},${state.zoom.y}) scale(${state.zoom.scale})`);
}

function configureChat() {
  const openai = state.chatStatus.providers.openai;
  const option = $("chat-provider").querySelector('option[value="openai"]');
  option.disabled = !openai.available;
  option.textContent = openai.available
    ? `OpenAI high-quality · ${openai.model}`
    : "OpenAI high-quality · API key required";
  if (openai.available) $("chat-provider").value = "openai";
  $("chat-provider-note").textContent = openai.available
    ? `Model reasoning is grounded in a bounded evidence package. Model: ${openai.model}.`
    : "Local mode works offline. Set OPENAI_API_KEY before launch to enable model reasoning.";
  $("chat-provider").addEventListener("change", () => {
    const selected = $("chat-provider").value;
    $("chat-provider-note").textContent = selected === "openai"
      ? `Model reasoning is grounded in a bounded evidence package. Model: ${openai.model}.`
      : "Deterministic answer assembled locally from visible graph facts.";
  });
}

function switchRightPanel(view) {
  const chat = view === "chat";
  const factory = view === "factory";
  const portfolio = view === "portfolio";
  const recovery = view === "recovery";
  const evaluation = view === "evaluation";
  const memory = view === "memory";
  const data = view === "data";
  const runtime = view === "runtime";
  const audit = view === "audit";
  $("chat-view").hidden = !chat;
  $("factory-view").hidden = !factory;
  $("portfolio-view").hidden = !portfolio;
  $("recovery-view").hidden = !recovery;
  $("evaluation-view").hidden = !evaluation;
  $("memory-view").hidden = !memory;
  $("data-view").hidden = !data;
  $("runtime-view").hidden = !runtime;
  $("audit-view").hidden = !audit;
  $("inspector-view").hidden = chat || factory || portfolio || recovery || evaluation || memory || data || runtime || audit;
  $("chat-tab").classList.toggle("active", chat);
  $("factory-tab").classList.toggle("active", factory);
  $("portfolio-tab").classList.toggle("active", portfolio);
  $("recovery-tab").classList.toggle("active", recovery);
  $("evaluation-tab").classList.toggle("active", evaluation);
  $("memory-tab").classList.toggle("active", memory);
  $("data-tab").classList.toggle("active", data);
  $("runtime-tab").classList.toggle("active", runtime);
  $("audit-tab").classList.toggle("active", audit);
  $("inspector-tab").classList.toggle("active", !chat && !factory && !portfolio && !recovery && !evaluation && !memory && !data && !runtime && !audit);
}

async function loadData() {
  try {
    const summary = await api("/api/data/summary");
    state.dataSummary = summary;
    const cards = $("data-summary");
    cards.replaceChildren();
    [[summary.statistics.columns, "columns"], [summary.statistics.constraints, "constraints"], [summary.statistics.indexes, "indexes"], [summary.statistics.fixture_rows, "fixture rows"]].forEach(([value, label]) => {
      const card = document.createElement("div");
      const number = document.createElement("strong"); number.textContent = formatNumber(value);
      const text = document.createElement("span"); text.textContent = label;
      card.append(number, text); cards.appendChild(card);
    });
    const posture = $("data-posture");
    posture.className = `audit-posture ${summary.production_ready ? "passed" : "blocked"}`;
    posture.replaceChildren();
    const title = document.createElement("strong"); title.textContent = summary.production_ready ? "Production evidence complete" : "Development proof only";
    const detail = document.createElement("p"); detail.textContent = `${summary.source_table} → ${summary.target_table} · ${summary.evidence_class}`;
    posture.append(title, detail);
    const targets = $("data-targets"); targets.replaceChildren();
    (summary.targets || []).forEach((target) => {
      const card = document.createElement("article"); card.className = `factory-run ${target.status === "passed" ? "passed" : "blocked"}`;
      const heading = document.createElement("strong"); heading.textContent = target.dialect;
      const status = document.createElement("span"); status.className = "answer-badge"; status.textContent = `${target.status} · ${target.evidence}`;
      const table = document.createElement("code"); table.textContent = target.target_table;
      const identity = document.createElement("small"); identity.textContent = target.image_identity ? `image ${target.image_identity}` : "No live container receipt yet";
      card.append(heading, status, table, identity); targets.appendChild(card);
    });
    const checks = $("data-checks"); checks.replaceChildren();
    Object.entries(summary.checks || {}).forEach(([name, passed]) => {
      const row = document.createElement("div"); row.className = `factory-gate ${passed ? "passed" : "failed"}`;
      const status = document.createElement("strong"); status.textContent = passed ? "passed" : "blocked";
      const label = document.createElement("span"); label.textContent = name.replaceAll("_", " ");
      row.append(status, label); checks.appendChild(row);
    });
    $("data-gaps").textContent = (summary.gaps || []).join(" · ") || "No declared gaps";
    $("data-receipt-hash").textContent = summary.content_sha256 || "No receipt";
  } catch (error) { setError(error); }
}

async function loadPortfolio() {
  try {
    state.portfolio = await api("/api/portfolio/summary");
    const portfolio = state.portfolio;
    const posture = $("portfolio-posture");
    const approvalRequired = Boolean(portfolio.approval?.required);
    posture.className = `audit-posture ${approvalRequired ? "blocked" : "passed"}`;
    posture.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = approvalRequired ? "Human approval required" : "Ready for bounded dispatch";
    const detail = document.createElement("p");
    detail.textContent = approvalRequired
      ? `${(portfolio.approval?.required_order_ids || []).length} high-risk work cell(s) must be approved against this exact plan hash.`
      : "No high-risk work cells or critical conflicts require approval.";
    const authority = document.createElement("small");
    authority.textContent = "Approval authority: human only · projection: read only";
    posture.append(title, detail, authority);

    const waves = $("portfolio-waves");
    waves.replaceChildren();
    (portfolio.waves || []).forEach((wave) => {
      const row = document.createElement("div");
      row.className = "portfolio-wave";
      const label = document.createElement("strong");
      label.textContent = `Wave ${wave.wave}`;
      const cells = document.createElement("div");
      wave.work_order_ids.forEach((id) => {
        const item = document.createElement("code");
        item.textContent = id;
        cells.appendChild(item);
      });
      row.append(label, cells);
      waves.appendChild(row);
    });

    const conflicts = $("portfolio-conflicts");
    conflicts.replaceChildren();
    (portfolio.conflicts || []).forEach((conflict) => {
      const row = document.createElement("div");
      row.className = `factory-gate ${conflict.severity === "critical" ? "failed" : "passed"}`;
      const severity = document.createElement("strong");
      severity.textContent = conflict.severity;
      const purpose = document.createElement("span");
      purpose.textContent = `${conflict.kind.replaceAll("_", " ")} · ${conflict.resolution}`;
      const id = document.createElement("code");
      id.textContent = conflict.id.slice(-10);
      row.append(severity, purpose, id);
      conflicts.appendChild(row);
    });
    if (!portfolio.conflicts?.length) conflicts.textContent = "No conflicts detected.";

    const orders = $("portfolio-orders");
    orders.replaceChildren();
    (portfolio.orders || []).forEach((order) => {
      const row = document.createElement("div");
      row.className = `factory-run ${["high", "critical"].includes(order.risk) ? "blocked" : "passed"}`;
      const title = document.createElement("strong");
      title.textContent = order.title;
      const risk = document.createElement("span");
      risk.textContent = `${order.risk} risk`;
      const id = document.createElement("code");
      id.textContent = order.id;
      row.append(title, risk, id);
      orders.appendChild(row);
    });
    $("portfolio-plan-hash").textContent = portfolio.content_sha256 || "No portfolio plan snapshot";
  } catch (error) {
    setError(error);
  }
}

async function loadRecovery() {
  try {
    state.recovery = await api("/api/durable/summary");
    const snapshot = state.recovery;
    const stats = snapshot.statistics || {};
    const configured = snapshot.status === "passed";
    const posture = $("recovery-posture");
    const unsafe = (stats.states?.dead_letter || 0) + (stats.states?.blocked || 0);
    posture.className = `audit-posture ${configured && unsafe === 0 ? "passed" : "blocked"}`;
    posture.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = !configured ? "No durable database configured" : unsafe ? "Operator attention required" : "Recovery posture healthy";
    const detail = document.createElement("p");
    detail.textContent = !configured
      ? "Initialize work/durable/control.sqlite3 to observe live queue state."
      : `${stats.work_items || 0} work cell(s), ${stats.events || 0} durable event(s), ${unsafe} blocked or dead-lettered.`;
    posture.append(title, detail);

    const metrics = $("recovery-metrics");
    metrics.replaceChildren();
    [["Runs", stats.runs], ["Queued", stats.states?.queued], ["Running", stats.states?.running], ["Passed", stats.states?.passed], ["Dead", stats.states?.dead_letter], ["Approvals", stats.consumed_approvals]].forEach(([label, value]) => {
      const row = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = value || 0;
      const span = document.createElement("span");
      span.textContent = label;
      row.append(strong, span);
      metrics.appendChild(row);
    });

    const runs = $("recovery-runs");
    runs.replaceChildren();
    (snapshot.runs || []).forEach((run) => {
      const row = document.createElement("div");
      row.className = `factory-run ${run.state === "passed" ? "passed" : "blocked"}`;
      const title = document.createElement("strong"); title.textContent = run.run_id;
      const stateLabel = document.createElement("span"); stateLabel.textContent = run.state;
      const hash = document.createElement("code"); hash.textContent = (run.plan_sha256 || "").slice(0, 12);
      row.append(title, stateLabel, hash); runs.appendChild(row);
    });
    const items = $("recovery-items");
    items.replaceChildren();
    (snapshot.items || []).forEach((item) => {
      const row = document.createElement("div");
      row.className = `factory-run ${item.state === "passed" ? "passed" : "blocked"}`;
      const title = document.createElement("strong"); title.textContent = item.work_order_id;
      const stateLabel = document.createElement("span"); stateLabel.textContent = `${item.state} · attempt ${item.attempt}/${item.max_attempts}`;
      const wave = document.createElement("code"); wave.textContent = `wave ${item.wave}`;
      row.append(title, stateLabel, wave); items.appendChild(row);
    });
    const events = $("recovery-events");
    events.replaceChildren();
    (snapshot.events || []).slice(-30).reverse().forEach((event) => {
      const row = document.createElement("li");
      const title = document.createElement("strong"); title.textContent = event.kind.replaceAll("_", " ");
      const detail = document.createElement("span"); detail.textContent = `${event.run_id}${event.item_id ? ` · ${event.item_id}` : ""}`;
      row.append(title, detail); events.appendChild(row);
    });
    $("recovery-hash").textContent = snapshot.content_sha256 || "No durable snapshot";
  } catch (error) {
    setError(error);
  }
}

async function loadMemory(selectLatest = true) {
  try {
    state.memorySummary = await api("/api/memory/summary");
    const stats = state.memorySummary.statistics || {};
    const metrics = $("memory-metrics");
    metrics.replaceChildren();
    [
      ["Experiences", stats.experience_count || 0],
      ["Positive", (stats.outcomes || {}).verified_success || 0],
      ["Unchanged", (stats.outcomes || {}).accept_unchanged || 0],
      ["Negative", (stats.outcomes || {}).verified_failure || 0],
      ["Graph nodes", stats.covered_graph_nodes || 0],
      ["Paths", stats.covered_paths || 0],
    ].forEach(([label, value]) => {
      const item = document.createElement("div");
      const amount = document.createElement("strong");
      amount.textContent = String(value);
      const caption = document.createElement("span");
      caption.textContent = label;
      item.append(amount, caption);
      metrics.appendChild(item);
    });
    const list = $("memory-experiences");
    list.replaceChildren();
    const experiences = state.memorySummary.experiences || [];
    $("memory-empty").hidden = experiences.length > 0;
    experiences.forEach((experience) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `factory-run ${experience.outcome_class === "verified_failure" ? "blocked" : "passed"}`;
      button.dataset.experienceId = experience.experience_id;
      const title = document.createElement("strong");
      title.textContent = experience.summary || experience.work_order_id;
      const meta = document.createElement("span");
      meta.textContent = `${experience.outcome_class.replaceAll("_", " ")} · ${experience.evidence_class}`;
      const identity = document.createElement("code");
      identity.textContent = experience.experience_id;
      button.append(title, meta, identity);
      button.addEventListener("click", () => loadExperience(experience.experience_id));
      list.appendChild(button);
    });
    $("memory-snapshot-hash").textContent = state.memorySummary.snapshot_sha256 || "No memory snapshot";
    if (selectLatest && experiences.length) await loadExperience(experiences[0].experience_id);
    if (!experiences.length) $("memory-detail").hidden = true;
  } catch (error) {
    setError(error);
  }
}

async function loadExperience(experienceId) {
  try {
    const experience = await api("/api/memory/experience", { id: experienceId });
    document.querySelectorAll("#memory-experiences .factory-run").forEach((item) => {
      item.classList.toggle("active", item.dataset.experienceId === experienceId);
    });
    $("memory-detail").hidden = false;
    $("memory-title").textContent = experience.knowledge.summary;
    $("memory-id").textContent = experience.experience_id;
    $("memory-badges").replaceChildren(
      answerBadge(experience.outcome.class, experience.outcome.class === "verified_failure" ? "low" : "high"),
      answerBadge(experience.evidence_class),
      answerBadge(`${experience.outcome.attempts} attempt${experience.outcome.attempts === 1 ? "" : "s"}`),
    );
    const lessons = $("memory-lessons");
    lessons.replaceChildren();
    (experience.knowledge.lessons || []).forEach((lesson) => {
      const item = document.createElement("li");
      item.textContent = lesson;
      lessons.appendChild(item);
    });
    const bindings = $("memory-bindings");
    bindings.replaceChildren();
    [...(experience.scope.graph_node_ids || []), ...(experience.scope.paths || [])].forEach((binding) => {
      const code = document.createElement("code");
      code.textContent = binding;
      bindings.appendChild(code);
    });
    $("memory-experience-hash").textContent = experience.content_sha256;
  } catch (error) {
    setError(error);
  }
}

async function loadEvaluations(selectLatest = true) {
  try {
    const payload = await api("/api/evaluations", { limit: 50 });
    state.evaluations = payload.evaluations || [];
    const container = $("evaluation-runs");
    container.replaceChildren();
    $("evaluation-empty").hidden = state.evaluations.length > 0;
    state.evaluations.forEach((evaluation) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `factory-run ${evaluation.quality_status === "qualified" ? "passed" : "blocked"}`;
      button.dataset.evaluationKey = evaluation.evaluation_key;
      const title = document.createElement("strong");
      title.textContent = evaluation.evaluation_id;
      const meta = document.createElement("span");
      meta.textContent = `${evaluation.quality_status} · ${evaluation.cases} cases · ${Math.round((evaluation.repair_rate || 0) * 100)}% repair`;
      const identity = document.createElement("code");
      identity.textContent = evaluation.evaluation_class;
      button.append(title, meta, identity);
      button.addEventListener("click", () => loadEvaluation(evaluation.evaluation_key));
      container.appendChild(button);
    });
    if (selectLatest && state.evaluations.length) {
      await loadEvaluation(state.evaluations[0].evaluation_key);
    } else if (!state.evaluations.length) {
      $("evaluation-detail").hidden = true;
    }
  } catch (error) {
    setError(error);
  }
}

async function loadEvaluation(evaluationKey) {
  try {
    const receipt = await api("/api/evaluation", { id: evaluationKey });
    const quality = receipt.quality_gate || { status: "unreported", metrics: {}, checks: {} };
    document.querySelectorAll("#evaluation-runs .factory-run").forEach((item) => {
      item.classList.toggle("active", item.dataset.evaluationKey === evaluationKey);
    });
    $("evaluation-detail").hidden = false;
    $("evaluation-title").textContent = receipt.evaluation_id;
    $("evaluation-id").textContent = `${receipt.evaluation_class} · ${receipt.cases} completed cases`;
    $("evaluation-badges").replaceChildren(
      answerBadge(receipt.status, ["passed", "verified"].includes(receipt.status) ? "high" : "low"),
      answerBadge(quality.status, quality.status === "qualified" ? "high" : "low"),
      answerBadge(`${receipt.false_acceptances || 0} false acceptances`, receipt.false_acceptances ? "low" : "high"),
    );
    const metrics = $("evaluation-metrics");
    metrics.replaceChildren();
    const displayed = [
      [quality.metrics.repair_rate, "repair rate", true],
      [quality.metrics.correct_no_change_rate, "correct no-change", true],
      [quality.metrics.first_attempt_repair_rate, "first-attempt", true],
      [quality.metrics.evidence_selection_precision, "evidence precision", true],
      [quality.metrics.average_input_tokens, "average input tokens", false],
      [quality.metrics.estimated_cost_usd, "estimated cost USD", false],
    ];
    displayed.forEach(([value, label, percentage]) => {
      const card = document.createElement("div");
      const number = document.createElement("strong");
      number.textContent = percentage ? `${Math.round((value || 0) * 100)}%` : String(value ?? 0);
      const text = document.createElement("span");
      text.textContent = label;
      card.append(number, text);
      metrics.appendChild(card);
    });
    const checks = $("evaluation-checks");
    checks.replaceChildren();
    Object.entries(quality.checks || {}).forEach(([name, passed]) => {
      const row = document.createElement("div");
      row.className = `factory-gate ${passed ? "passed" : "failed"}`;
      const status = document.createElement("strong");
      status.textContent = passed ? "passed" : "blocked";
      const label = document.createElement("span");
      label.textContent = name.replaceAll("_", " ");
      row.append(status, label);
      checks.appendChild(row);
    });
    $("evaluation-limitations").textContent = (receipt.limitations || []).join(" ");
    $("evaluation-receipt-hash").textContent = receipt.content_sha256;
  } catch (error) {
    setError(error);
  }
}

async function loadAudit(selectLatest = true) {
  try {
    const [summary, timeline] = await Promise.all([
      api("/api/audit/summary"),
      api("/api/audit/events", { audience: $("audience").value, limit: 100 }),
    ]);
    state.auditSummary = summary;
    state.auditEvents = timeline.events || [];
    const stats = summary.statistics || {};
    const cards = $("audit-summary");
    cards.replaceChildren();
    [
      [stats.event_count || 0, "events"],
      [(stats.decisions?.blocked || 0), "blocked"],
      [stats.active_exceptions || 0, "exceptions"],
      [summary.trust_posture?.execution_status || "not evaluated", "execution"],
      [summary.trust_posture?.signed_checkpoint ? "yes" : "no", "signed"],
    ].forEach(([value, label]) => {
      const card = document.createElement("div");
      const number = document.createElement("strong");
      number.textContent = typeof value === "number" ? formatNumber(value) : value;
      const text = document.createElement("span");
      text.textContent = label;
      card.append(number, text);
      cards.appendChild(card);
    });
    const posture = summary.trust_posture || {};
    const posturePanel = $("audit-posture");
    posturePanel.className = `audit-posture ${posture.promotion_status || "not_evaluated"}`;
    posturePanel.replaceChildren();
    const postureTitle = document.createElement("strong");
    postureTitle.textContent = `Promotion ${String(posture.promotion_status || "not evaluated").replaceAll("_", " ")}`;
    const postureText = document.createElement("p");
    postureText.textContent = (posture.unresolved_gaps || []).length
      ? `Unresolved gates: ${posture.unresolved_gaps.join(", ")}.`
      : "No unresolved promotion gates.";
    posturePanel.append(postureTitle, postureText);
    renderAuditDecisionList("audit-execution", summary.execution_decisions || [], "No hardened execution decision recorded.");
    renderAuditDecisionList("audit-decisions", summary.promotion_decisions || [], "No promotion decisions recorded.");
    renderAuditTimeline(state.auditEvents);
    $("audit-checkpoint").textContent = summary.checkpoint?.ledger_head_sha256 || "No checkpoint";
    if (selectLatest && summary.promotion_decisions?.length) {
      await loadAuditDecision(summary.promotion_decisions.at(-1).id);
    }
  } catch (error) {
    setError(error);
  }
}

function renderAuditDecisionList(containerId, decisions, emptyMessage) {
  const container = $(containerId);
  container.replaceChildren();
  decisions.forEach((decision) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `factory-run ${decision.status}`;
    const title = document.createElement("strong");
    title.textContent = decision.subject_id;
    const status = document.createElement("span");
    status.textContent = `${decision.status} · ${decision.gaps.length} gaps`;
    const id = document.createElement("code");
    id.textContent = decision.id;
    button.append(title, status, id);
    button.addEventListener("click", () => loadAuditDecision(decision.id));
    container.appendChild(button);
  });
  if (!decisions.length) container.textContent = emptyMessage;
}

async function loadAuditDecision(decisionId) {
  const decision = await api("/api/audit/decision", { id: decisionId });
  if (decision.policy_id === "release.promotion") state.auditReleaseId = decision.subject_id;
  const dossier = $("audit-dossier");
  dossier.className = `audit-dossier ${decision.status}`;
  dossier.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = `${decision.status.toUpperCase()} · ${decision.policy_id}`;
  const rationale = document.createElement("p");
  rationale.textContent = decision.rationale;
  const evidenceClass = document.createElement("small");
  evidenceClass.textContent = decision.inputs?.evidence_class
    ? `Evidence class: ${decision.inputs.evidence_class.replaceAll("-", " ")}`
    : "";
  const hash = document.createElement("code");
  hash.textContent = decision.content_sha256;
  dossier.append(title, rationale);
  if (evidenceClass.textContent) dossier.append(evidenceClass);
  dossier.append(hash);
}

function renderAuditTimeline(events) {
  const list = $("audit-events");
  list.replaceChildren();
  events.forEach((event) => {
    const item = document.createElement("li");
    const marker = document.createElement("span");
    const decisionStatus = event.details?.decision?.status;
    marker.className = `station-state ${decisionStatus || "passed"}`;
    marker.textContent = event.actor.role;
    const content = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = event.action.replaceAll(".", " ").replaceAll("_", " ");
    const meta = document.createElement("small");
    meta.textContent = `${event.sequence} · ${event.subject.id} · ${event.event_sha256.slice(0, 12)}`;
    content.append(title, meta);
    item.append(marker, content);
    list.appendChild(item);
  });
}

async function loadAuditDossier() {
  if (!state.auditReleaseId) return;
  try {
    const dossier = await api("/api/audit/dossier", { release: state.auditReleaseId });
    const panel = $("audit-dossier");
    panel.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = `${dossier.status.toUpperCase()} · ${dossier.release_id}`;
    const rationale = document.createElement("p");
    rationale.textContent = dossier.rationale;
    const inventory = document.createElement("p");
    inventory.textContent = `${dossier.evidence_inventory.length} evidence items · ${dossier.runtime_decisions.length} runtime decisions · ${dossier.execution_decisions.length} execution decisions · ${dossier.gaps.length} unresolved gaps`;
    const hash = document.createElement("code");
    hash.textContent = dossier.content_sha256;
    panel.append(title, rationale, inventory, hash);
  } catch (error) {
    setError(error);
  }
}

function renderRuntimeProjection(runtime, container) {
  const projection = runtime || { state: "static_only", confidence: 0.35, observation_count: 0, evidence_classes: [], operations: [] };
  container.className = `runtime-projection ${projection.state}`;
  container.replaceChildren();
  const stateLabel = document.createElement("strong");
  stateLabel.textContent = projection.state.replaceAll("_", " ");
  const confidence = document.createElement("span");
  confidence.textContent = `${Math.round((projection.confidence || 0) * 100)}% trust · ${projection.observation_count || 0} observations`;
  const classes = document.createElement("code");
  classes.textContent = (projection.evidence_classes || []).join(" · ") || "No runtime evidence attached";
  const operations = document.createElement("span");
  operations.textContent = (projection.operations || []).join(", ");
  container.append(stateLabel, confidence, classes);
  if (operations.textContent) container.appendChild(operations);
}

async function loadRuntimeRuns(selectLatest = true) {
  try {
    const payload = await api("/api/runtime/summary");
    state.runtimeRuns = payload.runs || [];
    const stats = payload.statistics || {};
    const summary = $("runtime-summary");
    summary.replaceChildren();
    [[stats.run_count || 0, "runs"], [stats.event_count || 0, "events"], [stats.contradicted_edges || 0, "contradictions"]].forEach(([value, label]) => {
      const card = document.createElement("div");
      const number = document.createElement("strong");
      number.textContent = formatNumber(value);
      const text = document.createElement("span");
      text.textContent = label;
      card.append(number, text);
      summary.appendChild(card);
    });
    const container = $("runtime-runs");
    container.replaceChildren();
    $("runtime-empty").hidden = state.runtimeRuns.length > 0;
    state.runtimeRuns.forEach((run) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `factory-run ${run.development_status}`;
      const title = document.createElement("strong");
      title.textContent = run.source_system;
      const meta = document.createElement("span");
      meta.textContent = `${run.event_count} events · mainframe ${run.mainframe_status}`;
      const identity = document.createElement("code");
      identity.textContent = run.run_id;
      button.append(title, meta, identity);
      button.dataset.runId = run.run_id;
      button.addEventListener("click", () => loadRuntimeRun(run.run_id));
      container.appendChild(button);
    });
    if (selectLatest && state.runtimeRuns.length) await loadRuntimeRun(state.runtimeRuns[0].run_id);
    if (!state.runtimeRuns.length) $("runtime-detail").hidden = true;
  } catch (error) {
    setError(error);
  }
}

async function loadRuntimeRun(runId) {
  try {
    const run = await api("/api/runtime/run", { id: runId });
    document.querySelectorAll("#runtime-runs .factory-run").forEach((item) => {
      item.classList.toggle("active", item.dataset.runId === runId);
    });
    $("runtime-detail").hidden = false;
    $("runtime-title").textContent = run.source_system;
    $("runtime-id").textContent = `${run.run_id} · ${run.adapter_id}`;
    $("runtime-badges").replaceChildren(
      answerBadge(run.policies.development_readiness.status, run.policies.development_readiness.status === "passed" ? "high" : "low"),
      answerBadge(`mainframe ${run.policies.mainframe_equivalence.status}`, run.policies.mainframe_equivalence.status === "passed" ? "high" : "low"),
      answerBadge(`${run.event_count} events`),
    );
    const policies = $("runtime-policies");
    policies.replaceChildren();
    Object.entries(run.policies).forEach(([name, policy]) => {
      const row = document.createElement("div");
      row.className = `factory-gate ${policy.status}`;
      const status = document.createElement("strong");
      status.textContent = policy.status;
      const label = document.createElement("span");
      label.textContent = name.replaceAll("_", " ");
      const gaps = document.createElement("code");
      gaps.textContent = `${(policy.gaps || []).length} gaps`;
      row.append(status, label, gaps);
      policies.appendChild(row);
    });
    const events = $("runtime-events");
    events.replaceChildren();
    run.events.forEach((event) => {
      const item = document.createElement("li");
      const marker = document.createElement("span");
      marker.className = `station-state ${event.assertion === "observed" ? "passed" : "blocked"}`;
      marker.textContent = event.evidence_class;
      const content = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = event.operation.replaceAll("_", " ");
      const meta = document.createElement("small");
      meta.textContent = event.entity_id;
      content.append(title, meta);
      item.append(marker, content);
      events.appendChild(item);
    });
    $("runtime-limitations").textContent = (run.limitations || []).join(" ");
    $("runtime-receipt-hash").textContent = run.content_sha256;
  } catch (error) {
    setError(error);
  }
}

async function loadFactoryRuns(selectLatest = true) {
  try {
    const payload = await api("/api/factory/runs", { limit: 50 });
    state.factoryRuns = payload.runs || [];
    const container = $("factory-runs");
    container.replaceChildren();
    $("factory-empty").hidden = state.factoryRuns.length > 0;
    state.factoryRuns.forEach((run) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `factory-run ${run.status}`;
      const title = document.createElement("strong");
      title.textContent = run.title;
      const meta = document.createElement("span");
      meta.textContent = `${run.status} · ${run.attempts} attempt${run.attempts === 1 ? "" : "s"}`;
      const identity = document.createElement("code");
      identity.textContent = run.run_id;
      button.append(title, meta, identity);
      button.dataset.runKey = run.run_key;
      button.addEventListener("click", () => loadFactoryRun(run.run_key));
      container.appendChild(button);
    });
    if (selectLatest && state.factoryRuns.length) {
      await loadFactoryRun(state.factoryRuns[0].run_key);
    } else if (!state.factoryRuns.length) {
      $("factory-detail").hidden = true;
    }
  } catch (error) {
    setError(error);
  }
}

async function loadFactoryRun(runKey) {
  try {
    const payload = await api("/api/factory/run", {
      id: runKey,
      audience: $("audience").value,
    });
    const receipt = payload.receipt;
    const summary = state.factoryRuns.find((item) => item.run_key === runKey);
    document.querySelectorAll("#factory-runs .factory-run").forEach((item) => {
      item.classList.toggle("active", item.dataset.runKey === runKey);
    });
    $("factory-detail").hidden = false;
    $("factory-title").textContent = summary?.title || receipt.work_order_id;
    $("factory-id").textContent = receipt.run_id;
    const badges = $("factory-badges");
    badges.replaceChildren(
      answerBadge(receipt.status, receipt.status === "passed" ? "high" : "low"),
      answerBadge(`${receipt.attempts} attempt${receipt.attempts === 1 ? "" : "s"}`),
      answerBadge(`${receipt.event_count} events`),
    );
    renderFactoryGates(receipt.verification?.gates || []);
    renderFactorySecurity(receipt.execution_security);
    renderFactoryIntelligence(receipt.intelligence);
    renderFactoryTimeline(payload.events || []);
    const paths = $("factory-paths");
    paths.replaceChildren();
    (receipt.changed_paths || []).forEach((path) => {
      const code = document.createElement("code");
      code.textContent = path;
      paths.appendChild(code);
    });
    if (!receipt.changed_paths?.length) paths.textContent = "No accepted file changes.";
    $("factory-receipt-hash").textContent = receipt.content_sha256;
  } catch (error) {
    setError(error);
  }
}

function renderFactorySecurity(security) {
  const posture = security || {
    status: "advisory",
    backend: "host-process",
    production_ready: false,
    gaps: ["hardened-execution-not-configured"],
  };
  const container = $("factory-security");
  container.className = `audit-posture ${posture.production_ready ? "passed" : "blocked"}`;
  container.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = `${String(posture.status).replaceAll("_", " ")} · ${posture.backend}`;
  const detail = document.createElement("p");
  detail.textContent = posture.production_ready
    ? "Signed admission, scoped identities, and OCI gate isolation were enforced."
    : `Not production ready: ${(posture.gaps || []).join(", ") || "enforcement evidence missing"}.`;
  const evidence = document.createElement("small");
  const required = posture.required_agent_actions || [];
  const authorized = posture.authorized_agent_actions || [];
  evidence.textContent = posture.evidence_class
    ? `${posture.evidence_class.replaceAll("-", " ")} · ${authorized.length}/${required.length} required agent actions attested`
    : "No signed execution evidence attached";
  const hash = document.createElement("code");
  hash.textContent = posture.execution_policy_sha256 || "No hardened execution policy attached";
  container.append(title, detail, evidence, hash);
}

function renderFactoryIntelligence(intelligence) {
  const posture = intelligence || {
    mode: "unreported",
    provider: "unknown",
    model: null,
    calls: 0,
    input_tokens: 0,
    output_tokens: 0,
    estimated_cost_usd: 0,
  };
  const container = $("factory-intelligence");
  container.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = `${String(posture.mode).replaceAll("-", " ")} · ${posture.provider}`;
  const model = document.createElement("p");
  model.textContent = posture.model
    ? `Model ${posture.model}; ${posture.calls || 0} independently receipted call(s).`
    : "Deterministic reference worker; no model-performance claim is made.";
  const metrics = document.createElement("div");
  metrics.className = "factory-intelligence-metrics";
  [
    ["Calls", posture.calls || 0],
    ["Input tokens", posture.input_tokens || 0],
    ["Output tokens", posture.output_tokens || 0],
    [
      "Estimated cost",
      posture.cost_estimate_available
        ? `$${Number(posture.estimated_cost_usd || 0).toFixed(4)}`
        : "not configured",
    ],
  ].forEach(([label, value]) => {
    const item = document.createElement("span");
    const amount = document.createElement("b");
    amount.textContent = String(value);
    const caption = document.createElement("small");
    caption.textContent = label;
    item.append(amount, caption);
    metrics.appendChild(item);
  });
  const hash = document.createElement("code");
  hash.textContent = posture.content_sha256 || "No intelligence receipt attached";
  container.append(heading, model, metrics, hash);
}

function renderFactoryGates(gates) {
  const container = $("factory-gates");
  container.replaceChildren();
  gates.forEach((gate) => {
    const row = document.createElement("div");
    row.className = `factory-gate ${gate.status}`;
    const status = document.createElement("strong");
    status.textContent = gate.status;
    const name = document.createElement("span");
    name.textContent = gate.id;
    const hash = document.createElement("code");
    hash.textContent = gate.output_sha256.slice(0, 12);
    row.append(status, name, hash);
    container.appendChild(row);
  });
}

function renderFactoryTimeline(events) {
  const list = $("factory-timeline");
  list.replaceChildren();
  events.forEach((event) => {
    const item = document.createElement("li");
    const marker = document.createElement("span");
    marker.className = `station-state ${event.state.toLowerCase()}`;
    marker.textContent = event.state;
    const content = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = event.kind.replaceAll("_", " ");
    const meta = document.createElement("small");
    const extras = [
      `station ${event.sequence}`,
      event.payload?.attempt !== undefined ? `attempt ${event.payload.attempt}` : null,
      event.payload?.redacted ? "private artifact redacted" : null,
    ].filter(Boolean);
    meta.textContent = extras.join(" · ");
    content.append(title, meta);
    item.append(marker, content);
    list.appendChild(item);
  });
}

function resetChat() {
  state.chatHistory = [];
  const messages = $("chat-messages");
  messages.replaceChildren();
  const welcome = document.createElement("article");
  welcome.className = "chat-message assistant";
  const text = document.createElement("p");
  text.textContent = "Conversation cleared. Ask a question grounded in the current audience view.";
  welcome.appendChild(text);
  messages.appendChild(welcome);
}

async function submitChat(event) {
  event.preventDefault();
  const input = $("chat-question");
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  appendChatMessage("user", question);
  const loading = appendChatMessage("assistant loading", "Retrieving evidence and constructing a grounded answer…");
  $("send-chat").disabled = true;
  try {
    const answer = await apiPost("/api/chat", {
      question,
      focus_node_id: state.selectedId,
      focus_edge_id: state.selectedEdgeId,
      audience: $("audience").value,
      provider: $("chat-provider").value,
      depth: Number($("depth").value),
      history: state.chatHistory,
    });
    loading.remove();
    renderChatAnswer(answer);
    state.chatHistory.push({ role: "user", content: question });
    state.chatHistory.push({ role: "assistant", content: answer.answer });
    state.chatHistory = state.chatHistory.slice(-8);
    renderChatSuggestions(answer.follow_up_questions || []);
    highlightGrounding(
      answer.grounding.node_ids || [],
      answer.grounding.edge_ids || [],
    );
  } catch (error) {
    loading.remove();
    appendChatMessage("assistant", `I could not answer that question. ${error.message}`);
  } finally {
    $("send-chat").disabled = false;
    input.focus();
  }
}

function appendChatMessage(role, content) {
  const article = document.createElement("article");
  article.className = `chat-message ${role}`;
  const paragraph = document.createElement("p");
  paragraph.textContent = content;
  article.appendChild(paragraph);
  $("chat-messages").appendChild(article);
  article.scrollIntoView({ block: "end", behavior: "smooth" });
  return article;
}

function renderChatAnswer(answer) {
  const article = document.createElement("article");
  article.className = "chat-message assistant";
  const meta = document.createElement("div");
  meta.className = "answer-meta";
  meta.append(
    answerBadge(`${answer.confidence.level} confidence`, answer.confidence.level),
    answerBadge(answer.provider === "openai" ? answer.model : "local evidence"),
    answerBadge(`${answer.grounding.node_ids.length} nodes`),
  );
  const summary = document.createElement("p");
  summary.textContent = answer.answer;
  article.append(meta, summary);

  (answer.sections || []).forEach((section) => {
    const container = document.createElement("section");
    container.className = "answer-section";
    const heading = document.createElement("h4");
    heading.textContent = section.heading;
    const body = document.createElement("p");
    body.textContent = section.body;
    container.append(heading, body);
    if (section.citation_ids?.length) {
      const markers = document.createElement("small");
      markers.textContent = section.citation_ids.map((item) => `[${item}]`).join(" ");
      container.appendChild(markers);
    }
    article.appendChild(container);
  });

  if (answer.citations?.length) {
    const details = document.createElement("details");
    details.className = "answer-section";
    const summaryElement = document.createElement("summary");
    summaryElement.textContent = `Evidence (${answer.citations.length})`;
    const list = document.createElement("ol");
    list.className = "citation-list";
    answer.citations.forEach((citation) => {
      const item = document.createElement("li");
      const lines = citation.line_start
        ? `:${citation.line_start}${citation.line_end && citation.line_end !== citation.line_start ? `–${citation.line_end}` : ""}`
        : "";
      const path = document.createElement("code");
      path.textContent = `[${citation.id}] ${citation.path || citation.source_id}${lines}`;
      const provenance = document.createElement("span");
      provenance.textContent = ` · ${citation.confidence || "unclassified"} · ${citation.method || "source"}`;
      item.append(path, provenance);
      list.appendChild(item);
    });
    details.append(summaryElement, list);
    article.appendChild(details);
  }

  const notes = [answer.confidence.rationale, ...(answer.limitations || [])].filter(Boolean);
  if (notes.length) {
    const limitations = document.createElement("div");
    limitations.className = "limitations";
    limitations.textContent = notes.join(" ");
    article.appendChild(limitations);
  }
  $("chat-messages").appendChild(article);
  article.scrollIntoView({ block: "end", behavior: "smooth" });
}

function answerBadge(text, className = "") {
  const badge = document.createElement("span");
  badge.className = `answer-badge ${className}`.trim();
  badge.textContent = text;
  return badge;
}

function renderChatSuggestions(questions) {
  const container = $("chat-suggestions");
  container.replaceChildren();
  questions.slice(0, 4).forEach((question) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = question;
    container.appendChild(button);
  });
}

function highlightGrounding(nodeIds, edgeIds) {
  const grounded = new Set(nodeIds);
  const groundedEdges = new Set(edgeIds);
  document.querySelectorAll(".node").forEach((item) => {
    item.classList.toggle("grounded", grounded.has(item.dataset.id));
  });
  document.querySelectorAll(".edge").forEach((item) => {
    if (!item.classList.contains("selected")) {
      item.classList.toggle("active", groundedEdges.has(item.dataset.id));
    }
  });
}

function shorten(value, limit) { return value.length > limit ? `${value.slice(0, limit - 1)}…` : value; }

function setError(error) {
  $("status-dot").classList.remove("online");
  $("status-dot").classList.add("error");
  $("status-text").textContent = error.message;
  console.error(error);
}

initialize();
