"""Public CardDemo GnuCOBOL engineering twin; never a z/OS evidence producer."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess

from .records import load_copybook, to_ascii_fixed
from .zos_bindings import ROOT, load_bindings, dataset_binding

SOURCE_COMMIT = "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
SOURCE_TREE = "a1253e31c839f78d1f185b01771ba956da63b005"
PACKAGE_VERSION = "3.1.2-5.1ubuntu1"
FLAGS = ["-std=ibm", "-fsign=EBCDIC", "-O2", "-Q", "-Wl,--build-id=none"]
PROGRAMS = {"INTCALC": "CBACT04C", "POSTTRAN": "CBTRN02C"}
# Fixed layouts and physical keys copied from the pinned SELECT/FD declarations.
FILES = {
    "INTCALC": {"ACCTFILE": (300, 11), "TCATBALF": (50, 17),
                "DISCGRP": (50, 16), "XREFFILE": (50, 16), "TRANSACT": (350, 0)},
    "POSTTRAN": {"ACCTFILE": (300, 11), "TCATBALF": (50, 17),
                 "XREFFILE": (50, 16), "TRANFILE": (350, 16),
                 "DALYTRAN": (350, 0), "DALYREJS": (430, 0)},
}
PUBLIC_SCENARIOS = {
    "intcalc-public-1": ("INTCALC", "arrival-rehearsal/INTCALC-run1-2026-10-05"),
    "intcalc-public-2": ("INTCALC", "arrival-rehearsal/INTCALC-run2-2026-10-05"),
    "intcalc-discriminating": ("INTCALC", "intcalc-discriminating-v1"),
    "intcalc-missing-disclosure": ("INTCALC", "intcalc-discriminating-v1"),
    "posttran-missing-card": ("POSTTRAN", "arrival-rehearsal/POSTTRAN-run1-2026-10-05"),
    "posttran-missing-account": ("POSTTRAN", "arrival-rehearsal/POSTTRAN-run1-2026-10-05"),
    "posttran-expired-account": ("POSTTRAN", "arrival-rehearsal/POSTTRAN-run1-2026-10-05"),
    "posttran-public": ("POSTTRAN", "arrival-rehearsal/POSTTRAN-run1-2026-10-05"),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def receipt(path, **data):
    data = dict(schema="factory-legacy-twin/1", run_class="engineering",
                oracle_class="executable-twin", qualification_credit=False,
                measurement_credit=False, zos_confirmation=False, releasable=False,
                oracle_status="provisional", twin_limits_path="docs/factory/twin-limits.md",
                twin_limits_sha256=sha((ROOT / "docs/factory/twin-limits.md").read_bytes()), **data)
    data["content_sha256"] = sha(json.dumps(data, sort_keys=True, separators=(",", ":")).encode())
    write_json(path, data)
    return data


def new_output(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=False)
    write_json(path / "engineering.json", {"run_class": "engineering",
               "qualification_credit": False, "measurement_credit": False})
    return path


def clean_env():
    # No inherited COB_* / DD_* / compiler flags may change this run.
    return {"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "TZ": "UTC", "SOURCE_DATE_EPOCH": "1658102400"}


def compiler_clock():
    version = subprocess.check_output(["dpkg-query", "-W", "-f=${Version}", "libfaketime"], env=clean_env()).decode()
    if version != "0.9.10-2.1":
        raise ValueError("unpinned compiler clock adapter")
    paths = subprocess.check_output(["dpkg-query", "-L", "libfaketime"], env=clean_env()).decode().splitlines()
    libraries = [Path(p) for p in paths if p.endswith("/libfaketime.so.1")]
    if len(libraries) != 1:
        raise ValueError("missing or ambiguous compiler clock adapter")
    return {"LD_PRELOAD": str(libraries[0]), "FAKETIME": "2022-07-18 00:00:00",
            "FAKETIME_DONT_FAKE_MONOTONIC": "1", "NO_FAKE_STAT": "1"}


def execute(command, cwd, log, *, extra_env=None, allowed=(0,), timeout=120):
    env = clean_env()
    if str(command[0]) == "cobc":
        env.update(compiler_clock())
    env.update(extra_env or {})
    try:
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        log.with_suffix(".stdout").write_bytes(e.stdout or b"")
        log.with_suffix(".stderr").write_bytes(e.stderr or b"")
        write_json(log.with_suffix(".json"), {"command": list(map(str, command)), "timeout": timeout})
        raise
    log.with_suffix(".stdout").write_bytes(result.stdout)
    log.with_suffix(".stderr").write_bytes(result.stderr)
    write_json(log.with_suffix(".json"), {"command": list(map(str, command)), "returncode": result.returncode})
    if result.returncode not in allowed:
        raise RuntimeError(f"command refused with rc={result.returncode}; see {log}")
    return result


def linux_platform():
    if platform.system() != "Linux":
        raise ValueError("Build/run requires Ubuntu 24.04 Linux; Windows execution is refused")
    osinfo = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    if osinfo.get("ID", "").strip('"') != "ubuntu" or osinfo.get("VERSION_ID", "").strip('"') != "24.04":
        raise ValueError("Ubuntu 24.04 is required")
    version = subprocess.check_output(["dpkg-query", "-W", "-f=${Version}", "gnucobol3"], env=clean_env()).decode()
    if version != PACKAGE_VERSION:
        raise ValueError(f"unpinned GnuCOBOL package: {version}")
    return {"os": osinfo, "machine": platform.machine(), "package": version,
            "compiler": subprocess.check_output(["cobc", "-V"], env=clean_env()).decode(),
            "runtime": subprocess.check_output(["cobcrun", "-V"], env=clean_env()).decode()}


def indexed_adapter(job, dd):
    length, key = FILES[job][dd]
    if not key:
        raise ValueError("sequential files do not need indexed adaptation")
    alternate = job == "INTCALC" and dd == "XREFFILE"
    tail = ("05 filler pic x(9).\n05 alt-key pic x(11).\n05 filler pic x(14)." if alternate
            else f"05 filler pic x({length-key}).")
    alt_clause = "alternate record key is alt-key" if alternate else ""
    return f"""identification division.
program-id. adapter.
environment division.
input-output section.
file-control.
select flat-file assign to dynamic flat-path
 organization sequential file status flat-status.
select index-file assign to dynamic index-path
 organization indexed access dynamic record key primary-key
 {alt_clause} file status index-status.
data division.
file section.
fd flat-file.
01 flat-record pic x({length}).
fd index-file.
01 index-record.
05 primary-key pic x({key}).
{tail}
working-storage section.
01 flat-path pic x(1024).
01 index-path pic x(1024).
01 operation pic x(8).
01 flat-status pic xx.
01 index-status pic xx.
01 finished pic 9 value 0.
procedure division.
 accept operation from argument-value
 accept flat-path from argument-value
 accept index-path from argument-value
 evaluate operation
 when 'load'
   open input flat-file
   perform check-flat
   open output index-file
   perform check-index
   perform until finished = 1
     read flat-file
     evaluate flat-status
     when '10' move 1 to finished
     when '00'
       move flat-record to index-record
       write index-record
       perform check-index
     when other perform check-flat
     end-evaluate
   end-perform
 when 'dump'
   open input index-file
   perform check-index
   open output flat-file
   perform check-flat
   perform until finished = 1
     read index-file next record
     evaluate index-status
     when '10' move 1 to finished
     when '00'
       move index-record to flat-record
       write flat-record
       perform check-flat
     when other perform check-index
     end-evaluate
   end-perform
 when other stop run returning 64
 end-evaluate
 close flat-file
 perform check-flat
 close index-file
 perform check-index
 stop run returning 0.
check-flat.
 if flat-status not = '00'
   display 'FLAT-STATUS=' flat-status upon syserr
   stop run returning 65
 end-if.
check-index.
 if index-status not = '00'
   display 'INDEX-STATUS=' index-status upon syserr
   stop run returning 66
 end-if.
"""


ABEND = """identification division.
program-id. CEE3ABD.
data division.
linkage section.
01 abcode pic s9(9) binary.
01 timing pic s9(9) binary.
procedure division using abcode timing.
 display 'TWIN-CEE3ABD=' abcode upon syserr
 stop run returning 12.
"""


def wrapper(job):
    if job == "POSTTRAN":
        return """identification division.
program-id. twinmain.
procedure division.
 call 'CBTRN02C'
 stop run returning return-code.
"""
    return """identification division.
program-id. twinmain.
data division.
working-storage section.
01 external-parms.
 05 parm-length pic s9(04) comp value 10.
 05 parm-date pic x(10).
procedure division.
 accept parm-date from environment 'TWIN_PROCESSING_DATE'
 call 'CBACT04C' using external-parms
 stop run returning return-code.
"""


def build(target, *, instrument=False):
    host = linux_platform()
    clock = compiler_clock()
    host["compiler_clock"] = {"package": "libfaketime=0.9.10-2.1",
                              "fixed_utc": clock["FAKETIME"],
                              "library_sha256": sha(Path(clock["LD_PRELOAD"]).read_bytes()),
                              "scope": "compiler subprocesses only, never application runtime"}
    bindings = load_bindings()
    if bindings["source_commit"] != SOURCE_COMMIT:
        raise ValueError("unexpected upstream source")
    target = new_output(target)
    sources = {}
    for job, program in PROGRAMS.items():
        folder = target / job
        folder.mkdir()
        (folder / "bin").mkdir()
        (folder / "logs").mkdir()
        for relative, digest in bindings["artifacts"].items():
            p = Path(relative)
            if (p.suffix.lower() == ".cpy" or p.name == program + ".cbl"):
                # All originals copied with their pinned bytes, never rewritten.
                shutil.copyfile(ROOT / p, folder / p.name)
                sources[relative] = digest
        for name in ("LICENSE", "NOTICE"):
            shutil.copyfile(ROOT / "spec/mainframe/copybooks" / name, folder / name)
        (folder / "main.cob").write_text(wrapper(job), encoding="ascii")
        (folder / "abend.cob").write_text(ABEND, encoding="ascii")
        compile_source=program+'.cbl'
        if instrument:
            from .scenario_coverage import instrument as add_probes
            traced,inventory=add_probes((folder/compile_source).read_text(),program)
            compile_source=program+'-traced.cbl'
            (folder/compile_source).write_text(traced,encoding='ascii')
            write_json(folder/'coverage-inventory.json',inventory)
        execute(["cobc", "-c", "-fixed", *FLAGS, "-I", ".", compile_source, "-o", "program.o"], folder, folder / "logs/compile-original")
        execute(["cobc", "-x", "-free", *FLAGS, "-fstatic-call", "main.cob", "abend.cob", "program.o", "-o", "bin/twin"], folder, folder / "logs/link")
        for dd, (_, key) in FILES[job].items():
            if key:
                (folder / (dd + ".cob")).write_text(indexed_adapter(job, dd), encoding="ascii")
                execute(["cobc", "-x", "-free", *FLAGS, dd + ".cob", "-o", "bin/" + dd], folder, folder / ("logs/compile-" + dd))
    hashes = {p.relative_to(target).as_posix(): sha(p.read_bytes()) for p in sorted(target.rglob("*")) if p.is_file() and (p.parent.name == "bin" or p.suffix in (".cob", ".cbl", ".cpy") or p.name=='coverage-inventory.json')}
    return receipt(target / "build-receipt.json", phase="build", source_commit=SOURCE_COMMIT,
                   source_tree=SOURCE_TREE, license="Apache-2.0", coverage_instrumented=instrument,
                   license_sha256=sha((ROOT / "spec/mainframe/copybooks/LICENSE").read_bytes()),
                   driver_sha256=sha(Path(__file__).read_bytes()),
                   source_hashes=sources, files=hashes, host=host, flags=FLAGS,
                   adapters="Generated indexed file bridge, parameter wrapper and explicit RC12 CEE3ABD shim",
                   limits="No CICS, JES/JCL execution, VSAM implementation or z/OS equivalence claim")


def verify_build(target):
    target = Path(target).resolve()
    d = json.loads((target / "build-receipt.json").read_text())
    seal = d.pop("content_sha256")
    if sha(json.dumps(d, sort_keys=True, separators=(",", ":")).encode()) != seal:
        raise ValueError("build receipt digest mismatch")
    if d["source_commit"] != SOURCE_COMMIT or d["run_class"] != "engineering":
        raise ValueError("wrong build binding")
    for name, digest in d["files"].items():
        p = (target / name).resolve()
        if not p.is_relative_to(target) or sha(p.read_bytes()) != digest:
            raise ValueError("build artifact mismatch")
    return d


def public_inputs(scenario):
    job, relative = PUBLIC_SCENARIOS[scenario]
    base = ROOT / "tests/mainframe/fixtures" / relative
    meta = json.loads((base / "run.json").read_text())
    bindings = load_bindings()
    provenance = json.loads((ROOT / "tests/mainframe/fixtures/PROVENANCE.json").read_text())["files"]
    before = [r for r in meta["datasets"] if r["phase"] == "before"]
    if scenario == "intcalc-missing-disclosure":
        before = [dict(r, dd=Path(r["file"]).stem, codec="cp037") for r in meta["expected_failure"]["datasets"]]
    images = {}
    hashes = {}
    for row in before:
        source = (base / row["file"]).resolve()
        if not source.is_relative_to(base.resolve()):
            raise ValueError("public fixture path escape")
        raw = source.read_bytes()
        expected = row.get("sha256", provenance.get(source.relative_to(ROOT).as_posix()))
        if not expected or sha(raw) != expected:
            raise ValueError("public fixture hash mismatch")
        dd = row["dd"]
        binding = dataset_binding(bindings, job, "STEP15", dd)
        if row["lrecl"] != FILES[job][dd][0]:
            raise ValueError("fixture record length mismatch")
        images[dd] = to_ascii_fixed(load_copybook(ROOT / binding["copybook"]), raw, codec=row["codec"])
        hashes[dd] = sha(raw)
    if set(images) != set(FILES[job]):
        raise ValueError("incomplete public input set")
    if scenario.startswith('posttran-') and scenario != 'posttran-public':
        from .posttran_invariants import rejection_inputs
        images = rejection_inputs(images, scenario)
        meta = dict(meta, public_input_variant=scenario)
    return job, meta, images, hashes


def unframe(raw, length):
    if not raw:
        return b""
    if len(raw) % (length + 1) or any(raw[i] != 10 for i in range(length, len(raw), length + 1)):
        raise ValueError("invalid fixed ASCII framing")
    return b"".join(raw[i:i+length] for i in range(0, len(raw), length+1))


def frame(raw, length):
    if len(raw) % length:
        raise ValueError("partial fixed record")
    return b"".join(raw[i:i+length] + b"\n" for i in range(0, len(raw), length))


def runtime_clock(job, meta):
    timestamp = meta['candidate_timestamp']
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}\.[0-9]{2}\.[0-9]{2}\.000000', timestamp):
        raise ValueError('unsupported deterministic timestamp')
    datetime.strptime(timestamp, '%Y-%m-%d-%H.%M.%S.%f')
    env = {'COB_CURRENT_DATE': timestamp[:10].replace('-', '/') + ' ' + timestamp[11:19].replace('.', ':') + '.000000000'}
    if job == 'INTCALC':
        value = meta.get('processing_date')
        if not isinstance(value,str) or not re.fullmatch(r'[0-9]{10}', value):
            raise ValueError('INTCALC requires explicit processing_date')
        datetime.strptime(value, '%Y%m%d%H')
        env['TWIN_PROCESSING_DATE'] = value
    elif job != 'POSTTRAN':
        raise ValueError('unknown job processing-date contract')
    # POSTTRAN explicitly has no parameter date; only its runtime clock applies.
    return env


def run(target, scenario, output):
    linux_platform()
    target = Path(target).resolve()
    build_record=verify_build(target)
    job, meta, images, hashes = public_inputs(scenario)
    env = runtime_clock(job, meta)
    if job == "POSTTRAN":
        from .posttran_invariants import require_collation_independent
        require_collation_independent(images)
    output = new_output(output)
    for name in ("files", "before", "after", "logs"):
        (output / name).mkdir()
    for dd, raw in images.items():
        length, key = FILES[job][dd]
        flat = output / "before" / dd
        flat.write_bytes(unframe(raw, length))
        physical = output / "files" / dd
        if key:
            execute([target / job / "bin" / dd, "load", flat, physical], output, output / "logs" / ("load-" + dd))
        else:
            physical.write_bytes(flat.read_bytes())
        env["DD_" + dd] = str(physical)
    result = execute([target / job / "bin/twin"], output, output / "logs/program", extra_env=env, allowed=(0, 4, 12))
    outputs = {}
    for dd, (length, key) in FILES[job].items():
        flat = output / "after" / (dd + ".fixed")
        if key:
            execute([target / job / "bin" / dd, "dump", flat, output / "files" / dd], output, output / "logs" / ("dump-" + dd))
        else:
            shutil.copyfile(output / "files" / dd, flat)
        raw = frame(flat.read_bytes(), length)
        (output / "after" / dd).write_bytes(raw)
        outputs[dd] = {"sha256": sha(raw), "records": len(raw) // (length+1)}
    invariants = None
    if job == "POSTTRAN":
        from .posttran_invariants import check, review_sheet
        invariants = check(images, {dd: (output / "after" / dd).read_bytes() for dd in FILES[job]}, timestamp=meta['candidate_timestamp'])
        write_json(output / 'posttran-invariants.json', invariants)
        write_json(output / 'posttran-review-sheet.json', review_sheet(images, {dd: (output / 'after' / dd).read_bytes() for dd in FILES[job]}))
    adequacy=dict(schema='scenario-adequacy/1',instrumented=False,decision_outcomes=None,
                  reason='uninstrumented control',releasable=False)
    if build_record.get('coverage_instrumented'):
        from .scenario_coverage import observe
        adequacy=observe(json.loads((target/job/'coverage-inventory.json').read_text()),result.stdout.decode())
        write_json(output/'scenario-adequacy.json',adequacy)
    return receipt(output / "run-receipt.json", scenario_adequacy=adequacy, invariants=invariants, phase="run", scenario=scenario, job=job,
                   build_receipt_sha256=sha((target / "build-receipt.json").read_bytes()),
                   inputs=hashes, input_ascii_sha256={dd: sha(raw) for dd, raw in images.items()},
                   public_input_variant=meta.get("public_input_variant"), outputs=outputs, returncode=result.returncode,
                   deterministic_clock=env["COB_CURRENT_DATE"], processing_date=env.get("TWIN_PROCESSING_DATE"),
                   processing_date_contract="required" if job == "INTCALC" else "not-used-by-POSTTRAN",
                   adjudication="not-performed", model_calls=0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    b = sub.add_parser("build"); b.add_argument("target", type=Path)
    r = sub.add_parser("run"); r.add_argument("target", type=Path); r.add_argument("scenario", choices=PUBLIC_SCENARIOS); r.add_argument("output", type=Path)
    args = p.parse_args()
    if args.action == "build":
        build(args.target)
    else:
        run(args.target, args.scenario, args.output)


if __name__ == "__main__":
    main()
