"""Human-attended PUBLIC host qualification worker; no CI-variable impersonation.

Only the pinned 16 public cases and nine probes. Private streaming is H2b and
cannot reuse this persistent public-observation path. Existing CI tools unchanged.
"""
import argparse
import os
from pathlib import Path
import platform
import re
import sys
import time
from tools import intcalc_reference_execution as ref
from tools.intcalc_reference_execution import (ROOT, DDS, LIMIT, Refused, require,
    sha, canonical, bounded, joined, exclusive, checked, run, clock_env, bridge,
    comparison_policy, decode_output, compare_results, split_runtime_diagnostics)
from tools.intcalc_reference_provisional import (BASE_BINDING, NEW_PROBES,
    inventory_digest, validate_reference_findings, run_probes, make_report)


def public_container():
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64'
            and not os.environ.get('GITHUB_ACTIONS'), 'host-public-container')
    permit = ref.strict(ref.bounded(Path('/host-public-permit.json')))
    require(type(permit) is dict and permit.get('schema') == 'ha-public-container/1'
            and permit.get('public_only') is True
            and permit.get('suite_sha256') == '6da875e28f95409290f77363c135ef98af395fe3448c9bf3e3da28b4cad370b2',
            'host-public-container')


def check_inputs(request_path):
    public_container()
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


def native():
    public_container()
    version, _ = checked(["dpkg-query", "-W", "-f=${Version}", "gnucobol3"],
                         ROOT, time.monotonic() + 30)
    require(version.decode() == "3.1.2-5.1ubuntu1", "compiler-version")


def inventory(destination):
    native()
    deadline = time.monotonic() + 120
    compiler, _ = checked(["cobc", "-V"], ROOT, deadline)
    runtime, _ = checked(["cobcrun", "-V"], ROOT, deadline)
    packages, _ = checked(["dpkg-query", "-W",
                          "-f=${Package}\t${Version}\t${Architecture}\n"], ROOT, deadline)
    licences = {}
    for p in sorted(Path("/usr/share/doc").glob("*/copyright")):
        if p.is_file() and not p.is_symlink():
            licences[p.relative_to("/usr/share/doc").as_posix()] = sha(bounded(p))
    libraries = {}
    for p in sorted(Path("/usr/lib/x86_64-linux-gnu").glob("libcob.so*")):
        resolved = p.resolve()
        if resolved.name in libraries:
            continue
        dependencies, _ = checked(["ldd", str(resolved)], ROOT, deadline)
        libraries[resolved.name] = {"sha256": sha(bounded(resolved)),
                                   "dynamic_dependencies": dependencies.decode("utf-8")}
    exclusive(destination, canonical({"schema": "reference-inventory/1",
        "compiler": compiler.decode("utf-8"), "runtime": runtime.decode("utf-8"),
        "packages": packages.decode("utf-8"), "copyright_files": licences,
        "libcob_inventory": libraries,
        "isam_backend_review": "PENDING", "licence_review": "PENDING",
        "qualified": False, "limit": LIMIT}) + b"\n")


def public_case(case, suite_root, work, compiled, deadline, layouts):
    require(set(case["inputs"]) == set(DDS) - {"TRANSACT"}, "input-dds")
    images = {dd: joined(suite_root, row) for dd, row in case["inputs"].items()}
    require(all(dd in layouts and layouts[dd] is not None for dd in images),
            "reference-sign-layout")
    converted = {dd: bridge(raw, *DDS[dd], layout=layouts[dd],
                            order_observable=dd in ("TCATBALF", "ACCTFILE"))
                 for dd, raw in images.items()}
    compare_files = comparison_policy(case)
    env = clock_env(case["timestamp"], case["processing_date"])
    for dd, raw in converted.items():
        exclusive(work / (dd + ".flat"), raw)
        checked([str(compiled / dd), "load", str(work / (dd + ".flat")),
                 str(work / dd)], work, deadline)
        env["DD_" + dd] = str(work / dd)
    exclusive(work / "TRANSACT", b"")
    env["DD_TRANSACT"] = str(work / "TRANSACT")
    code, stdout, stderr = run([str(compiled / "program")], work, deadline, env)
    reference = {"exit": code, "stdout": stdout, "stderr": stderr}
    if compare_files:
        checked([str(compiled / "ACCTFILE"), "dump", str(work / "ACCTFILE.after"),
                 str(work / "ACCTFILE")], work, deadline)
        reference["ACCTFILE"] = decode_output(bounded(work / "ACCTFILE.after"), 300)
        reference["TRANSACT"] = decode_output(bounded(work / "TRANSACT"), 350)
    oracle_in = work / "python-input"
    oracle_in.mkdir()
    mapping = {"ACCTFILE": "acctdata.txt", "TCATBALF": "tcatbal.txt",
               "DISCGRP": "discgrp.txt", "XREFFILE": "cardxref.txt"}
    for dd, name in mapping.items():
        raw, width = converted[dd], DDS[dd][0]
        exclusive(oracle_in / name, b"".join(raw[i:i + width] + b"\n"
                  for i in range(0, len(raw), width)))
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "oracle",
               "--input", str(oracle_in), "--output", str(work / "python-output"),
               "--processing-date", case["processing_date"], "--timestamp", case["timestamp"]]
    pycode, pyout, pyerr = run(command, work, deadline,
                             {'PYTHONPATH': str(ROOT / 'src') + ':' + str(ROOT)})
    require(pycode in (0, 2), "python-worker-fault")
    python = dict(exit=pycode, stdout=pyout, stderr=pyerr)
    for dd, filename in (("ACCTFILE", "acctdata.txt"), ("TRANSACT", "transactions.txt")):
        if not compare_files:
            continue
        p = work / "python-output" / filename
        if p.is_file():
            raw, width = bounded(p), DDS[dd][0]
            lines = raw.split(b"\n")
            require(lines[-1] == b"" and all(len(x) == width for x in lines[:-1]), "python-framing")
            python[dd] = decode_output(b"".join(lines[:-1]), width)
        else:
            python[dd] = b""
    hand = {dd: joined(suite_root, row) for dd, row in case["hand_outputs"].items()}
    expected_hand = {"stdout", "stderr"} | ({"ACCTFILE", "TRANSACT"} if compare_files else set())
    require(set(hand) == expected_hand, "hand-output-set")
    hand["exit"] = case["hand_exit"]
    report = compare_results(case, reference, hand, python, layouts)
    # Keep both raw reference stderr and the exact bytes used in comparisons.
    reference["stderr.raw"] = reference["stderr"]
    reference["stderr"], _ = split_runtime_diagnostics(reference["stderr"])
    for label, values in (("reference", reference), ("python", python), ("hand", hand)):
        for dd, raw in values.items():
            if isinstance(raw, bytes):
                exclusive(work / "observations" / label / dd, raw)
    return report


def compare(request_path, destination):
    started = time.monotonic()
    request, row, suite, probe_rows, expected_digest = check_inputs(request_path)
    native()
    ref.require(not destination.exists() and not destination.is_symlink(), "fresh-destination")
    destination.mkdir(mode=0o700)
    observed = destination / "inventory.json"
    inventory(observed)
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
        cases.append(public_case(case, suite_root, folder, compiled, deadline, layouts))
    check_inputs(request_path)
    report = make_report(ref.sha(ref.bounded(request_path)), request["suite"]["sha256"],
                         ref.sha(ref.bounded(observed)), actual, observations, cases)
    peak = ref.bounded(Path('/sys/fs/cgroup/memory.peak')).decode().strip()
    ref.require(peak.isdigit() and 0 < int(peak) <= 2147483648, 'host-public-memory')
    report['host_resources'] = dict(cgroup_memory_peak_bytes=int(peak),
                                   elapsed_milliseconds=int((time.monotonic()-started)*1000))
    ref.exclusive(destination / "report.json", ref.canonical(report) + b"\n")
    return 0 if report["comparison_criterion_met"] else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('compare', 'oracle'))
    for key in ('request', 'output', 'input'):
        parser.add_argument('--'+key, type=Path)
    parser.add_argument('--processing-date')
    parser.add_argument('--timestamp')
    args = parser.parse_args(argv)
    public_container()
    if args.mode == 'compare':
        require(args.request is not None and args.output is not None, 'host-public-arguments')
        return compare(args.request, args.output)
    from carddemo_oracle.oracle import run_directory, OracleExecutionError
    from carddemo_oracle.records import RecordError
    require(args.input is not None and args.output is not None, 'host-public-arguments')
    try:
        run_directory(args.input, args.output, args.processing_date, args.timestamp)
    except (OracleExecutionError, RecordError):
        print('python-oracle-exception', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Refused, OSError, ValueError, KeyError, TypeError):
        print('host-public-worker-refused')
        raise SystemExit(2) from None
