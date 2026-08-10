"use strict";

const NS = "http://www.w3.org/2000/svg";
const state = {
  meta: null,
  chatStatus: null,
  chatHistory: [],
  selection: null,
  selectedId: null,
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
  dataset: "data", business_rule: "rule", modernization_workload: "rule",
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
    $("status-dot").classList.add("online");
    $("status-text").textContent = "Local graph online";
    populatePerspectives();
    populateLegend();
    configureChat();
    bindControls();
    await loadPerspective();
  } catch (error) {
    setError(error);
  }
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
  $("inspector-tab").addEventListener("click", () => switchRightPanel("inspector"));
  $("chat-tab").addEventListener("click", () => switchRightPanel("chat"));
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
    if (event.key === "/" && document.activeElement !== $("search")) {
      event.preventDefault();
      $("search").focus();
    }
  });
  bindPanZoom();
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
  document.querySelectorAll(".edge").forEach((element) => {
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
    document.querySelectorAll(".node").forEach((item) => item.classList.toggle("active", item.dataset.id === nodeId));
    document.querySelectorAll(".edge").forEach((item) => item.classList.toggle("active", item.dataset.source === nodeId || item.dataset.target === nodeId));
    $("inspector-placeholder").hidden = true;
    $("inspector").hidden = false;
    $("detail-kind").textContent = node.kind.replaceAll("_", " ");
    $("detail-kind").style.background = colors[groupFor(node.kind)];
    $("detail-name").textContent = node.name;
    $("detail-id").textContent = node.id;
    const statement = node.properties?.statement || "";
    $("detail-statement").textContent = statement;
    $("detail-statement").hidden = !statement;
    renderProperties(node.properties || {});
    renderEvidence(node.evidence || []);
    renderRelations(node);
    $("chat-focus").textContent = `${node.name} · ${node.kind.replaceAll("_", " ")}`;
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

function renderEvidence(evidence) {
  const container = $("detail-evidence");
  container.replaceChildren();
  if (!evidence.length) {
    container.textContent = "No node-level evidence; inspect connected derivation edges.";
    return;
  }
  evidence.forEach((item) => {
    const card = document.createElement("div");
    card.className = "evidence-card";
    const label = document.createElement("strong");
    label.textContent = `${item.confidence || "unclassified"} · ${item.method || "source"}`;
    const path = document.createElement("code");
    const lines = item.line_start ? `:${item.line_start}${item.line_end && item.line_end !== item.line_start ? `–${item.line_end}` : ""}` : "";
    path.textContent = `${item.path || item.source_id || "unknown"}${lines}`;
    card.append(label, path);
    container.appendChild(card);
  });
}

function renderRelations(node) {
  const container = $("detail-relations");
  container.replaceChildren();
  const relations = [
    ...node.incoming.map((edge) => ({ relation: `← ${edge.relation}`, target: edge.source })),
    ...node.outgoing.map((edge) => ({ relation: `${edge.relation} →`, target: edge.target })),
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
    button.addEventListener("click", () => {
      if (state.positions.has(item.target)) inspectNode(item.target);
      else loadNeighborhood(item.target);
    });
    container.appendChild(button);
  });
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
    if (event.target.closest?.(".node")) return;
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
  $("chat-view").hidden = !chat;
  $("inspector-view").hidden = chat;
  $("chat-tab").classList.toggle("active", chat);
  $("inspector-tab").classList.toggle("active", !chat);
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
    highlightGrounding(answer.grounding.node_ids || []);
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

function highlightGrounding(nodeIds) {
  const grounded = new Set(nodeIds);
  document.querySelectorAll(".node").forEach((item) => {
    item.classList.toggle("grounded", grounded.has(item.dataset.id));
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
