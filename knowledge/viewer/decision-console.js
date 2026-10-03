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
  $("message").textContent = "";
  try {
    await { campaigns, queue, catalogue, workspace, history }[current]();
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
    badge(v.state || "observed"),
  );
  content.append(
    el(
      "p",
      "Frozen controller: decisions are recorded here, but this controller does not read them. Stop it outside the Tower if required.",
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
  content.append(
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
  const grid = el("div", undefined, "trial-grid");
  for (const t of v.trials) {
    const b = button(t.id, () => drawer(t.id).append(json(t)));
    b.className = "trial " + t.state;
    b.setAttribute("aria-label", t.id + " " + t.state);
    grid.append(b);
  }
  content.append(grid);
  for (const a of v.alerts || [])
    content.append(
      el(
        "div",
        a.code +
          " · " +
          (a.diagnostic_class || "") +
          " " +
          (a.trials || []).join(", "),
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
async function review(item) {
  clearTimeout(timer);
  const i = await api(
    item.decidable ? "review" : "item?id=" + encodeURIComponent(item.id),
    item.decidable ? { id: item.id } : undefined,
  );
  const d = drawer(item.summary || item.id);
  d.append(badge(item.kind), json(i.bound), json(i.evidence_view));
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
      item.validation?.passed === false
    )
      n.disabled = true;
    choice.append(n);
  }
  if (item.validation) d.append(json(item.validation));
  if (item.validation?.passed === false) choice.value = "rejected";
  form.append(el("label", "Decision"), choice);
  const fields = {};
  for (const name of item.required_fields) {
    const label = el("label", name.replaceAll("_", " ")),
      input = name === "reason" ? el("textarea") : el("input");
    input.required = true;
    if (name === "review_after") input.type = "date";
    label.append(input);
    form.append(label);
    fields[name] = input;
  }
  let slot;
  if (item.kind === "evidence-release") {
    d.append(
      el(
        "p",
        "The frozen export will include both release decisions, including your identity and reason. Review the complete bound bundle before approving.",
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
        request_id: crypto.randomUUID(),
        previous_decision_sha256: i.latest_decision?.content_sha256 || null,
      };
      for (const [k, n] of Object.entries(fields)) p[k] = n.value;
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
