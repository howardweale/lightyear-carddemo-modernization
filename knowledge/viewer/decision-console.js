"use strict";
// Credentials and session tokens remain in memory, never URL/localStorage.
let token = "",
  current = "campaigns",
  selectedCampaign = null,
  timer = null;
const $ = (id) => document.getElementById(id),
  content = $("content");
function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function button(text, fn) {
  const b = el("button", text);
  b.addEventListener("click", () => Promise.resolve(fn()).catch(showError));
  return b;
}
function json(value) {
  return el("pre", JSON.stringify(value, null, 2));
}
function showError(e) {
  $("message").textContent = e.message || String(e);
}
async function api(route, data) {
  const r = await fetch("/api/tower/" + route, {
    method: data ? "POST" : "GET",
    headers: {
      Authorization: "Bearer " + token,
      ...(data ? { "Content-Type": "application/json" } : {}),
    },
    body: data ? JSON.stringify(data) : undefined,
  });
  const v = await r.json();
  if (!r.ok) throw Error(v.error);
  return v;
}
function drawer(title) {
  const d = $("drawer");
  d.replaceChildren(
    button("Close", () => {
      d.hidden = true;
    }),
    el("h2", title),
  );
  d.hidden = false;
  return d;
}
function badge(text) {
  return el("span", text, "badge");
}
async function load() {
  if (!token) return;
  clearTimeout(timer);
  const scopeInfo = await api("queue");
  for (const tab of document.querySelectorAll(".factory-tab")) tab.hidden = scopeInfo.session.scope !== "factory";
  $("message").textContent = "";
  try {
    await { campaigns, queue, catalogue, workspace, history, knowledge, businessRules, programs }[current]();
  } catch (e) {
    showError(e);
  }
  timer = setTimeout(load, document.hidden ? 30000 : 3000);
}
async function campaigns() {
  if (selectedCampaign) return campaign(selectedCampaign);
  const list = await api("campaigns");
  content.replaceChildren(el("h2", "Campaigns"));
  if (!list.campaigns.length) {
    content.append(
      el(
        "p",
        "No campaigns configured in this scope. Add a local campaign registry to observe published evidence.",
        "empty",
      ),
    );
    return;
  }
  const cards = el("div", undefined, "cards");
  for (const c of list.campaigns) {
    const card = el("article", undefined, "card");
    card.append(
      el("h3", c.id),
      badge(c.adapter),
      button("Review campaign", () => {
        selectedCampaign = c.id;
        return load();
      }),
    );
    cards.append(card);
  }
  content.append(cards);
}
async function campaign(id) {
  const v = await api("campaign?id=" + encodeURIComponent(id));
  content.replaceChildren(
    button("All campaigns", () => {
      selectedCampaign = null;
      return load();
    }),
    el("h2", id),
    badge(v.stale ? "stale" : (v.state || "observed")),
  );
  content.append(
    el(
      "p",
      v.controller_reads_tower_decisions
        ? "B06 controller consumes verified launch and pause decisions. The Tower records operator intent; it never starts or stops processes. Operator review; not independent."
        : v.status_export_schema ? "Read-only campaign status. Decision handling is defined by the campaign controller; the Tower never starts or stops processes."
        : "Frozen controller: decisions are recorded here, but this controller does not read them. Stop it outside the Tower if required.",
      "boundary",
    ),
  );
  for (const k of [
    "plan_sha256",
    "declaration_sha256",
    "snapshot_sha256",
    "authorization_sha256",
  ])
    content.append(el("p", k + ": " + (v[k] || "unavailable"), "hash"));
  content.append(
    button("Verify evidence", async () => {
      const fresh = await api("campaign?id=" + encodeURIComponent(id));
      drawer("Integrity verification").append(json(fresh.integrity));
    }),
  );
  const totals = v.totals || {};
  if (v.totals) content.append(
    el(
      "p",
      `${totals.cohort_passed ?? 0} passes · ${totals.cohort_completed ?? 0} completed cohort trials · pilots excluded`,
    ),
  );
  if (totals.wilson_95)
    content.append(
      el(
        "p",
        `Wilson 95% interval: ${(100 * totals.wilson_95.lower).toFixed(1)}–${(100 * totals.wilson_95.upper).toFixed(1)}%`,
      ),
    );
  for (const [k, limit] of Object.entries(v.limits || {})) {
    if (v.used?.[k] == null) {
      content.append(el("small", `${k}: unavailable / ${limit}`));
      continue;
    }
    const p = el("progress");
    p.max = limit || 1;
    p.value = v.used?.[k] || 0;
    content.append(el("small", `${k}: ${p.value} / ${limit}`), p);
  }
  if (v.fixture) content.append(el("p", "FIXTURE — zero-model integration rehearsal; not a measured result.", "boundary"));
  for (const j of v.journeys || []) {
    content.append(el("h3", `${j.id}: ${j.cohort_passed}/${j.cohort_completed} completed · ${j.planned} planned`));
    content.append(el("p", j.void ? "Journey VOID; no rate." :
      `${j.interim ? "Interim · " : ""}pilots excluded` + (j.wilson_95 ? ` · Wilson 95%: ${(100*j.wilson_95.lower).toFixed(1)}–${(100*j.wilson_95.upper).toFixed(1)}%` : "")));
  }
  if (v.calendar?.latest_launch_utc) content.append(el("p", `Latest launch (UTC): ${v.calendar.latest_launch_utc} · period closes ${v.calendar.period_end_exclusive_utc}`));
  if (v.pause) content.append(el("p", `Paused: ${v.pause.reasons.join(", ")}. Review ${v.pause.request_id} in the Work queue. The controller consumes the signed decision; the Tower does not control processes.`, "boundary"));
  const grid = el("div", undefined, "trial-grid");
  for (const t of v.trials) {
    const b = button(t.id, () => drawer(t.id).append(json(t)));
    b.className = "trial " + t.state;
    b.setAttribute("aria-label", t.id + " " + t.state);
    grid.append(b);
  }
  content.append(grid);
  if (v.verdicts) {
    const g = v.graph_projection;
    if (g) {
      content.append(el("h3", "Verify graph context"),
        el("p", `Projection: ${g.state} · ${g.mode || "off"} · ${g.projection_sha256 || "none"}`),
        el("p", "Public CardDemo reference only. Customer and Maintec source are not enabled. Approval expiry stops judge submissions and removes graph tools.", "boundary"));
      if (g.node_count !== undefined) content.append(el("p",
        `${g.node_count} nodes · ${g.edge_count} edges · ${g.excluded_count} exclusions · leak check ${g.leak_check}`));
      if (g.decision_sha256) {
        const link = el("a", `Tower decision ${g.decision_sha256}`);
        link.href = "#drawer";
        link.addEventListener("click", async (event) => {
          event.preventDefault();
          try {
            const journal = await api("history");
            const decision = journal.events.find((e) => e.kind === "tower_decision" &&
              e.content_sha256 === g.decision_sha256);
            if (!decision) throw Error("Decision is unavailable in this Tower scope.");
            drawer("Graph projection decision").append(json(decision));
          } catch (error) { showError(error); }
        });
        content.append(link);
      }
    }
    content.append(
      el("p", `Submissions: ${v.submissions}; refused requests: ${v.refusals}`),
    );
    for (const r of v.verdicts)
      content.append(el("p", `${r.id}: ${r.verdict} · receipt ${r.receipt_sha256} · context ${r.context_projection_sha256 || "none"}`));
  }
  for (const a of v.alerts || [])
    content.append(
      el(
        "div",
        a.code +
          " · " +
          [
            a.journey,
            a.budget ? `${a.budget} ${100*a.threshold}%` : "",
            a.diagnostic_class,
            (a.trials || []).join(", "),
          ].filter(Boolean).join(" "),
        "alert",
      ),
    );
  if (v.legacy_approvals?.length) content.append(json(v.legacy_approvals));
}
async function queue() {
  const v = await api("queue");
  content.replaceChildren(el("h2", "Work queue"));
  const filter = el("input");
  filter.placeholder = "Filter kind, role or scope";
  filter.setAttribute("aria-label", filter.placeholder);
  const list = el("div", undefined, "cards");
  const render = () => {
    list.replaceChildren();
    for (const i of v.items.filter((i) =>
      JSON.stringify([i.kind, i.scope, i.required_roles]).includes(
        filter.value,
      ),
    )) {
      const c = el("article", undefined, "card");
      c.append(
        el("h3", i.kind || i.id),
        badge(i.age?.overdue ? "Review overdue" : i.status),
        el("p", i.summary || "Invalid evidence — decision disabled."),
        el("small", (i.required_roles || []).join(", ")),
      );
      if (i.status === "review due") c.append(el("p", i.next_action));
      else if (i.status !== "invalid")
        c.append(
          button(i.decidable ? "Review and decide" : "View evidence", () =>
            review(i),
          ),
        );
      list.append(c);
    }
  };
  filter.addEventListener("input", render);
  render();
  content.append(filter, list);
}
async function knowledge() {
  const status = await api("knowledge");
  content.replaceChildren(el("h2", "Graph memory"), el("p", "Operator review; not independent attestation. Outcomes show correlation, not causation."));
  if (status.available) {
    content.append(el("h3", "Annotation health"), json(status.health), el("h3", "Routing policy and run shares"), json(status.routing), el("h3", "Search indexes"), json(status.search));
  } else content.append(el("p", "No signed knowledge status configured in this scope."));
  const q = await api("queue");
  const items = q.items.filter(i => ["graph-annotation", "graph-annotation-verified"].includes(i.kind));
  const selected = new Set();
  for (const item of items) {
    const row = el("article", undefined, "card"), select = el("input");
    select.type = "checkbox"; select.disabled = !item.decidable;
    select.setAttribute("aria-label", "Select " + item.id);
    select.addEventListener("change", () => select.checked ? selected.add(item.id) : selected.delete(item.id));
    row.append(select, badge(item.kind), badge(item.status), button("Review anchors and evidence", () => review(item)));
    content.append(row);
  }
  content.append(button("Review selected decisions", async () => {
    clearTimeout(timer);
    const rows = [];
    for (const id of selected) rows.push({...await api("review", {id}), outcomes:items.find(item=>item.id===id).outcomes});
    const d = drawer("Bulk annotation decisions"), form = el("form"), outcome = el("select");
    for (const value of ["approved", "rejected", "retired"]) { const o=el("option",value); o.value=value; outcome.append(o); }
    const inputs = {};
    for (const name of ["reason", "named_owner", "review_after"]) {
      const input=el("input"); input.required=true; if(name==="review_after") input.type="date";
      const label=el("label",name); label.append(input); form.append(label); inputs[name]=input;
    }
    for (const row of rows) d.append(json({id:row.id,bound:row.bound,evidence:row.evidence_view}));
    const submit=el("button","Record selected decisions"); submit.type="submit"; form.append(outcome,submit); d.append(form);
    form.addEventListener("submit",async e=>{
      e.preventDefault(); submit.disabled=true;
      try {
        for (const row of rows) {
          const value=row.kind==="graph-annotation-verified" && outcome.value==="approved" ? "verified" : outcome.value;
          if (!(row.outcomes || []).includes(value)) throw Error("Selected outcome is not allowed for " + row.id);
          await api("decide",{item_id:row.id,bound:row.bound,outcome:value,
            ...Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,v.value])),
            previous_decision_sha256:row.latest_decision?.content_sha256||null,request_id:crypto.randomUUID()});
        }
        d.hidden=true; await knowledge();
      } catch(error) { showError(error); } finally { submit.disabled=false; }
    });
  }));
}
async function review(item) {
  clearTimeout(timer);
  const i = await api(
    item.decidable ? "review" : "item?id=" + encodeURIComponent(item.id),
    item.decidable ? { id: item.id } : undefined,
  );
  const d = drawer(item.summary || item.id);
  d.append(badge(item.kind), json(i.bound), json(i.evidence_view));
  const graphReview = i.evidence_view?.records?.graph_review;
  if (graphReview) {
    d.append(el("h3", "Public graph projection review"),
      el("p", "Public CardDemo reference only; this does not authorize Maintec or customer source."),
      el("p", "Expiry is 00:00 UTC at the start of the review date. Allow time for the complete session; expiry stops judge submissions and removes graph tools."),
      el("p", graphReview.eligible ? "Review the bound source and acknowledge every listed public overlap hash in your reason." : "Approval blocked: protected matches or unsupported lane. Rejection remains available."));
    for (const token of graphReview.required_acknowledgments) d.append(el("code", token));
  }
  for (const anchor of i.evidence_view?.records?.annotation?.anchors || []) {
    const link=el("a",anchor); link.href="/?node="+encodeURIComponent(anchor); d.append(link);
  }
  if (item.scope === "carddemo-zos")
    d.append(el("p", "No record values are shown or released. Notes are retained only as hash commitments. Review local intake evidence separately. Operator review; not independent.", "boundary"));
  if (item.kind.startsWith("rule-") || item.kind === "qualification-acceptance")
    d.append(
      button("Validate bound evidence", async () =>
        d.append(
          json(await api("validation?id=" + encodeURIComponent(item.id))),
        ),
      ),
    );
  if (!item.decidable) {
    d.append(
      el(
        "p",
        "Read only for this credential. Required role: " +
          item.required_roles.join(", "),
      ),
    );
    return;
  }
  const form = el("form"),
    choice = el("select");
  for (const o of item.outcomes) {
    const n = el("option", o);
    n.value = o;
    if (
      ["approved", "accepted"].includes(o) &&
      (item.validation?.passed === false || graphReview?.eligible === false)
    )
      n.disabled = true;
    choice.append(n);
  }
  if (item.validation) d.append(json(item.validation));
  if (item.validation?.passed === false || graphReview?.eligible === false) choice.value = "rejected";
  form.append(el("label", "Decision"), choice);
  const fields = {};
  for (const name of item.required_fields) {
    const label = el("label", name.replaceAll("_", " ")),
      input = name === "reason" ? el("textarea") : el("input");
    input.required = true;
    if (name === "review_after") input.type = "date";
    if (name === "named_owner" && item.scope === "carddemo-zos") {
      input.value = "howard-weale";
      input.readOnly = true;
    }
    label.append(input);
    form.append(label);
    fields[name] = input;
  }
  const factoryContract = i.evidence_view?.records?.factory;
  const factoryInputs = {};
  let dependencyAcknowledgment;
  if (factoryContract) {
    d.append(el("p", "Public development. This records operator intent; it does not dispatch a campaign, spend money or release customer evidence.", "boundary"));
    for (const id of factoryContract.details.items || []) {
      const label = el("label", id), outcome = el("select"), reason = el("textarea");
      for (const value of ["", "accept", "reject", "investigate"]) {
        const option = el("option", value || "Choose item decision"); option.value = value; outcome.append(option);
      }
      outcome.required = true; reason.required = true; reason.setAttribute("aria-label", "Reason for " + id);
      label.append(outcome, reason); form.append(label); factoryInputs[id] = {outcome, reason};
    }
    if (factoryContract.kind === "legacy-behaviour-disposition") {
      form.append(el("p", "Choosing fix invalidates these dependent arguments:"), json(factoryContract.details.dependent_arguments));
      dependencyAcknowledgment = el("input"); dependencyAcknowledgment.type = "checkbox";
      const label = el("label", "I reviewed every dependent argument listed above"); label.append(dependencyAcknowledgment); form.append(label);
    }
  }
  let slot;
  if (item.kind === "evidence-release") {
    d.append(
      el(
        "p",
        item.scope === "carddemo-zos"
          ? "Release includes only the bound no-values bundle and both signed decisions. Notes appear only as hash commitments."
          : "The frozen export will include both release decisions, including your identity and reason. Review the complete bound bundle before approving.",
      ),
    );
    slot = el("select");
    for (const role of item.required_roles) {
      const n = el("option", role);
      n.value = role;
      slot.append(n);
    }
    form.append(el("label", "Release role"), slot);
  }
  form.append(
    el(
      "p",
      "You are recording authenticated intent. Required independence is enforced by the service. No verdict will change.",
      "boundary",
    ),
  );
  const itemChoices = {};
  for (const id of i.classification_item_ids || []) {
    const select = el("select");
    select.required = true;
    select.setAttribute("aria-label", "Classification decision for " + id);
    for (const value of ["", "accept", "reject"]) {
      const option = el("option", value || "Choose a decision");
      option.value = value;
      select.append(option);
    }
    itemChoices[id] = select;
    form.append(el("label", id), select);
  }
  const submit = el("button", "Record decision");
  submit.type = "submit";
  form.append(submit);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    submit.disabled = true;
    try {
      const p = {
        item_id: i.id,
        bound: i.bound,
        outcome: choice.value,
        ...(factoryContract ? {factory_items: Object.fromEntries(Object.entries(factoryInputs).map(([id, row]) => [id, {outcome: row.outcome.value, reason: row.reason.value}])),
          acknowledged_dependencies: dependencyAcknowledgment?.checked ? factoryContract.details.dependent_arguments : null} : {}),
        request_id: crypto.randomUUID(),
        previous_decision_sha256: i.latest_decision?.content_sha256 || null,
      };
      for (const [k, n] of Object.entries(fields)) p[k] = n.value;
      if (graphReview && p.outcome === "approved") {
        const acknowledged = new Set(p.reason.split(/\s+/));
        if (!graphReview.eligible) throw Error("Protected matches cannot be approved.");
        if (graphReview.required_acknowledgments.some(t => !acknowledged.has(t)))
          throw Error("Acknowledge every listed public-source hash in your reason after reviewing the source.");
      }
      if (Object.keys(itemChoices).length)
        p.item_decisions = Object.fromEntries(
          Object.entries(itemChoices).map(([id, select]) => [id, select.value]),
        );
      if (slot) {
        p.decision_slot = slot.value;
        p.previous_decision_sha256 =
          i.latest_decisions_by_role?.[slot.value] || null;
      }
      const result = await api("decide", p);
      d.replaceChildren(
        button("Close", () => {
          d.hidden = true;
          load();
        }),
        el("h2", "Decision recorded"),
        el("p", result.payload.independence),
        json(result),
      );
    } catch (err) {
      showError(err);
      submit.disabled = false;
    }
  });
  d.append(form);
}
async function catalogue() {
  const v = await api("catalogue");
  content.replaceChildren(el("h2", "Qualified lane catalogue"));
  if (!v.available) {
    content.append(el("p", v.limitation, "empty"));
    return;
  }
  if (v.entries.some((e) => e.qualification?.fixture_only))
    content.append(
      el(
        "p",
        "Fixture records — not production qualification evidence.",
        "alert",
      ),
    );
  content.append(el("p", "Signed catalogue " + v.catalogue_sha256, "hash"));
  const table = el("table"),
    head = el("tr");
  const targets = [...new Set(v.entries.map((r) => r.target_lane))].sort();
  const sources = [...new Set(v.entries.map((r) => r.source_lane))].sort();
  for (const h of ["Source / target", ...targets]) head.append(el("th", h));
  table.append(head);
  for (const source of sources) {
    const tr = el("tr");
    tr.append(el("th", source));
    for (const target of targets) {
      const td = el("td");
      const entries = v.entries.filter(
        (r) => r.source_lane === source && r.target_lane === target,
      );
      if (!entries.length) td.append(el("span", "No signed entry"));
      for (const r of entries) {
        td.append(button(r.status, () => drawer(r.id).append(json(r))));
        if (r.upcoming_expiry?.length)
          td.append(
            el("small", "Upcoming expiry: " + r.upcoming_expiry.join(", ")),
          );
        if (r.review_due?.length)
          td.append(
            el(
              "small",
              "Dependent rule review due: " + r.review_due.join(", "),
            ),
          );
      }
      tr.append(td);
    }
    table.append(tr);
  }
  content.append(table);
}

async function businessRules() {
  const v = await api("business-rules");
  content.replaceChildren(el("h2", "Lightyear business rules"));
  if (!v.available) content.append(el("p", "No authenticated rule requests in this scope."));
  for (const item of v.catalogues || []) {
    content.append(el("h3", item.request_id));
    for (const rule of item.catalogue.entries) {
      content.append(el("p", `${rule.id}: ${rule.statement} — ${rule.display_status || rule.status}; ${rule.applicable_count} applicable`));
      content.append(el("p", `${rule.agree_count} agree; ${rule.disagree_count} disagree; ${rule.indeterminate_count} indeterminate`));
      content.append(el("pre", JSON.stringify(rule.source, null, 2)));
      if (rule.first_disagreement) content.append(el("pre", JSON.stringify(rule.first_disagreement, null, 2)));
      content.append(el("p", `Evidence strength: ${rule.evidence_strength || "not assessed"} — ${rule.evidence_strength_reason || ""}`));
      const assessment = el("details"); assessment.append(el("summary", "Scenario adequacy and assessment"), json(rule.scenario_adequacy || "not reported"), json(rule.scenario_reasons || [])); content.append(assessment);
      content.append(el("small", `Receipt: ${rule.receipt_sha256}`, "hash"));
    }
    content.append(el("p", "Keep-or-fix decisions are reviewed and signed in the decision queue."));
  }
}
async function workspace() {
  const v = await api("workspace");
  content.replaceChildren(el("h2", v.title || "Customer workspace"));
  if (!v.configured) {
    content.append(
      el(
        "p",
        "No customer workspace configured. Each engagement uses its own data root, authority and journal.",
        "empty",
      ),
    );
    return;
  }
  if (v.scope === "carddemo-zos") {
    content.append(el("p", "Read-only arrival view. Counts, hashes and review status only. Open Work queue to review a request; record values remain in local intake files.", "boundary"));
    if (!v.arrivals.length) content.append(el("p", "No verified arrival requests yet."));
    for (const arrival of v.arrivals) {
      const card = el("article", undefined, "card");
      card.append(badge(arrival.status), el("p", `${arrival.runs} runs · ${arrival.files} files · ${arrival.findings} findings`),
        el("p", arrival.intake_sha256, "hash"));
      content.append(card);
    }
    return;
  }
  const labels = {
    equivalent: "verified equivalent",
    divergent: "differs: needs your decision",
    indeterminate: "couldn’t decide: more evidence needed",
  };
  for (const [k, n] of Object.entries(v.counts || {}))
    content.append(el("p", `${n} ${labels[k]}`));
  content.append(json(v));
}
async function history() {
  const v = await api("history");
  content.replaceChildren(el("h2", "Decision history"));
  for (const e of v.events
    .filter((e) => ["tower_decision", "tower_proposal"].includes(e.kind))
    .reverse()) {
    const c = el("article", undefined, "card");
    c.append(
      el("h3", e.payload.kind || e.payload.proposal_type),
      badge(e.payload.independence || e.payload.label),
      el("p", e.payload.reason || e.payload.text),
      el("small", e.actor.name + " · " + e.occurred_at),
      el("p", e.content_sha256, "hash"),
    );
    content.append(c);
  }
}
$("login").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const input = e.target.elements.credential;
    const s = await api("session", { credential: input.value });
    input.value = "";
    token = s.token;
    $("identity").textContent = s.actor.name + " · " + s.scope;
    $("login").hidden = true;
    load();
  } catch (err) {
    showError(err);
  }
});
document.querySelectorAll("[data-tab]").forEach((b) =>
  b.addEventListener("click", () => {
    current = b.dataset.tab;
    selectedCampaign = null;
    load();
  }),
);
$("logout").addEventListener("click", async () => {
  try {
    await api("logout", {});
  } catch (_) {}
  token = "";
  clearTimeout(timer);
  $("login").hidden = false;
  $("identity").textContent = "Signed out";
  content.replaceChildren();
  $("drawer").hidden = true;
});
document.addEventListener("visibilitychange", () => {
  clearTimeout(timer);
  timer = setTimeout(load, document.hidden ? 30000 : 0);
});


let selectedProgram = "INTCALC";
function evidenceSources(sources) {
  const detail = el("details", undefined, "evidence-sources");
  detail.append(el("summary", "Evidence sources and SHA-256"));
  for (const source of sources || []) {
    const line = el("p"), a = el("a", source.path);
    a.href = "https://github.com/howardweale/lightyear-carddemo-modernization/blob/" + source.commit + "/" + source.path;
    a.target = "_blank"; a.rel = "noopener noreferrer";
    line.append(a, el("code", source.sha256, "hash")); detail.append(line);
  }
  return detail;
}
function evidenceCard(title, block) {
  const card = el("article", undefined, "card evidence-card"); card.append(el("h3", title));
  card.append(evidenceSources(block.sources)); return card;
}
function evidenceTable(headers, rows) {
  const table = el("table"), head = el("thead"), tr = el("tr"), body = el("tbody");
  for (const h of headers) tr.append(el("th", h)); head.append(tr); table.append(head, body);
  for (const values of rows) {const row = el("tr"); for (const value of values) row.append(el("td", value === null || value === undefined ? "Not reported" : String(value))); body.append(row);}
  return table;
}
async function programs() {
  const v = await api("program?id=" + encodeURIComponent(selectedProgram));
  content.replaceChildren(el("p", "FACTORY · PUBLIC DEVELOPMENT", "eyebrow"), el("h2", "Program evidence"));
  const nav = el("div", undefined, "program-picker");
  for (const name of ["INTCALC", "POSTTRAN"]) {const b=button(name,async()=>{selectedProgram=name;await programs();});b.setAttribute("aria-pressed",String(name===selectedProgram));nav.append(b);} content.append(nav);
  if (!v.available) {content.append(el("p", v.reason || "Programs are unavailable in this scope."));return;}
  content.append(el("h2",v.id),badge("Not releasable"),el("p",v.claim,"boundary"),el("p",`Experiment: ${v.observed_head} · Evidence import: ${v.evidence_commit}`,"hash"));
  const waiting=button(`Waiting on you · ${v.waiting_on_you.count}`,async()=>{current="queue";await queue();}); content.append(waiting);
  const grid=el("div",undefined,"program-grid");content.append(grid);
  const checklist=el("article",undefined,"card evidence-card");checklist.append(el("h3","Releasability checklist"));
  checklist.append(evidenceTable(["Criterion","Measured value","State"],v.checklist.map(r=>[r.criterion,r.value,r.state])));
  for(const row of v.checklist){const detail=el("details");detail.append(el("summary",row.criterion+": "+row.state),el("p",row.reason),evidenceSources(row.sources));checklist.append(detail);}grid.append(checklist);
  const scenarios=evidenceCard("Scenarios",v.scenarios), sc=v.scenarios.value;
  scenarios.append(evidenceTable(["Evidence","Business logic","I/O handling"],[["Public data",sc.public_data?.coverage_by_class?.["business-logic"]?.fraction,sc.public_data?.coverage_by_class?.["io-handling"]?.fraction],["Including declared faults",sc.with_declared_faults?.coverage_by_class?.["business-logic"]?.fraction,sc.with_declared_faults?.coverage_by_class?.["io-handling"]?.fraction]]));
  scenarios.append(el("p",`${sc.fault_expectations_met}/${sc.fault_count} declared fault expectations met`),el("p",sc.exception_state));
  const gaps=el("details");gaps.append(el("summary",`${sc.gaps.length} listed I/O gaps / historical exceptions`),json(sc.gaps));scenarios.append(gaps);grid.append(scenarios);
  const mutation=evidenceCard("Mutation evidence",v.mutation),m=v.mutation.value;
  mutation.append(el("p",`Raw kills: ${m.raw_kill_fraction}`,"metric"),el("p",`Failure ${m.raw_counts["killed-failure"] || 0} · Divergent ${m.raw_counts["killed-divergent"] || 0}`));
  mutation.append(evidenceTable(["Claim scope","After exclusions","Unresolved"],Object.entries(m.scoped_assessments).map(([k,r])=>[k,r.mutation.kill_rate,r.mutation.unresolved_survivors.length])));
  mutation.append(el("p",m.warning,"boundary"),el("p",`${m.compiler_refusals.length} compiler refusals · ${m.generator_avoided} invalid mutants avoided`));
  mutation.append(evidenceTable(["Equivalence disposition","Count"],[["Compiler-proven",m.classes.compiler_proven],["Class proof",m.classes.class_proof],["Individually argued",m.classes.individually_argued],["Refuted",m.classes.refuted],["Evidence gap (overlapping)",m.classes.evidence_gap]]));
  const survivors=el("details");survivors.append(el("summary","Survivors, refusals and evidence gaps"),json({survivors:m.survivors,compiler_refusals:m.compiler_refusals,evidence_gaps:m.evidence_gap_ids,scoped:m.scoped_assessments}));mutation.append(survivors);grid.append(mutation);
  const answer=evidenceCard("Answer key and limits",v.answer_key),a=v.answer_key.value;
  answer.append(el("p",`${a.oracle_class} · ${a.oracle_status}`),el("p",`z/OS confirmed: ${a.zos_confirmation ? "yes" : "no"}`),el("p",`Human review: ${a.review_state}`));
  if(a.second_opinion)answer.append(el("p",`Second opinion: ${a.second_opinion.status}`),el("p",`Phase 2 authorized: ${a.second_opinion.phase2_authorized ? "yes" : "no"}`));
  const limits=el("details");limits.append(el("summary","Twin limits register"),el("pre",a.limits));answer.append(limits);grid.append(answer);
  const legacy=evidenceCard("Keep or fix",v.keep_or_fix);
  for(const row of v.keep_or_fix.value){legacy.append(el("h4",row.id),el("p",row.observed_behavior),el("p",`Historical disposition: ${row.disposition}`),el("p",`Source lines: ${row.source_lines.join(", ")}`),el("code",row.source_sha256,"hash"));const deps=el("details");deps.append(el("summary","Signed overlays and dependent arguments"),json(row.signed_overlay),json(row.dependent_arguments || "Not reported in this register version"));legacy.append(deps);}grid.append(legacy);
  const decisions=el("details");decisions.append(el("summary","Signed decision overlays"),json(v.decision_overlays));content.append(decisions);
}
