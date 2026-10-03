"""Immutable folder intake with explicit sidecar metadata and value-free findings."""

import re
from datetime import datetime
from pathlib import Path

from lightyear_control_tower.decisions import canonical
from .records import (
    DecodeError,
    decode_fixed,
    decode_rdw,
    decode_text_lines,
    load_copybook,
)
from .source import sha
from .zos_bindings import (
    ROOT,
    BINDINGS,
    compare_jcl,
    dataset_binding,
    inspect_jcl,
    load_bindings,
)
from .zos_evidence import confined, freeze, read_json, write_json, load_run
from .zos_logs import observe

KINDS = {
    "jcl",
    "job-output",
    "return-codes",
    "before-dataset",
    "after-dataset",
    "compiler-listing",
    "coverage",
    "note",
    "run-metadata",
    "unknown",
}


def classify(relative):
    p = Path(relative)
    name = p.name.lower()
    if name == "run.json":
        return "run-metadata"
    if p.suffix.lower() in (".jcl", ".prc"):
        return "jcl"
    if "before" in p.parts:
        return "before-dataset"
    if "after" in p.parts:
        return "after-dataset"
    if name in ("job-output.txt", "jes.txt", "sysout.txt", "job.log"):
        return "job-output"
    if name in ("return-codes.txt", "return-codes.json", "rc.txt"):
        return "return-codes"
    if "compiler" in name or name.endswith(".lst"):
        return "compiler-listing"
    if "coverage" in name:
        return "coverage"
    if name in ("note.txt", "notes.txt", "run-note.txt"):
        return "note"
    return "unknown"


def finding(code, reason, **extra):
    return dict(code=code, reason=reason, **extra)


def decode_dataset(original, item):
    raw = confined(original, item["file"]).read_bytes()
    binding = item["binding"]
    codec = item["codec"]
    framing = item["recfm"]
    if framing in ("VB", "VBA", "VBS", "VS"):
        raise DecodeError(
            "BDW/blocked or spanned records unsupported; resend binary unblocked RDW records or fixed sequential records with DCB metadata"
        )
    if binding["mode"] == "text":
        if framing not in ("F", "FB", "FA", "FBA"):
            raise DecodeError("Text outputs require fixed-length binary lines")
        return decode_text_lines(
            raw, record_length=item["lrecl"], codec=codec, asa=framing in ("FA", "FBA")
        )
    layout = load_copybook(ROOT / binding["copybook"])
    if framing == "V":
        return decode_rdw(layout, raw, codec=codec)
    if framing not in ("F", "FB"):
        raise DecodeError(
            "Unknown record framing; provide RECFM and transfer description"
        )
    return decode_fixed(layout, raw, codec=codec)


def inspect_run(original, folder, files, bindings):
    classified = {f: classify(Path(f).relative_to(folder).as_posix()) for f in files}
    findings = []
    metadata_file = f"{folder}/run.json"
    metadata = {}
    if metadata_file in files:
        try:
            metadata = read_json(confined(original, metadata_file))
            if (
                not isinstance(metadata, dict)
                or metadata.get("schema") != "zos-delivery-run/1"
            ):
                raise ValueError()
        except (ValueError, TypeError):
            findings.append(
                finding(
                    "metadata-invalid",
                    "Run metadata is invalid; provide zos-delivery-run/1 metadata.",
                )
            )
            metadata = {}
    else:
        findings.append(
            finding(
                "metadata-missing",
                "Dataset transfer metadata missing; provide a run.json with job, dataset/DD bindings, RECFM, LRECL and code page.",
            )
        )
    job_match = re.fullmatch(
        r"(INTCALC|POSTTRAN|CREASTMT|TRANREPT)-run\d+-\d{4}-\d\d-\d\d", folder
    )
    job = metadata.get("job") or (job_match[1] if job_match else None)
    if not isinstance(job, str):
        job = None
    if job not in bindings["jobs"] or (job_match and job_match[1] != job):
        findings.append(
            finding(
                "job-unbound",
                "Run name/job does not match a known job; confirm the job identity.",
            )
        )
        job = None
    for file, kind in classified.items():
        if kind == "unknown":
            findings.append(
                finding(
                    "unknown-file",
                    "Unrecognized file retained; identify its purpose.",
                    file_sha256=sha(confined(original, file).read_bytes()),
                )
            )
    for kind in (
        "jcl",
        "job-output",
        "return-codes",
        "before-dataset",
        "after-dataset",
    ):
        if kind not in classified.values():
            findings.append(
                finding(
                    "missing-" + kind,
                    f'Missing {kind.replace("-", " ")}; please resend.',
                )
            )
    notes = "\n".join(
        confined(original, p).read_text(encoding="utf-8")
        for p, k in classified.items()
        if k == "note"
    )
    parameter_sources = {}
    for name in ("system_datetime", "processing_date", "candidate_timestamp"):
        stated = set(re.findall(r"^" + name.upper() + r"\s*=\s*(\S+)\s*$", notes, re.M))
        if metadata.get(name) is not None and not isinstance(metadata[name], str):
            findings.append(
                finding(
                    "parameter-invalid",
                    "Clock parameters must be explicit strings; confirm the original values.",
                )
            )
            metadata[name] = None
        if metadata.get(name):
            stated.add(metadata[name])
        if len(stated) > 1:
            findings.append(
                finding(
                    "note-parameter-conflict",
                    "Run note and metadata disagree on a declared clock parameter.",
                )
            )
            metadata[name] = None
        elif stated:
            parameter_sources[name] = (
                "metadata" if metadata.get(name) else "explicit-run-note"
            )
            metadata[name] = next(iter(stated))
    if not metadata.get("system_datetime"):
        findings.append(
            finding(
                "missing-system-time",
                "System date/time used was not stated; provide it with timezone.",
            )
        )
    else:
        try:
            stamp = datetime.fromisoformat(
                metadata["system_datetime"].replace("Z", "+00:00")
            )
            if stamp.utcoffset() is None:
                raise ValueError()
        except ValueError:
            findings.append(
                finding(
                    "system-time-invalid",
                    "System date/time is invalid or lacks a timezone; provide an ISO timestamp with offset.",
                )
            )
    jcls = [p for p, k in classified.items() if k == "jcl"]
    jcl_text = "\n".join(
        confined(original, p).read_text(encoding="utf-8") for p in jcls
    )
    if job:
        findings.extend(compare_jcl(bindings, job, jcl_text))
    output = "\n".join(
        confined(original, p).read_text(encoding="utf-8")
        for p, k in classified.items()
        if k in ("job-output", "return-codes")
    )
    compiler = "\n".join(
        confined(original, p).read_text(encoding="utf-8")
        for p, k in classified.items()
        if k == "compiler-listing"
    )
    observation = observe(output, compiler)
    findings.extend(observation["findings"])
    if observation["job_name"] and job and observation["job_name"] != job:
        findings.append(
            finding(
                "job-output-mismatch",
                "Job output names a different job from this run folder; confirm provenance.",
            )
        )
    # Missing identity/options are explicit, but do not invent an engine fingerprint.
    if not observation["steps"]:
        findings.append(
            finding(
                "missing-step-codes",
                "No recognized step completion records; provide IEF messages or STEP/PGM/RC lines.",
            )
        )
    date_matches = set(re.findall(r"\bPARM='(\d{10})'", jcl_text))
    declared_date = metadata.get("processing_date")
    if declared_date:
        date_matches.add(declared_date)
    processing_date = next(iter(date_matches)) if len(date_matches) == 1 else None
    if job == "INTCALC" and (
        not isinstance(processing_date, str)
        or not re.fullmatch(r"\d{10}", processing_date)
    ):
        findings.append(
            finding(
                "processing-date-unbound",
                "INTCALC processing date missing or conflicting between JCL and metadata; confirm the exact PARM.",
            )
        )
        processing_date = None
    items, seen, identities = [], set(), set()
    descriptors = metadata.get("datasets", [])
    if not isinstance(descriptors, list):
        descriptors = []
        findings.append(
            finding(
                "dataset-metadata",
                "Datasets must be a list of explicit transfer bindings.",
            )
        )
    for desc in descriptors:
        try:
            if (
                not isinstance(desc, dict)
                or desc["phase"] not in ("before", "after")
                or not job
            ):
                raise ValueError()
            file = f'{folder}/{desc["file"]}'
            confined(original, file)
            if (
                file not in files
                or file in seen
                or classified[file] != desc["phase"] + "-dataset"
            ):
                raise ValueError()
            seen.add(file)
            binding = dataset_binding(bindings, job, desc["step"], desc["dd"])
            identity = (desc["step"], desc["dd"], desc["phase"])
            if identity in identities:
                raise ValueError()
            identities.add(identity)
            if desc.get("dsn") != binding["dsn"]:
                findings.append(
                    finding(
                        "dataset-name-mismatch",
                        "Delivered dataset name differs from pinned JCL; review its binding.",
                        dd=desc["dd"],
                    )
                )
            dcb_rows = [
                r
                for r in inspect_jcl(jcl_text)
                if r["step"] == desc["step"] and r["dd"] == desc["dd"]
            ]
            dcb = dcb_rows[0]["dcb"] if len(dcb_rows) == 1 else {}
            attrs = {}
            origins = {}
            for attr in ("recfm", "lrecl", "blksize"):
                attrs[attr] = desc.get(attr, dcb.get(attr))
                origins[attr] = (
                    "declared"
                    if attr in desc
                    else ("derived-from-submitted-JCL" if attr in dcb else "missing")
                )
                if attr in desc and attr in dcb and desc[attr] != dcb[attr]:
                    findings.append(
                        finding(
                            "dcb-disagreement",
                            f"Declared {attr.upper()} disagrees with submitted JCL; confirm transfer framing.",
                            dd=desc["dd"],
                        )
                    )
            if (
                not isinstance(attrs["recfm"], str)
                or type(attrs["lrecl"]) is not int
                or not 1 <= attrs["lrecl"] <= 32760
                or type(attrs["blksize"]) is not int
                or attrs["blksize"] < 0
            ):
                raise ValueError()
            codec = desc.get("codec", "cp037")
            if codec not in ("cp037", "cp500", "cp1140"):
                raise ValueError()
            item = dict(
                file=file,
                phase=desc["phase"],
                step=desc["step"],
                dd=desc["dd"],
                binding=binding,
                codec=codec,
                code_page_observation=(
                    "declared " + codec if "codec" in desc else "assumed cp037"
                ),
                format_origins=origins,
                **attrs,
            )
            expected_length = binding["record_length"] + (
                4 if attrs["recfm"] == "V" else 0
            )
            if attrs["lrecl"] != expected_length:
                findings.append(
                    finding(
                        "record-length",
                        "Declared LRECL disagrees with the bound copybook/program layout.",
                        dd=desc["dd"],
                    )
                )
            raw = confined(original, file).read_bytes()
            if b"\r\n" in raw:
                findings.append(
                    finding(
                        "text-conversion-crlf",
                        "CR/LF pairs found where binary EBCDIC records are required; resend binary.",
                        dd=desc["dd"],
                    )
                )
            if raw and sum(32 <= b <= 126 and b != 0x40 for b in raw) / len(raw) > 0.80:
                findings.append(
                    finding(
                        "text-conversion-ascii",
                        "Byte distribution looks like ASCII text rather than EBCDIC; confirm binary download.",
                        dd=desc["dd"],
                    )
                )
            if attrs["recfm"] in ("F", "FB", "FA", "FBA") and len(raw) % attrs["lrecl"]:
                findings.append(
                    finding(
                        "fixed-framing",
                        "Byte count is not a multiple of the declared LRECL; resend complete binary records.",
                        dd=desc["dd"],
                    )
                )
            try:
                records = decode_dataset(original, item)
                # All bound business records are DISPLAY, so controls are implausible.
                if any(
                    any(ord(c) < 32 or 127 <= ord(c) < 160 for c in f["value"])
                    for r in records
                    for f in r["fields"]
                ):
                    findings.append(
                        finding(
                            "byte-distribution",
                            "Decoded DISPLAY fields contain control bytes; confirm code page and binary transfer.",
                            dd=desc["dd"],
                        )
                    )
                item["records"] = len(records)
            except (DecodeError, ValueError):
                reason = "Record bytes do not match declared framing/layout; resend binary with confirmed DCB and code page."
                if attrs["recfm"] in ("VB", "VBA", "VBS", "VS"):
                    reason = "Blocked/spanned variable records unsupported; resend unblocked binary RDW (RECFM V) or fixed sequential records with DCB."
                findings.append(finding("decode-refused", reason, dd=desc["dd"]))
                item["records"] = None
            item["sha256"] = sha(raw)
            items.append(item)
        except (KeyError, ValueError, TypeError):
            findings.append(
                finding(
                    "unbound-dataset",
                    "Dataset metadata is missing, ambiguous or invalid; supply file, phase, step, DD, DSN and transfer DCB.",
                )
            )
    for f, k in classified.items():
        if k in ("before-dataset", "after-dataset") and f not in seen:
            findings.append(
                finding(
                    "unbound-dataset",
                    "Dataset file has no validated explicit binding; supply its transfer metadata.",
                    file_sha256=sha(confined(original, f).read_bytes()),
                )
            )
    # Required mutation/output set, derived from the application run sheet.
    required = {
        "INTCALC": {"ACCTFILE", "TRANSACT"},
        "POSTTRAN": {"ACCTFILE", "TRANFILE", "TCATBALF", "DALYREJS"},
        "CREASTMT": {"STMTFILE", "HTMLFILE"},
        "TRANREPT": {"TRANREPT"},
    }.get(job, set())
    present = {(i["dd"], i["phase"]) for i in items}
    input_dds = {
        "INTCALC": {"TCATBALF", "XREFFILE", "ACCTFILE", "DISCGRP"},
        "POSTTRAN": {"DALYTRAN", "XREFFILE", "ACCTFILE", "TCATBALF", "TRANFILE"},
        "CREASTMT": {"TRNXFILE", "XREFFILE", "ACCTFILE", "CUSTFILE"},
        "TRANREPT": {"TRANFILE", "CARDXREF", "TRANTYPE", "TRANCATG", "DATEPARM"},
    }.get(job, set())
    for dd in sorted(input_dds):
        if (dd, "before") not in present:
            findings.append(
                finding(
                    "missing-input",
                    "Before-image of required application input missing.",
                    dd=dd,
                )
            )
    for dd in sorted(required):
        for phase in ("before", "after"):
            if (dd, phase) not in present:
                findings.append(
                    finding(
                        "missing-image",
                        f"Missing {phase}-image of required output/update dataset; provide an empty binary image if it was newly created.",
                        dd=dd,
                    )
                )
    return dict(
        schema="zos-intake-run/1",
        job=job,
        source_folder=folder,
        files=classified,
        datasets=items,
        findings=findings,
        processing_date=processing_date,
        system_datetime=metadata.get("system_datetime"),
        candidate_timestamp=metadata.get("candidate_timestamp"),
        starting_state_id=metadata.get("starting_state_id"),
        parameter_sources=parameter_sources,
        observation=observation,
        bindings_sha256=sha(BINDINGS.read_bytes()),
    )


def intake(folder, description, signer):
    bindings = load_bindings()
    arrival, manifest = freeze(folder, description, signer)
    groups = {}
    for f in manifest["files"]:
        parts = Path(f["path"]).parts
        group = parts[0] if len(parts) > 1 else "_unassigned"
        groups.setdefault(group, []).append(f["path"])
    hashes, gaps = {}, []
    for n, (folder, files) in enumerate(sorted(groups.items()), 1):
        name = f"run-{n:03d}"
        try:
            run = inspect_run(arrival / "original", folder, files, bindings)
        except (UnicodeError, ValueError, KeyError, TypeError):
            run = dict(
                schema="zos-intake-run/1",
                job=None,
                source_folder=folder,
                files={f: classify(f) for f in files},
                datasets=[],
                findings=[
                    finding(
                        "run-unreadable",
                        "Run metadata or text files could not be parsed; provide UTF-8 job output and valid run metadata.",
                    )
                ],
                observation={},
                bindings_sha256=sha(BINDINGS.read_bytes()),
            )
        write_json(arrival / "runs" / name / "run.json", run)
        hashes[name] = sha((arrival / "runs" / name / "run.json").read_bytes())
        gaps.extend(dict(run=name, **item) for item in run["findings"])
    index = signer.sign(
        dict(
            schema="zos-intake/1",
            arrival_sha256=manifest["content_sha256"],
            bindings_sha256=sha(BINDINGS.read_bytes()),
            runs=hashes,
            findings=gaps,
            status="review-required" if gaps else "ready-for-review",
        )
    )
    write_json(arrival / "intake.json", index)
    write_json(arrival / "gaps.json", dict(schema="zos-gaps/1", findings=gaps))
    lines = [
        "# Delivery gaps",
        "",
        *[
            f'- {g["run"]}{" / "+g["dd"] if "dd" in g else ""}: {g["reason"]}'
            for g in gaps
        ],
    ]
    (arrival / "gaps.md").write_text(
        "\n".join(lines or ["No gaps"]) + "\n", encoding="utf-8"
    )
    # The inbox carries safe hashes/counts only; raw delivery values stay in arrivals.
    safe = dict(
        schema="zos-intake-review/1",
        arrival_sha256=manifest["content_sha256"],
        intake_sha256=index["content_sha256"],
        files=len(manifest["files"]),
        runs=len(hashes),
        findings=len(gaps),
        status=index["status"],
    )
    safe_path = (
        ROOT
        / "work/control-tower/requests/carddemo-zos/evidence"
        / f"{arrival.name}.json"
    )
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_bytes(canonical(safe) + b"\n")
    # Evidence cannot live under control-plane paths in the current Tower; use an explicitly safe mirror.
    mirror = ROOT / "work/mainframe/review" / f"{arrival.name}.json"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_bytes(canonical(safe) + b"\n")
    request = dict(
        schema="tower-request/1",
        scope="carddemo-zos",
        id=arrival.name,
        kind="intake-acceptance",
        bound={"intake": sha(mirror.read_bytes())},
        evidence={"intake": mirror.relative_to(ROOT).as_posix()},
        summary=f"Intake review: {len(hashes)} runs, {len(gaps)} findings. Operator review; not independent.",
        proposed_by="zos-intake",
        authored_by=["zos-intake"],
        workload="workload:carddemo-intcalc",
    )
    (safe_path.parent.parent / f"{arrival.name}.json").write_bytes(
        canonical(request) + b"\n"
    )
    return arrival, safe


def decode_run(path, public_key):
    arrival, run = load_run(path, public_key)
    if run["bindings_sha256"] != sha(BINDINGS.read_bytes()):
        raise ValueError("Intake binding table changed")
    load_bindings()
    records = {}
    for item in run["datasets"]:
        if item["records"] is None:
            continue
        key = item["step"] + "/" + item["dd"] + "/" + item["phase"]
        if key in records:
            raise ValueError("Duplicate dataset binding")
        records[key] = dict(
            descriptor=item, records=decode_dataset(arrival / "original", item)
        )
    result = dict(
        schema="zos-decoded-run/1",
        run_sha256=sha((Path(path) / "run.json").read_bytes()),
        datasets=records,
    )
    write_json(Path(path) / "decoded.json", result)
    write_json(Path(path) / "observation.json", run["observation"])
    return run, result
