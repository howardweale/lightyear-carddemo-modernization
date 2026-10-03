"""Closed, value-free CardDemo evidence vocabulary. No arrival-file reader here."""

import hashlib
import re
from datetime import date
from pathlib import Path

from .decisions import canonical, digest
from .kinds import DecisionKind, KindRegistry, default_registry
from .requests import RequestInbox, SHA, confined, read_json

SCOPE = "carddemo-zos"
POLICY = "carddemo-zos-no-values/1"
WORKLOAD = "workload:carddemo-intcalc"
HOWARD = "howard-weale"
AGENT = "zos-intake"
PEOPLE = {
    HOWARD: ("Howard Weale", "human"),
    AGENT: ("Intake agent", "agent"),
    "release-sponsor": ("Release sponsor", "customer"),
}
KINDS = (
    "intake-acceptance",
    "normalization",
    "difference-disposition",
    "evidence-release",
)
MIRROR = "work/mainframe/review/carddemo-zos"
REQUEST_ID = re.compile(
    r"(?:intake-acceptance|normalization|difference-disposition|evidence-release)-[a-f0-9]{64}\Z"
)


def initialize_workspace(root):
    """Create a data workspace only; no credentials, grants or decisions."""
    config = dict(
        schema="tower-workspace/1",
        scope=SCOPE,
        title="CardDemo z/OS arrivals",
        disclosure_policy=POLICY,
        read_only_arrivals=True,
    )
    path = confined(root, "control-tower/workspace.json", internal=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(read_json(path) == config)
    else:
        with path.open("xb") as stream:
            stream.write(canonical(config) + b"\n")
    confined(root, f"work/control-tower/requests/{SCOPE}", internal=True).mkdir(
        parents=True, exist_ok=True
    )
    confined(root, MIRROR).mkdir(parents=True, exist_ok=True)
    return config


def require(ok):
    if not ok:
        raise ValueError("CardDemo no-values policy refused evidence")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def registry():
    base = default_registry()
    return KindRegistry(
        [
            DecisionKind(
                "normalization",
                ("approved", "rejected"),
                ("normalization-approver",),
                ("rule",),
                required_fields=("reason", "named_owner", "review_after"),
                consumer="carddemo-zos-intake",
                source="verified-agent-proposal",
            ),
            *[base.get(k) for k in KINDS if k != "normalization"],
        ]
    )


def hashes(values):
    require(
        isinstance(values, list)
        and bool(values)
        and all(isinstance(v, str) and SHA.fullmatch(v) for v in values)
    )


def rule(value):
    """Only the qualified timestamp operation, scoped to exact runs/field bindings."""
    from lightyear_mainframe.zos_bindings import load_bindings, dataset_binding, ROOT
    from lightyear_mainframe.records import load_copybook
    from lightyear_mainframe.zos_compare import TIMESTAMP

    require(
        isinstance(value, dict)
        and set(value)
        == {"schema", "workload", "dataset", "field", "pattern", "runs", "still_caught"}
    )
    require(value["schema"] == "zos-tower-rule/1" and value["workload"] == WORKLOAD)
    require(value["pattern"] == TIMESTAMP)
    hashes(value["runs"])
    require(len(value["runs"]) == 2 and len(set(value["runs"])) == 2)
    step, dd = value["dataset"].split("/")
    binding = dataset_binding(load_bindings(), "INTCALC", step, dd)
    require(value["field"] in binding["timestamp_fields"])
    caught = value["still_caught"]
    require(isinstance(caught, dict) and set(caught) == {"field", "detected"})
    require(
        caught["detected"] is True
        and caught["field"] not in binding["timestamp_fields"]
    )
    layout = load_copybook(ROOT / binding["copybook"])
    require(caught["field"] in {f.path for f in layout.fields if not f.filler})
    return value


def from_draft(draft):
    return rule(
        {
            "schema": "zos-tower-rule/1",
            **{
                k: draft[k]
                for k in (
                    "workload",
                    "dataset",
                    "field",
                    "pattern",
                    "runs",
                    "still_caught",
                )
            },
        }
    )


def evidence(value):
    """Reject unknown fields recursively; never redact a signed record in place."""
    require(isinstance(value, dict))
    schema = value.get("schema")
    if schema == "zos-tower-rule/1":
        return rule(value)
    if schema == "zos-intake-review/1":
        require(
            set(value)
            == {
                "schema",
                "arrival_sha256",
                "intake_sha256",
                "files",
                "runs",
                "findings",
                "status",
            }
        )
        hashes([value["arrival_sha256"], value["intake_sha256"]])
        require(
            all(
                type(value[k]) is int and value[k] >= 0
                for k in ("files", "runs", "findings")
            )
        )
        require(value["status"] in {"ready-for-review", "review-required"})
    elif schema == "zos-difference-review/1":
        require(
            set(value)
            == {
                "schema",
                "source_sha256",
                "target_sha256",
                "diagnostic_sha256",
                "added",
                "deleted",
                "changed",
            }
        )
        hashes(
            [value[k] for k in ("source_sha256", "target_sha256", "diagnostic_sha256")]
        )
        require(
            all(
                type(value[k]) is int and value[k] >= 0
                for k in ("added", "deleted", "changed")
            )
        )
    elif schema == "zos-evidence-release/1":
        require(set(value) == {"schema", "scope", "disclosure_policy", "members"})
        require(value["scope"] == SCOPE and value["disclosure_policy"] == POLICY)
        require(
            isinstance(value["members"], list) and 0 < len(value["members"]) <= 1000
        )
        for member in value["members"]:
            require(
                member.get("schema")
                in {"zos-intake-review/1", "zos-difference-review/1"}
            )
            evidence(member)
    else:
        require(False)
    return value


def write_request(root, kind, records):
    """Offline intake producer: only closed evidence crosses into the Tower root."""
    require(kind in KINDS and set(records) == set(registry().get(kind).hashes))
    bound, links = {}, {}
    for key, record in records.items():
        raw = canonical(evidence(record)) + b"\n"
        bound[key] = sha(raw)
        rel = f"{MIRROR}/{bound[key]}.json"
        target = confined(root, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            require(target.read_bytes() == raw)
        else:
            with target.open("xb") as f:
                f.write(raw)
        links[key] = rel
    item_id = kind + "-" + digest(bound)
    request = dict(
        schema="tower-request/1",
        scope=SCOPE,
        id=item_id,
        kind=kind,
        bound=bound,
        evidence=links,
        summary=kind + ": operator review; not independent.",
        proposed_by=AGENT,
        authored_by=[AGENT],
        workload=WORKLOAD,
    )
    path = confined(
        root, f"work/control-tower/requests/{SCOPE}/{item_id}.json", internal=True
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(request) + b"\n"
    if path.exists():
        require(path.read_bytes() == raw)
    else:
        with path.open("xb") as f:
            f.write(raw)
    return request


class Inbox(RequestInbox):
    def item(self, request_id):
        require(isinstance(request_id, str) and REQUEST_ID.fullmatch(request_id))
        item = super().item(request_id)
        kind = self.registry.get(item["kind"])
        require(set(item["bound"]) == {*kind.hashes, "request"})
        for key in kind.hashes:
            require(item["evidence"][key] == f"{MIRROR}/{item['bound'][key]}.json")
            record = evidence(read_json(confined(self.root, item["evidence"][key])))
            expected = {
                "intake-acceptance": "zos-intake-review/1",
                "normalization": "zos-tower-rule/1",
                "difference-disposition": "zos-difference-review/1",
                "evidence-release": "zos-evidence-release/1",
            }
            require(record["schema"] == expected[kind.name])
        # No caller-provided labels, names, paths, dates or summary text are reflected.
        return {
            k: item[k]
            for k in (
                "schema",
                "scope",
                "id",
                "kind",
                "bound",
                "evidence",
                "status",
                "kind_version",
                "item_sha256",
            )
        } | {
            "summary": kind.name + ": operator review; not independent.",
            "proposed_by": AGENT,
            "authored_by": [AGENT],
            "workload": WORKLOAD,
        }

    def queue(self):
        result = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                result.append(self.item(path.stem))
            except (ValueError, OSError, KeyError, TypeError):
                result.append(
                    dict(
                        id="invalid-" + sha(path.name.encode()),
                        scope=SCOPE,
                        status="invalid",
                        reason_code="request-evidence-invalid",
                        decidable=False,
                    )
                )
        return result


def agent_proposal(item, events):
    """Require authenticated agent provenance for this exact rule and request."""
    matches = [
        e
        for e in events
        if e["kind"] == "tower_proposal"
        and e["actor"]["id"] == AGENT
        and e["actor"]["kind"] == "agent"
        and e["payload"].get("proposal_type") == "rule-proposal"
        and e["payload"].get("bound") == item["bound"]
    ]
    require(bool(matches))
    p = matches[-1]
    require(sha(canonical(rule(p["payload"]["rule"])) + b"\n") == item["bound"]["rule"])
    return p["content_sha256"]
