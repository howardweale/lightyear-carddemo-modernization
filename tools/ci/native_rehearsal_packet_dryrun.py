"""CI-only simulated decisions from the operator review documents, not Mac execution."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

from tools.native_rehearsal_bind_review import render

PACKET = Path("docs/factory/native-p5-rehearsal")


def acceptable(field, value, expected):
    if field == "message_age_hours":
        return type(value) in (int, float) and 0 <= value <= 24
    if field == "available_kib":
        return type(value) is int and value >= 1048576
    if field == "uid":
        return type(value) is int and value > 0
    if field == "groups":
        return isinstance(value, list) and bool(value) and all(type(x) is int for x in value) and 80 not in value
    return type(value) is type(expected) and value == expected


def decide(observations, rules):
    stops = [r["id"] for r in rules if r["field"] not in observations or
             not acceptable(r["field"], observations[r["field"]], r["good"])]
    return dict(decision="STOP" if stops else "SIMULATED_CHECKS_MATCH",
                stops=stops, execution_authorized=False, native_proof=False)


def report(packet):
    contract = json.loads((packet / "DRY-RUN-RULES.json").read_text())
    rules = contract["rules"]
    documents = {name: (packet/name).read_text(encoding="utf8")
                 for name in ("COMMAND-SHEET.txt", "RETURN-CHECKLIST.txt")}
    if len({r["id"] for r in rules}) != len(rules):
        raise ValueError("duplicate-rule")
    for rule in rules:
        if rule["anchor"] not in documents[rule["document"]]:
            raise ValueError("document-anchor-missing:" + rule["id"])
    baseline = {r["field"]: r["good"] for r in rules}
    control = decide(baseline, rules)
    if control["stops"]:
        raise ValueError("simulated-control-failed")
    observations = []
    for rule in rules:
        changed = deepcopy(baseline)
        changed[rule["field"]] = rule["bad"]
        result = decide(changed, rules)
        row = dict(id=rule["id"], fixture_value=rule["bad"], **result)
        observations.append(row)
        if result["stops"] != [rule["id"]]:
            raise ValueError("negative-control-failed:" + rule["id"])
    # Placeholder draft must refuse binding before producing any output.
    template = json.loads((packet / "BINDING-VALUES.json").read_text())
    refused = False
    try:
        render(documents["COMMAND-SHEET.txt"], documents["RETURN-CHECKLIST.txt"], dict(
            public_values=template["public_values"], received_at=template["values_message_received_at"],
            not_before=template["values_not_before"], slot_start=template["rehearsal_start"]))
    except (ValueError, TypeError):
        refused = True
    if not refused:
        raise ValueError("placeholder-draft-not-refused")
    return dict(schema="no-key-review-dry-run/1", placeholder_binding="REFUSED",
                scope="Simulated review decisions; no command-sheet block executed",
                physical_checks="NOT TESTED", mac_commands="NOT EXECUTED",
                cleanup="UNKNOWN", execution_authorized=False, native_proof=False,
                expected_case_classifications={"S1":"PASS", "S2":"PASS", "S3":"PASS",
                    "S4":"FAIL", "S5":"FAIL", "S6":"FAIL", "S7":"CI ONLY"},
                document_sha256={n:hashlib.sha256((packet/n).read_bytes()).hexdigest()
                                 for n in documents}, control=control, rows=observations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("CI-only; do not run locally")
    result = report(PACKET)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    for row in result["rows"]:
        print(row["id"], row["decision"], ",".join(row["stops"]))
    print("Placeholder binding REFUSED; physical checks NOT TESTED; cleanup UNKNOWN")


if __name__ == "__main__":
    main()
