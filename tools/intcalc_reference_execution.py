"""Public-only GnuCOBOL qualification; no seed, freeze or gate admission."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SIGN_LIMIT = "REFERENCE_LIMIT_PREFERRED_SIGNS"
SIGN_APPROVAL_PATH = "spec/reference-execution/2026-11-16-preferred-signs-r1/HOWARD-DECISION-20261116.md"
SIGN_APPROVAL_SHA256 = "6f12d921e95d875acee50ccf27f08356a79aa87e05cf8374e962218dbf2c13a2"
SIGN_SCOPE = ("signed zoned inputs require preferred C/D signs; zone-F signed inputs "
              "are outside the reference proven domain and need mainframe evidence")
LIMIT = "open-source reference, not mainframe-proven; " + SIGN_LIMIT + ": " + SIGN_SCOPE
MAX_BYTES = 8 * 1024 * 1024
DDS = {"ACCTFILE": (300, 11), "TCATBALF": (50, 17),
       "DISCGRP": (50, 16), "XREFFILE": (50, 16), "TRANSACT": (350, 0)}
FLAGS = ["-std=ibm", "-fsign=EBCDIC", "-fbinary-size=2-4-8",
         "-fbinary-byteorder=big-endian", "-fbinary-truncate", "-O2",
         "-Q", "-Wl,--build-id=none"]
IDS = [f"PC-{n:02}" for n in range(1, 17)]
PROBES = {"decimal", "size-error", "binary-truncation", "signs",
          "numeric-class", "clock", "indexed-order"}


class Refused(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Refused(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def strict(raw):
    def pairs(items):
        row = {}
        for key, value in items:
            require(key not in row, "duplicate-key")
            row[key] = value
        return row
    def invalid(_):
        raise Refused("noninteger-json")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_float=invalid, parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Refused("invalid-json") from exc


def bounded(path, cap=MAX_BYTES):
    require(not path.is_symlink() and path.is_file(), "regular-file")
    require(path.stat().st_size <= cap, "file-size")
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    require(len(raw) <= cap, "file-size")
    return raw


def joined(root, record):
    require(type(record) is dict and set(record) == {"path", "sha256"},
            "file-binding")
    name = record["path"]
    require(type(name) is str and "\\" not in name and ":" not in name,
            "relative-path")
    p = Path(name)
    require(not p.is_absolute() and p.parts and
            all(x not in ("", ".", "..") for x in name.split("/")), "relative-path")
    current = root
    for part in p.parts:
        current = current / part
        require(not current.is_symlink(), "linked-path")
    require(current.resolve().is_relative_to(root.resolve()), "path-escape")
    raw = bounded(current)
    require(sha(raw) == record["sha256"], "file-hash")
    return raw


def exclusive(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def binding(raw):
    row = strict(raw)
    require(row.get("schema") == "intcalc-reference-binding/1", "binding-schema")
    for key in ("image_manifest", "image_config", "isam_inventory_sha256",
                "licence_review_sha256", "public_suite_sha256",
                "profile_probe_review_sha256"):
        require(type(row.get(key)) is str and
                re.fullmatch(r"[0-9a-f]{64}", row[key]), "unbound-" + key)
    require(row.get("platform") == "linux/amd64" and
            row.get("compiler_package") == "3.1.2-5.1ubuntu1", "reference-platform")
    require(row.get("flags") == FLAGS, "compile-flags")
    require(row.get("case_ids") == IDS and row.get("case_author") == "Claude",
            "public-case-inventory")
    require(row.get("hidden_generation_enabled") is False and
            row.get("freeze_enabled") is False, "no-freeze-authority")
    reference_domain_binding(row)
    return row


def clock_env(timestamp, processing_date):
    require(type(timestamp) is str and
            re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d{6}", timestamp),
            "timestamp-shape")
    require(type(processing_date) is str and
            re.fullmatch(r"\d{10}", processing_date), "processing-date")
    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%d-%H.%M.%S.%f")
        datetime.strptime(processing_date, "%Y%m%d%H")
    except ValueError as exc:
        raise Refused("invalid-date") from exc
    return {"COB_CURRENT_DATE": dt.strftime("%Y/%m/%d %H:%M:%S.") +
            f"{dt.microsecond:06}000", "TWIN_PROCESSING_DATE": processing_date}


def reference_domain_binding(row):
    require(row.get("reference_limits") == [SIGN_LIMIT], "reference-sign-limit-binding")
    approval = row.get("reference_limit_approval_sha256")
    require(type(approval) is str and re.fullmatch(r"[0-9a-f]{64}", approval),
            "reference-limit-decision-pending")
    require(approval == SIGN_APPROVAL_SHA256, "reference-limit-approval-mismatch")
    joined(ROOT, {"path": SIGN_APPROVAL_PATH, "sha256": approval})


def preferred_signs(raw, layout, width):
    # The caller supplies the pinned input copybook layout, never an inferred
    # record value or a suite-authored list of fields to exempt.
    require(layout.record_length == width and not layout.variable and not layout.overlays,
            "reference-sign-layout")
    require(len(raw) % width == 0, "partial-record")
    for field in layout.fields:
        if not field.signed:
            continue
        require(field.usage == "DISPLAY", "reference-sign-layout")
        require(not field.separate and field.sign in ("LEADING", "TRAILING") and
                field.length > 0 and field.offset >= 0 and
                field.offset + field.length <= width, "reference-sign-layout")
        sign_offset = 0 if field.sign == "LEADING" else field.length - 1
        for start in range(0, len(raw), width):
            value = raw[start + field.offset:start + field.offset + field.length]
            require(all(b & 15 <= 9 for b in value), "reference-zoned-digit")
            require(value[sign_offset] >> 4 in (12, 13),
                    "reference-signed-zoned-nonpreferred")
            require(all(b >> 4 == 15 for i, b in enumerate(value) if i != sign_offset),
                    "reference-zoned-digit-zone")


def bridge(raw, width, key, *, order_observable=False, layout=None):
    require(len(raw) % width == 0, "partial-record")
    if layout is not None:
        preferred_signs(raw, layout, width)
    try:
        converted = raw.decode("cp037").encode("ascii")
    except UnicodeError as exc:
        raise Refused("representation-domain") from exc
    require(all(32 <= c <= 126 for c in converted), "representation-domain")
    require(converted.decode("ascii").encode("cp037") == raw, "encoding-roundtrip")
    if key:
        keys = [raw[i:i + key] for i in range(0, len(raw), width)]
        require(len(keys) == len(set(keys)), "duplicate-primary-key")
        if order_observable:
            # Compare whole actual keys, not the union of their characters.
            ebcdic_order = sorted(keys)
            ascii_order = sorted(keys, key=lambda k: k.decode("cp037").encode("ascii"))
            require(ebcdic_order == ascii_order, "cp037-key-order")
    return converted


def decode_output(raw, width):
    require(len(raw) % width == 0, "output-framing")
    require(all(32 <= c <= 126 for c in raw), "output-domain")
    try:
        result = raw.decode("ascii").encode("cp037")
    except UnicodeError as exc:
        raise Refused("output-domain") from exc
    require(result.decode("cp037").encode("ascii") == raw, "output-roundtrip")
    return result


def first_difference(left, right, width, fields=()):
    stop = min(len(left), len(right))
    offset = next((i for i in range(stop) if left[i] != right[i]), None)
    if offset is None and len(left) == len(right):
        return None
    offset = stop if offset is None else offset
    within = offset % width
    names = [f.path for f in fields if f.offset <= within < f.offset + f.length]
    return {"byte": offset, "record": offset // width + 1,
            "offset": within, "field": names[0] if names else "FILLER_OR_BOUNDARY",
            "left": left[offset:offset + 1].hex(), "right": right[offset:offset + 1].hex(),
            "left_bytes": len(left), "right_bytes": len(right)}


def clean_env(extra=None):
    row = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src")}
    # CI-only origin is propagated to the unchanged Python oracle worker, not
    # fabricated for an attended freeze or accepted as gate qualification.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        row["GITHUB_ACTIONS"] = "true"
    row.update(extra or {})
    return row


def run(command, cwd, deadline, extra=None):
    require(os.name == "posix", "posix-required")
    remaining = deadline - time.monotonic()
    require(remaining > 0, "original-deadline")
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(command, cwd=cwd, env=clean_env(extra),
                                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                start_new_session=True)
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise Refused("original-deadline") from exc
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        require(out.tell() <= MAX_BYTES and err.tell() <= MAX_BYTES, "capture-size")
        out.seek(0)
        err.seek(0)
        return proc.returncode, out.read(), err.read()


def checked(command, cwd, deadline, extra=None):
    code, out, err = run(command, cwd, deadline, extra)
    require(code == 0, "reference-command-exit")
    return out, err


def native():
    require(os.environ.get("GITHUB_ACTIONS") == "true" and
            platform.system() == "Linux" and platform.machine() == "x86_64",
            "native-amd64-ci-only")
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


def compile_reference(work, deadline, sources):
    from tools import intcalc_reference_adapters as twin
    for record in sources:
        exclusive(work / Path(record["path"]).name, joined(ROOT, record))
    exclusive(work / "main.cob", twin.wrapper("INTCALC").encode("ascii"))
    exclusive(work / "abend.cob", twin.ABEND.encode("ascii"))
    checked(["cobc", "-c", "-fixed", *FLAGS, "-I", ".", "CBACT04C.cbl",
             "-o", "program.o"], work, deadline)
    checked(["cobc", "-x", "-free", *FLAGS, "-fstatic-call", "main.cob",
             "abend.cob", "program.o", "-o", "program"], work, deadline)
    for dd, (_, key) in DDS.items():
        if key:
            exclusive(work / (dd + ".cob"), twin.indexed_adapter("INTCALC", dd).encode("ascii"))
            checked(["cobc", "-x", "-free", *FLAGS, dd + ".cob", "-o", dd], work, deadline)


def probes(work, deadline, specifications):
    require(set(p["id"] for p in specifications) == PROBES
            and len(specifications) == len(PROBES), "probe-inventory")
    observations = []
    for p in specifications:
        require(p.get("derivation") and p.get("independent_review_sha256"), "probe-review-pending")
        folder = work / ("probe-" + p["id"])
        folder.mkdir()
        exclusive(folder / "probe.cob", joined(ROOT, p["source"]))
        checked(["cobc", "-x", "-free", *FLAGS, "probe.cob", "-o", "probe"], folder, deadline)
        code, out, err = run([str(folder / "probe")], folder, deadline, p["environment"])
        equal = (code == p["exit_code"] and out.hex() == p["stdout_hex"] and err.hex() == p["stderr_hex"])
        observations.append({"id": p["id"], "match": equal, "exit": code,
                             "stdout_hex": out.hex(), "stderr_hex": err.hex()})
    return observations


def comparison_policy(case):
    value = case.get("compare_output_files", True)
    require(type(value) is bool, "compare-output-files")
    require(value == (case["id"] not in ("PC-10", "PC-11", "PC-12")),
            "public-case-comparison-policy")
    return value


IMPLICIT_CLOSE_FILES = {
    "TRANSACT-FILE": "TRANSACT", "ACCOUNT-FILE": "ACCTFILE",
    "DISCGRP-FILE": "DISCGRP", "XREF-FILE": "XREFFILE",
    "TCATBAL-FILE": "TCATBALF",
}


def split_runtime_diagnostics(stderr):
    """Separate five exact libcob lines; preserve every other byte for comparison."""
    allowed = {
        ("libcob: warning: implicit CLOSE of " + name + " ('" + dd + "')\n").encode("ascii"):
        (name, dd) for name, dd in IMPLICIT_CLOSE_FILES.items()
    }
    compared, diagnostics = [], []
    # Split only LF, retaining termination. CRLF, partial and extended lines
    # deliberately do not match; no decoding or blanket warning suppression.
    parts = stderr.split(b"\n")
    for index, part in enumerate(parts):
        line = part + (b"\n" if index < len(parts) - 1 else b"")
        if line in allowed:
            name, dd = allowed[line]
            diagnostics.append({"file": name, "dd": dd, "line_hex": line.hex()})
        else:
            compared.append(line)
    return b"".join(compared), diagnostics


def compare_results(case, reference, hand, python, layouts):
    reference = dict(reference)
    reference["stderr"], runtime_diagnostics = split_runtime_diagnostics(reference["stderr"])
    compare_files = comparison_policy(case)
    require(type(hand["exit"]) is int and hand["exit"] == (0 if compare_files else 12),
            "hand-exit-convention")
    require(hand["stderr"] == b"", "hand-stderr-convention")
    require(all(c < 128 for c in hand["stdout"]) and b"\r" not in hand["stdout"],
            "hand-stdout-convention")
    findings = case.get("python_findings", [])
    require(type(findings) is list, "python-findings")
    scopes = {"O1": {"TRANSACT"}, "O2": {"ACCTFILE", "TRANSACT", "success_class"},
              "O3": {"ACCTFILE", "TRANSACT", "success_class"},
              "O4": {"ACCTFILE", "TRANSACT", "success_class"}}
    for finding in findings:
        require(type(finding) is dict and
                set(finding) == {"finding", "pair", "channel", "difference_sha256"},
                "python-finding-shape")
        require(finding["finding"] in scopes and
                finding["pair"] in ("reference-python", "hand-python") and
                finding["channel"] in scopes[finding["finding"]] and
                type(finding["difference_sha256"]) is str and
                re.fullmatch(r"[0-9a-f]{64}", finding["difference_sha256"]),
                "python-finding-scope")
    comparisons = []
    for label, a, b in (("reference-hand", reference, hand),
                        ("reference-python", reference, python), ("hand-python", hand, python)):
        channels = {}
        is_python = label.endswith("-python")
        for channel in ("ACCTFILE", "TRANSACT", "stdout", "stderr", "exit", "success_class"):
            if channel in DDS and not compare_files:
                channels[channel] = {"status": "NOT_COMPARED", "reason": "abend-persistence-unspecified"}
                continue
            if (is_python and channel in ("stdout", "stderr", "exit")) or (not is_python and channel == "success_class"):
                channels[channel] = {"status": "NOT_MODELLED" if is_python else "NOT_COMPARED"}
                continue
            if channel == "success_class":
                left, right = a["exit"] == 0, b["exit"] == 0
                diff = None if left == right else {"left_success": left, "right_success": right}
            elif channel == "exit":
                diff = None if a[channel] == b[channel] else {"left": a[channel], "right": b[channel]}
            else:
                diff = first_difference(a[channel], b[channel], DDS[channel][0] if channel in DDS else 1,
                                        layouts[channel].fields if channel in layouts else ())
            if diff is None:
                channels[channel] = {"status": "MATCH"}
                continue
            # A named finding is not a blanket waiver. Its exact public discrepancy
            # must have been reviewed and hash-bound in Claude's suite beforehand.
            digest = sha(canonical(diff))
            matches = [f for f in findings if f["pair"] == label and
                       f["channel"] == channel and f["difference_sha256"] == digest]
            channels[channel] = {"status": "PREREGISTERED_FINDING" if matches else "DIFFERENT",
                                 "difference": diff, "difference_sha256": digest,
                                 "findings": sorted({f["finding"] for f in matches})}
        comparisons.append({"pair": label, "channels": channels})
    statuses = [c["status"] for p in comparisons for c in p["channels"].values()]
    return {"id": case["id"], "compare_output_files": compare_files,
            "comparisons": comparisons, "runtime_diagnostics": runtime_diagnostics,
            "all_modelled_channels_match": not any(s in ("DIFFERENT", "PREREGISTERED_FINDING") for s in statuses),
            "freeze_criterion_met": "DIFFERENT" not in statuses,
            "reference": "GnuCOBOL execution of unmodified public COBOL source; never z/OS",
            "qualified": False, "freeze_performed": False, "limit": LIMIT}


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
    pycode, pyout, pyerr = run(command, work, deadline)
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


def qualify(binding_path, suite_path, destination):
    row = binding(bounded(binding_path))
    native()
    require(not destination.exists(), "fresh-destination")
    suite_raw = bounded(suite_path)
    require(sha(suite_raw) == row["public_suite_sha256"], "public-suite-hash")
    suite = strict(suite_raw)
    require(suite["schema"] == "intcalc-claude-public-suite/1" and
            suite["author"] == "Claude" and suite["visibility"] == "public" and
            [c["id"] for c in suite["cases"]] == IDS, "public-suite")
    for record in row["sources"]:
        joined(ROOT, record)
    probe_raw = joined(ROOT, row["probes"])
    require(sha(joined(ROOT, row["licence_review"])) == row["licence_review_sha256"], "licence-review-hash")
    require(sha(joined(ROOT, row["probe_review"])) == row["profile_probe_review_sha256"], "probe-review-hash")
    require(sha(joined(ROOT, row["isam_inventory"])) == row["isam_inventory_sha256"], "isam-inventory-hash")
    destination.mkdir()
    deadline = time.monotonic() + 1800
    compiled = destination / "compiled"
    compiled.mkdir()
    compile_reference(compiled, deadline, row["compile_sources"])
    observation = probes(destination, deadline, strict(probe_raw)["probes"])
    from lightyear_mainframe.records import load_copybook
    from lightyear_mainframe.zos_bindings import load_bindings, dataset_binding
    layouts = {dd: load_copybook(ROOT / dataset_binding(load_bindings(), "INTCALC", "STEP15", dd)["copybook"])
               for dd in DDS}
    cases = []
    for case in suite["cases"]:
        folder = destination / case["id"]
        folder.mkdir()
        cases.append(public_case(case, suite_path.parent, folder, compiled, deadline, layouts))
    for record in row["sources"]:
        joined(ROOT, record)
    equal = all(p["match"] for p in observation) and all(c["freeze_criterion_met"] for c in cases)
    report = {"schema": "intcalc-reference-discrepancy/1", "binding_sha256": sha(bounded(binding_path)),
              "public_suite_sha256": sha(suite_raw), "probes": observation, "cases": cases,
              "all_three_way_match": all(c["all_modelled_channels_match"] for c in cases),
              "freeze_criterion_met": equal,
              "reference": "GnuCOBOL execution of unmodified public COBOL source; never z/OS",
              "qualification_pending_review": True,
              "qualified": False, "freeze_performed": False, "limit": LIMIT}
    exclusive(destination / "report.json", canonical(report) + b"\n")
    return equal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check-binding", "inventory", "public", "oracle"))
    for name in ("binding", "suite", "output", "input"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--processing-date")
    parser.add_argument("--timestamp")
    args = parser.parse_args(argv)
    if args.mode == "check-binding":
        binding(bounded(args.binding))
        print("reference-bindings-present-not-qualified")
    elif args.mode == "inventory":
        inventory(args.output)
        print("reference-inventory-review-required")
    elif args.mode == "public":
        ok = qualify(args.binding, args.suite, args.output)
        print("reference-criterion-met-review-required" if ok else "reference-discrepancy")
        return 0 if ok else 2
    else:
        require(os.environ.get("GITHUB_ACTIONS") == "true", "ci-only-oracle")
        from carddemo_oracle.oracle import run_directory, OracleExecutionError
        from carddemo_oracle.records import RecordError
        try:
            run_directory(args.input, args.output, args.processing_date, args.timestamp)
        except (OracleExecutionError, RecordError):
            print("python-oracle-exception", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Refused as exc:
        print(str(exc))
        raise SystemExit(2) from None
