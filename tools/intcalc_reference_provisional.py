"""Provisional public GnuCOBOL comparison. Never qualification or freezing."""
import argparse
import copy
import os
from pathlib import Path
import re
import time
from tools import intcalc_reference_execution as ref

BASE_BINDING = "spec/reference-execution/2026-11-16-preferred-signs-r1/BINDING.json"
NEW_PROBES = ("zoned-signs-2", "decimal-data-items")


def inventory_projection(value):
    ref.require(value.get("schema") == "reference-inventory/1", "inventory-schema")
    keys = ("compiler", "runtime", "packages", "copyright_files", "libcob_inventory")
    ref.require(all(k in value for k in keys), "inventory-fields")
    projected = copy.deepcopy({k: value[k] for k in keys})
    ref.require(isinstance(projected["libcob_inventory"], dict) and
                projected["libcob_inventory"], "inventory-libraries")
    for row in projected["libcob_inventory"].values():
        ref.require(re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")) is not None,
                    "inventory-library-hash")
        text = row["dynamic_dependencies"]
        ref.require(isinstance(text, str) and "not found" not in text,
                    "inventory-unresolved-library")
        # Only process-local trailing ldd load addresses are excluded. Keep
        # names, paths, whitespace/order and every other field byte-for-byte.
        row["dynamic_dependencies"] = re.sub(r" \(0x[0-9a-fA-F]+\)(?=\n|$)", "", text)
    return projected


def inventory_digest(value):
    return ref.sha(ref.canonical(inventory_projection(value)))


def check_inputs(request_path):
    ref.require(os.environ.get("GITHUB_ACTIONS") == "true", "provisional-ci-only")
    request = ref.strict(ref.bounded(request_path))
    ref.require(request.get("schema") == "reference-provisional-request/1" and
                request.get("provisional") is True and
                request.get("qualified") is False and
                request.get("freeze_enabled") is False, "provisional-only")
    for key in ("inventory_review", "probe_review"):
        record = request.get(key)
        ref.require(isinstance(record, dict) and
                    re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")) is not None,
                    "unbound-" + key)
    raw = ref.joined(ref.ROOT, request["expected_inventory"])
    expected = ref.strict(raw)
    digest = inventory_digest(expected)
    review = ref.strict(ref.joined(ref.ROOT, request["inventory_review"]))
    ref.require(review.get("schema") == "reference-provisional-inventory-review/1" and
                review.get("reviewer") == "Claude" and
                review.get("accepted_for_provisional") is True and
                review.get("inventory_sha256") == ref.sha(raw) and
                review.get("package_library_sha256") == digest, "inventory-review")
    binding_raw = ref.joined(ref.ROOT, request["source_binding"])
    row = ref.strict(binding_raw)
    ref.require(request["source_binding"]["path"] == BASE_BINDING and
                row["flags"] == ref.FLAGS and row["platform"] == "linux/amd64" and
                row["compiler_package"] == "3.1.2-5.1ubuntu1" and
                row["case_ids"] == ref.IDS and row["case_author"] == "Claude" and
                row["freeze_enabled"] is False and row["hidden_generation_enabled"] is False,
                "provisional-profile")
    for record in row["sources"]:
        ref.joined(ref.ROOT, record)
    suite_raw = ref.joined(ref.ROOT, request["suite"])
    ref.require(ref.sha(suite_raw) == row["public_suite_sha256"], "public-suite-hash")
    suite = ref.strict(suite_raw)
    ref.require(suite.get("schema") == "intcalc-claude-public-suite/1" and
                suite.get("author") == "Claude" and suite.get("visibility") == "public" and
                [c["id"] for c in suite["cases"]] == ref.IDS, "public-suite")
    probes_raw = ref.joined(ref.ROOT, request["probes"])
    probe_rows = ref.strict(probes_raw)["probes"]
    original = ref.strict(ref.joined(ref.ROOT, row["probes"]))["probes"]
    ref.require(probe_rows[:7] == original and len(probe_rows) == 9 and
                tuple(p["id"] for p in probe_rows[7:]) == NEW_PROBES, "nine-probe-set")
    for probe in probe_rows:
        ref.joined(ref.ROOT, probe["source"])
    approval = ref.strict(ref.joined(ref.ROOT, request["probe_review"]))
    ref.require(approval.get("schema") == "reference-nine-probe-review/1" and
                approval.get("reviewer") == "Claude" and
                approval.get("accepted") is True and
                approval.get("probes_sha256") == ref.sha(probes_raw), "nine-probe-review")
    validate_reference_findings(row.get("reference_findings", []))
    ref.reference_domain_binding(row)
    return request, row, suite, probe_rows, digest


def validate_reference_findings(findings):
    ref.require(type(findings) is list and len(findings) <= 1, "reference-findings")
    for finding in findings:
        ref.require(type(finding) is dict and set(finding) ==
                    {"finding", "probe", "pair", "channel", "difference_sha256"},
                    "reference-finding-shape")
        ref.require(finding["finding"] == ref.SIGN_LIMIT and
                    finding["probe"] == "zoned-signs-2" and
                    finding["pair"] == "reference-ibm" and finding["channel"] == "stdout" and
                    type(finding["difference_sha256"]) is str and
                    re.fullmatch(r"[0-9a-f]{64}", finding["difference_sha256"]),
                    "reference-finding-scope")


def probe_result(p, code, out, err, findings):
    validate_reference_findings(findings)
    channels = {}
    for channel, actual, expected in (("exit", code, p["exit_code"]),
            ("stdout", out, bytes.fromhex(p["stdout_hex"])),
            ("stderr", err, bytes.fromhex(p["stderr_hex"]))):
        if actual == expected:
            channels[channel] = {"status": "MATCH"}
            continue
        if channel == "exit":
            diff = {"left": actual, "right": expected}
        else:
            diff = ref.first_difference(actual, expected, 1)
            # Bind ALL bytes on both sides, not just the first different byte.
            diff.update(left_sha256=ref.sha(actual), right_sha256=ref.sha(expected))
        digest = ref.sha(ref.canonical(diff))
        matches = [f for f in findings if f["probe"] == p["id"] and
                   f["channel"] == channel and f["difference_sha256"] == digest]
        channels[channel] = {"status": "PREREGISTERED_FINDING" if matches else "DIFFERENT",
                             "difference": diff, "difference_sha256": digest,
                             "findings": [f["finding"] for f in matches]}
    statuses = [c["status"] for c in channels.values()]
    return {"id": p["id"], "match": all(s == "MATCH" for s in statuses),
            "comparison_criterion_met": "DIFFERENT" not in statuses,
            "exit": code, "stdout_hex": out.hex(), "stderr_hex": err.hex(),
            "expected": {"exit": p["exit_code"], "stdout_hex": p["stdout_hex"],
                         "stderr_hex": p["stderr_hex"]}, "channels": channels}


def run_probes(work, deadline, specifications, findings=None):
    findings = [] if findings is None else findings
    validate_reference_findings(findings)
    # The separate nine-probe review is checked by check_inputs. The merged
    # qualified runner deliberately still requires its original seven probes.
    ref.require(len(specifications) == 9 and
                {p["id"] for p in specifications} == ref.PROBES | set(NEW_PROBES),
                "nine-probe-set")
    observations = []
    for p in specifications:
        ref.require(bool(p.get("derivation")), "probe-derivation")
        folder = work / ("probe-" + p["id"])
        folder.mkdir()
        ref.exclusive(folder / "probe.cob", ref.joined(ref.ROOT, p["source"]))
        ref.checked(["cobc", "-x", "-free", *ref.FLAGS, "probe.cob", "-o", "probe"], folder, deadline)
        code, out, err = ref.run([str(folder / "probe")], folder, deadline, p["environment"])
        ref.exclusive(folder / "observations" / "stdout", out)
        ref.exclusive(folder / "observations" / "stderr", err)
        observations.append(probe_result(p, code, out, err, findings))
    return observations


def make_report(request_hash, suite_hash, observed_hash, package_hash, observations, cases):
    cases = copy.deepcopy(cases)
    comparison = all(p.get("comparison_criterion_met", p["match"]) for p in observations) and all(c["freeze_criterion_met"] for c in cases)
    for case in cases:
        case["comparison_criterion_met"] = case.pop("freeze_criterion_met")
        case.update(provisional=True, qualified=False, freeze_criterion_met=False)
    return {"schema": "intcalc-reference-discrepancy/1", "provisional": True,
            "qualified": False, "freeze_performed": False, "freeze_criterion_met": False,
            "comparison_criterion_met": comparison,
            "qualification_pending_review": True, "request_sha256": request_hash,
            "binding_sha256": None, "image_digest_bound": False,
            "public_suite_sha256": suite_hash, "inventory_sha256": observed_hash,
            "package_library_sha256": package_hash, "probes": observations, "cases": cases,
            "reference_limits": [ref.SIGN_LIMIT],
            "all_probes_match": all(p["match"] for p in observations),
            "all_three_way_match": all(c["all_modelled_channels_match"] for c in cases),
            "reference": "GnuCOBOL execution of unmodified public COBOL source; never z/OS",
            "limit": ref.LIMIT + "; PROVISIONAL same-job build, no published image binding"}


def compare(request_path, destination):
    request, row, suite, probe_rows, expected_digest = check_inputs(request_path)
    ref.native()
    ref.require(not destination.exists() and not destination.is_symlink(), "fresh-destination")
    destination.mkdir(mode=0o700)
    observed = destination / "inventory.json"
    ref.inventory(observed)
    actual = inventory_digest(ref.strict(ref.bounded(observed)))
    ref.require(actual == expected_digest, "provisional-inventory-mismatch")
    # The observed inventory must match BEFORE compiling any probe or program.
    deadline = time.monotonic() + 1800
    compiled = destination / "compiled"
    compiled.mkdir()
    ref.compile_reference(compiled, deadline, row["compile_sources"])
    observations = run_probes(destination, deadline, probe_rows, row["reference_findings"])
    from lightyear_mainframe.records import load_copybook
    from lightyear_mainframe.zos_bindings import load_bindings, dataset_binding
    layouts = {dd: load_copybook(ref.ROOT / dataset_binding(load_bindings(), "INTCALC", "STEP15", dd)["copybook"])
               for dd in ref.DDS}
    suite_root = (ref.ROOT / request["suite"]["path"]).parent
    cases = []
    for case in suite["cases"]:
        folder = destination / case["id"]
        folder.mkdir()
        cases.append(ref.public_case(case, suite_root, folder, compiled, deadline, layouts))
    check_inputs(request_path)
    report = make_report(ref.sha(ref.bounded(request_path)), request["suite"]["sha256"],
                         ref.sha(ref.bounded(observed)), actual, observations, cases)
    ref.exclusive(destination / "report.json", ref.canonical(report) + b"\n")
    return 0 if report["comparison_criterion_met"] else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check-inputs", "compare"))
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "check-inputs":
            check_inputs(args.request)
            print("provisional-inputs-reviewed-not-qualified")
        else:
            ref.require(args.output is not None, "arguments")
            raise SystemExit(compare(args.request, args.output))
    except ref.Refused as exc:
        print(str(exc))
        raise SystemExit(2) from None
