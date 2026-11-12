"""Read-only A-F reporting from pinned public receipts, never run authorization.

This renderer checks hashes, identities, inventory and verdict joins. Hashes do
not authenticate a producer: the operator must obtain receipts from the trusted
controller/judge and independently run the open verifier before final reporting.
No signatures, admissions, executions, gate changes or evidence writes occur.
"""
from hashlib import sha256
import json
from pathlib import Path
import re

CONTROL_IDS = ["human-clean-control","configured-build-control","tower-unreachable","workspace-changed","kill-count-before-reserve","kill-count-after-reserve","kill-generation-before-reserve","kill-generation-after-reserve","kill-generation-after-observed","worker-network-positive-before","worker-network-denied","worker-network-positive-after","wall-and-window","budget-count-preflight","budget-count-overrun","budget-count-unknown","budget-generation-preflight","answer-fragment","duplicate-attempt"]
MAX_BYTES = 2 * 1024 * 1024
LIMITATION = ("Receipt-derived classification only; input hashes do not prove producer "
              "authenticity. This renderer grants no execution or qualification authority.")


class ReportError(ValueError):
    """Absent or inconsistent evidence cannot yield a favorable tier."""


def require(value, reason):
    if not value:
        raise ReportError(reason)


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def _constant(value):
    raise ReportError("nonfinite-json")


def decode(raw):
    try:
        require(len(raw) <= MAX_BYTES, "receipt-size")
        value = json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
        require(isinstance(value, dict), "receipt-object")
        return value
    except (ValueError, UnicodeError) as error:
        if isinstance(error, ReportError):
            raise
        raise ReportError("invalid-json") from None


def digest(value, length=64):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{" + str(length) + "}", value)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def load_rules(path, expected_sha256):
    require(digest(expected_sha256), "approved-rule-digest-required")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES and sha256(raw).hexdigest() == expected_sha256,
            "approved-tier-rules-changed")
    rules = decode(raw)
    require(rules.get("schema") in ("qualified-run-tier-rules/1", "qualified-run-tier-rules/2")
            and text(rules.get("version")), "rule-version")
    require(type(rules.get("case_count")) is int and 1 <= rules["case_count"] <= 10000,
            "rule-case-count")
    require(rules.get("bc_cutoff") == 10 and type(rules["bc_cutoff"]) is int, "rule-bc-cutoff")
    require(isinstance(rules.get("tiers"), dict) and set(rules["tiers"]) == set("ABCDEF")
            and all(isinstance(t, dict) and all(text(t.get(k)) for k in
                    ("name", "test", "what_it_proves")) for t in rules["tiers"].values()),
            "rule-tier-definitions")
    return rules


class Reader:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.sources = []

    def read(self, ref):
        require(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "receipt-reference")
        name = ref["path"]
        require(text(name) and "\\" not in name and ":" not in name, "receipt-path")
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts, "receipt-path")
        target = self.root / relative
        require(target.resolve().is_relative_to(self.root), "receipt-outside-bundle")
        require(not any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
                        for p in (target, *target.parents)), "receipt-link")
        require(digest(ref["sha256"]), "receipt-digest")
        with target.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES and sha256(raw).hexdigest() == ref["sha256"],
                "receipt-bytes-mismatch")
        result = decode(raw)
        self.sources.append(dict(ref))
        return result


def _binding(row, schema, run_id, exact_e=None, catalog_sha256=None):
    require(row.get("schema") == schema and row.get("run_id") == run_id, "receipt-run-binding")
    if exact_e is not None:
        require(row.get("exact_e") == exact_e, "receipt-source-binding")
    if catalog_sha256 is not None:
        require(row.get("catalog_sha256") == catalog_sha256, "receipt-catalog-binding")


def _inventory(rows, count):
    require(isinstance(rows, list) and len(rows) == count, "frozen-inventory-count")
    ids = []
    for row in rows:
        require(isinstance(row, dict) and set(row) == {"id", "definition"}, "definition-shape")
        require(text(row["id"]), "definition-id")
        definition = row["definition"]
        require(isinstance(definition, dict) and
                set(definition) == {"file", "commit", "sha256"} and
                text(definition["file"]) and digest(definition["commit"], 40) and
                digest(definition["sha256"]), "definition-binding")
        ids.append(row["id"])
    require(len(set(ids)) == count, "duplicate-inventory-id")
    return ids


def _controls(bundle, reader, run_id, exact_e):
    refs = bundle.get("controls")
    require(isinstance(refs, list) and len(refs) == len(CONTROL_IDS), "missing-control-drills")
    outcomes = {}
    for ref in refs:
        row = reader.read(ref)
        _binding(row, "qualified-run-control/1", run_id, exact_e)
        identity, status = row.get("control_id"), row.get("status")
        require(text(identity) and identity in CONTROL_IDS and identity not in outcomes,
                "control-inventory-drift")
        require(status in ("PASS", "STOPPED", "FAIL_OPEN", "NOT_RUN"), "control-verdict")
        require(status != "FAIL_OPEN", "control-failed-open")
        if status != "PASS":
            require(text(row.get("reason")), "missing-control-reason")
        outcomes[identity] = status
    require(set(outcomes) == set(CONTROL_IDS), "missing-control-drills")
    if "NOT_RUN" in outcomes.values():
        require("STOPPED" in outcomes.values(), "unexplained-unrun-control")
    return outcomes


def _classify(bundle, reader, rules, rule_sha256, approved_catalog_sha256):
    require(bundle.get("schema") == "qualified-run-report-bundle/1", "bundle-schema")
    require(bundle.get("rules_sha256") == rule_sha256, "bundle-tier-rules-binding")
    run = reader.read(bundle.get("run"))
    run_id = run.get("run_id")
    require(text(run_id), "run-identity")
    _binding(run, "qualified-run-status/1", run_id)
    state = run.get("state")
    require(state in ("not_started", "completed", "stopped"), "run-state")
    for key in ("answers_exposed", "catalog_changed_after_freeze", "evidence_missing",
                "verifier_disagrees", "limit_exceeded", "control_failed_open"):
        require(type(run.get(key)) is bool, "missing-control-evidence:" + key)
        require(not run[key], key)
    if state == "not_started":
        require(text(run.get("reason")), "missing-no-run-reason")
        require(not bundle.get("cases") and not bundle.get("verifier"), "no-run-contradiction")
        if bundle.get("controls"):
            exact_e = run.get("exact_e")
            require(digest(exact_e, 40), "missing-control-source")
            control_outcomes = _controls(bundle, reader, run_id, exact_e)
            if "STOPPED" in control_outcomes.values():
                return "D", None, run_id, exact_e, ["control-stopped-before-run:" + run["reason"]]
        return "E", None, run_id, None, ["not-started:" + run["reason"]]

    exact_e = run.get("exact_e")
    require(digest(exact_e, 40), "missing-executable-binding")
    catalog_ref = bundle.get("catalog")
    require(digest(approved_catalog_sha256), "approved-catalog-digest-required")
    require(isinstance(catalog_ref, dict) and catalog_ref.get("sha256") == approved_catalog_sha256,
            "unapproved-catalog-binding")
    catalog = reader.read(catalog_ref)
    catalog_sha = catalog_ref["sha256"]
    _binding(catalog, "qualified-run-frozen-catalog/1", run_id, exact_e)
    require(run.get("catalog_sha256") == catalog_sha, "run-catalog-drift")
    cases = _inventory(catalog.get("cases"), rules["case_count"])
    gate_rows = catalog.get("gates")
    require(isinstance(gate_rows, list) and 1 <= len(gate_rows) <= 256, "condition-inventory")
    gates = _inventory(gate_rows, len(gate_rows))
    reader.gate_count = len(gates)
    control_outcomes = _controls(bundle, reader, run_id, exact_e)
    require("STOPPED" not in control_outcomes.values() or state == "stopped",
            "control-stop-run-contradiction")
    limits = catalog.get("limit_ids")
    require(isinstance(limits, list) and limits and all(text(x) for x in limits) and
            len(set(limits)) == len(limits), "limit-inventory")
    observed_limits = run.get("limits")
    require(isinstance(observed_limits, dict) and set(observed_limits) == set(limits),
            "missing-limit-evidence")
    require(all(value is True for value in observed_limits.values()), "limit-not-held-or-unknown")

    refs = bundle.get("cases")
    require(isinstance(refs, list) and len(refs) == rules["case_count"], "missing-case-evidence")
    outcomes, failures, passed = {}, [], 0
    for ref in refs:
        row = reader.read(ref)
        _binding(row, "qualified-run-case/1", run_id, exact_e, catalog_sha)
        case_id = row.get("case_id")
        require(text(case_id) and case_id in cases and case_id not in outcomes, "case-inventory-drift")
        verdicts = row.get("gates")
        require(isinstance(verdicts, dict) and set(verdicts) == set(gates),
                "missing-or-changed-gate")
        require(all(v in ("PASS", "FAIL", "NOT_RUN") for v in verdicts.values()),
                "unknown-gate-verdict")
        if "NOT_RUN" in verdicts.values():
            require(state == "stopped" and text(row.get("reason")), "unexplained-unrun-gate")
        complete_pass = all(v == "PASS" for v in verdicts.values())
        if complete_pass:
            passed += 1
        else:
            require(text(row.get("reason")), "missing-failure-receipt-reason")
            failures.append(row)
        outcomes[case_id] = verdicts
    require(set(outcomes) == set(cases), "incomplete-case-inventory")

    # Compare every frozen case, condition and prerequisite with the independent verifier.
    pre_verifier_hashes = sorted(x["sha256"] for x in reader.sources)
    verifier = reader.read(bundle.get("verifier"))
    _binding(verifier, "qualified-run-open-verifier/1", run_id, exact_e, catalog_sha)
    require(verifier.get("case_gates") == outcomes and
            verifier.get("control_outcomes") == control_outcomes and
            verifier.get("passed_cases") == passed and
            type(verifier.get("passed_cases")) is int and
            verifier.get("limits") == observed_limits and
            verifier.get("input_receipt_sha256") == pre_verifier_hashes,
            "verifier-disagrees-or-incomplete")
    require(verifier.get("status") in ("PASS", "PARTIAL", "STOPPED", "FAIL"),
            "missing-verifier-verdict")

    if state == "stopped":
        require(run.get("stopped_on") in ("limit", "control") and text(run.get("reason")),
                "missing-clean-stop-reason")
        require(verifier["status"] == "STOPPED", "verifier-disagrees")
        return "D", passed, run_id, exact_e, ["clean-stop:" + run["reason"]]
    if passed == 0:
        require(text(run.get("reason")), "missing-zero-pass-reason")
        require(verifier["status"] == "FAIL", "verifier-disagrees")
        return "D", 0, run_id, exact_e, ["zero-passes:" + run["reason"]]
    if passed == rules["case_count"]:
        require(verifier["status"] == "PASS", "verifier-disagrees")
        published_hashes = sorted(x["sha256"] for x in reader.sources)
        publication = reader.read(bundle.get("publication"))
        _binding(publication, "qualified-run-publication/1", run_id, exact_e, catalog_sha)
        entries = publication.get("receipts")
        require(isinstance(entries, list) and len(entries) == len(published_hashes),
                "missing-publication-evidence")
        require(all(isinstance(e, dict) and digest(e.get("sha256")) and
                    text(e.get("url")) and e["url"].startswith("https://") and
                    e.get("readback_verified") is True for e in entries),
                "missing-publication-readback")
        require(sorted(e["sha256"] for e in entries) == published_hashes,
                "publication-receipt-drift")
        return "A", passed, run_id, exact_e, ["all-frozen-cases", "all-frozen-conditions", "all-control-drills", "published", "verifier-PASS"]
    require(verifier["status"] == "PARTIAL", "verifier-disagrees")
    if passed >= rules["bc_cutoff"]:
        require(all(r.get("origin") == "judge" and text(r.get("difference")) for r in failures),
                "missing-judge-difference")
        return "B", passed, run_id, exact_e, ["strong-partial-count", "all-frozen-conditions", "all-control-drills", "judge-differences"]
    return "C", passed, run_id, exact_e, ["early-partial-count", "all-frozen-conditions", "all-control-drills", "failures-recorded"]


def render_bundle(bundle_path, *, rules_path, rules_sha256, catalog_sha256=None):
    rules = load_rules(rules_path, rules_sha256)  # A changed rule version is an error, never scored.
    bundle_path = Path(bundle_path)
    reader = Reader(bundle_path.parent)
    tier, count, run_id, exact_e, reasons = "F", None, None, None, []
    try:
        with bundle_path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        bundle_sha = sha256(raw).hexdigest()
        bundle = decode(raw)
        tier, count, run_id, exact_e, reasons = _classify(bundle, reader, rules, rules_sha256, catalog_sha256)
    except (ReportError, OSError) as error:
        # Do not expose paths or arbitrary exception text from an OS error.
        reasons = [str(error) if isinstance(error, ReportError) else "missing-unreadable-evidence"]
        bundle_sha = locals().get("bundle_sha")
    definition = rules["tiers"][tier]
    return dict(schema="qualified-run-outcome-report/1", rules_version=rules["version"],
                rules_sha256=rules_sha256, bundle_sha256=bundle_sha, tier=tier,
                tier_name=definition["name"], test=definition["test"],
                conditional_meaning=definition["what_it_proves"], reasons=reasons,
                passed_cases=count, case_denominator=rules["case_count"],
                gate_denominator=getattr(reader, "gate_count", None),
                run_id=run_id, exact_e=exact_e, receipts=reader.sources,
                authority_granted=False, limitation=LIMITATION)


def write_report(bundle_path, output_path, *, rules_path, rules_sha256, catalog_sha256=None):
    report = render_bundle(bundle_path, rules_path=rules_path, rules_sha256=rules_sha256,
                           catalog_sha256=catalog_sha256)
    with Path(output_path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return report
