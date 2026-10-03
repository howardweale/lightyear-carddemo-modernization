"""One-way INTCALC input bridge, local Java execution and offline verdict replay."""

import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from lightyear_control_tower.decisions import canonical, verify_envelope
from lightyear_control_tower.verification import verify_decision
from .records import from_ascii_fixed, load_copybook, to_ascii_fixed
from .source import sha
from .zos_bindings import ROOT
from .zos_compare import afters, compare_records, is_timestamp, TIMESTAMP
from .zos_evidence import confined, load_run, private_path, read_json, write_json, now
from .zos_intake import decode_run

INPUTS = {
    "TCATBALF": "tcatbal.txt",
    "DISCGRP": "discgrp.txt",
    "XREFFILE": "cardxref.txt",
    "ACCTFILE": "acctdata.txt",
}
OUTPUTS = {"ACCTFILE": "acctdata.txt", "TRANSACT": "transactions.txt"}


def implementation_hashes():
    files = sorted((ROOT / "src/lightyear_mainframe").glob("*.py"))
    files += [
        ROOT / "spec/mainframe/carddemo-bindings.json",
    ]
    files += [
        ROOT / "src/lightyear_control_tower" / name
        for name in ("carddemo_policy.py", "verification.py", "kinds.py")
    ]
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in files}


def prepare(path, public_key, signer):
    arrival, run = load_run(path, public_key)
    if run["job"] != "INTCALC" or run["findings"]:
        raise ValueError(
            "INTCALC bridge requires complete, bound intake with no unresolved findings"
        )
    processing = run["processing_date"]
    if not processing:
        raise ValueError("Processing date is not bound to delivered JCL or note")
    try:
        datetime.strptime(processing[:8], "%Y%m%d")
    except ValueError as exc:
        raise ValueError("Processing date is invalid") from exc
    timestamp = run.get("candidate_timestamp")
    if not isinstance(timestamp, str) or not is_timestamp(timestamp):
        raise ValueError(
            "Explicit candidate timestamp required in run metadata; never infer it from hidden after-images"
        )
    files = {}
    output = private_path(Path(path) / "candidate/inputs")
    output.mkdir(parents=True, exist_ok=True)
    for dd, filename in INPUTS.items():
        matches = [
            i for i in run["datasets"] if i["dd"] == dd and i["phase"] == "before"
        ]
        if len(matches) != 1:
            raise ValueError("Required INTCALC input has no unique before-image")
        item = matches[0]
        if item["recfm"] not in ("F", "FB"):
            raise ValueError("Input bridge requires fixed sequential before-images")
        raw = confined(arrival / "original", item["file"]).read_bytes()
        layout = load_copybook(ROOT / item["binding"]["copybook"])
        ascii_bytes = to_ascii_fixed(layout, raw, codec=item["codec"])
        target = output / filename
        if target.exists() and target.read_bytes() != ascii_bytes:
            raise ValueError("Candidate inputs already exist with different bytes")
        if not target.exists():
            target.write_bytes(ascii_bytes)
        files[filename] = dict(
            source_sha256=item["sha256"],
            sha256=sha(ascii_bytes),
            copybook_sha256=layout.copybook_sha256,
            records=len(raw) // layout.record_length,
            codec=item["codec"],
            code_page_observation=item["code_page_observation"],
        )
    receipt = signer.sign(
        dict(
            schema="zos-intcalc-inputs/1",
            run_sha256=sha((Path(path) / "run.json").read_bytes()),
            files=files,
            processing_date=processing,
            candidate_timestamp=timestamp,
            final_account_policy="source-faithful",
            implementation=implementation_hashes(),
        )
    )
    write_json(Path(path) / "candidate/input-manifest.json", receipt)
    return receipt


def run_candidate(path, jar, public_key, signer):
    path = private_path(path)
    manifest = read_json(path / "candidate/input-manifest.json")
    if (
        not verify_envelope(manifest, public_key)
        or manifest["implementation"] != implementation_hashes()
    ):
        raise ValueError("Input manifest signature or implementation binding failed")
    load_run(path, public_key)
    for file, entry in manifest["files"].items():
        if (
            sha(confined(path / "candidate/inputs", file).read_bytes())
            != entry["sha256"]
        ):
            raise ValueError("Input bytes changed")
    output = path / "candidate/outputs"
    if output.exists():
        raise ValueError(
            "Candidate already attempted; do not overwrite the prior outcome"
        )
    jar = Path(jar).resolve()
    if not jar.is_file() or jar.suffix != ".jar":
        raise ValueError("A built local candidate JAR is required")
    java = shutil.which("java")
    if not java:
        raise ValueError("Java is unavailable")
    output.mkdir(parents=True)
    command = [
        java,
        "-jar",
        str(jar),
        "--carddemo.input-dir=" + str(path / "candidate/inputs"),
        "--carddemo.output-dir=" + str(output),
        "--carddemo.processing-date=" + manifest["processing_date"],
        "--carddemo.timestamp=" + manifest["candidate_timestamp"],
        "--carddemo.final-account-policy=source-faithful",
    ]
    start = now()
    tick = time.monotonic()
    log = path / "candidate/execution.log"
    with log.open("xb") as stream:
        try:
            process = subprocess.run(
                command,
                cwd=path / "candidate",
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=300,
                check=False,
            )
            return_code, status = process.returncode, "completed"
        except subprocess.TimeoutExpired:
            return_code, status = None, "timed-out"
    files = {
        name: sha((output / name).read_bytes())
        for name in [*OUTPUTS.values(), "candidate-receipt.json"]
        if (output / name).is_file()
    }
    receipt = signer.sign(
        dict(
            schema="zos-intcalc-execution/1",
            input_manifest_sha256=manifest["content_sha256"],
            jar_sha256=sha(jar.read_bytes()),
            java_sha256=sha(Path(java).read_bytes()),
            started_at_utc=start,
            ended_at_utc=now(),
            elapsed_seconds=time.monotonic() - tick,
            status=status,
            return_code=return_code,
            outputs=files,
            log_sha256=sha(log.read_bytes()),
            implementation=implementation_hashes(),
        )
    )
    write_json(path / "candidate/execution.json", receipt)
    return receipt


def approved_paths(bundle, public_key, head, run_hash, *, at):
    if not public_key or not head:
        raise ValueError(
            "Normalization requires an independently trusted Tower public key and journal head"
        )
    ignored = {}
    from lightyear_control_tower.carddemo_policy import (
        rule as validate_rule,
        require,
        POLICY,
    )

    require(bundle.get("schema") in {"zos-approved-rules/1", "zos-rule-register/1"})
    require(isinstance(bundle.get("rules"), list))
    require(
        set(bundle)
        == (
            {"schema", "rules"}
            if bundle["schema"] == "zos-approved-rules/1"
            else {
                "schema",
                "rules",
                "scope",
                "disclosure_policy",
                "journal_head_sha256",
                "content_sha256",
                "signature",
            }
        )
    )
    if bundle["schema"] == "zos-rule-register/1":
        require(
            verify_envelope(bundle, public_key)
            and bundle.get("scope") == "carddemo-zos"
            and bundle.get("disclosure_policy") == POLICY
            and bundle.get("journal_head_sha256") == head
        )
    for item in bundle["rules"]:
        require(set(item) == {"rule", "proof"})
        rule, proof = item["rule"], item["proof"]
        validate_rule(rule)
        # Exact verified inbox binding includes a request hash; retain it from proof.
        event = next(
            e
            for e in proof["journal"]["events"]
            if e["content_sha256"] == proof["decision_sha256"]
        )
        bound = event["payload"]["bound"]
        require(bound["rule"] == sha(canonical(rule) + b"\n"))
        if (
            rule["workload"] != "workload:carddemo-intcalc"
            or rule["pattern"] != TIMESTAMP
            or run_hash not in rule["runs"]
            or not rule["still_caught"]["detected"]
        ):
            raise ValueError("Normalization scope or still-caught binding failed")
        verify_decision(
            proof,
            public_key,
            "normalization",
            bound,
            expected_head=head,
            scope="carddemo-zos",
            outcomes=["approved"],
            now=at,
        )
        ignored.setdefault(rule["dataset"], []).append(rule["field"])
    return ignored


def compute_verdict(
    path, public_key, *, normalizations=None, tower_key=None, tower_head=None, at=None
):
    path = private_path(path)
    run, decoded = decode_run(path, public_key)
    at = at or datetime.now(timezone.utc)
    reasons, comparisons = [], {}
    manifest = read_json(path / "candidate/input-manifest.json")
    execution = read_json(path / "candidate/execution.json")
    for record in (manifest, execution):
        if (
            not verify_envelope(record, public_key)
            or record["implementation"] != implementation_hashes()
        ):
            raise ValueError("Candidate evidence signature or implementation mismatch")
    if (
        manifest["run_sha256"] != decoded["run_sha256"]
        or execution["input_manifest_sha256"] != manifest["content_sha256"]
    ):
        raise ValueError("Candidate evidence belongs to a different run/input")
    if execution["return_code"] != 0 or execution["status"] != "completed":
        reasons.append("Candidate did not complete successfully.")
    if run["findings"]:
        reasons.append("Intake has unresolved findings.")
    ignored = (
        approved_paths(
            normalizations, tower_key, tower_head, decoded["run_sha256"], at=at
        )
        if normalizations
        else {}
    )
    for file, item in manifest["files"].items():
        if (
            sha(confined(path / "candidate/inputs", file).read_bytes())
            != item["sha256"]
        ):
            raise ValueError("Candidate input bytes changed")
    for file, expected in execution["outputs"].items():
        if sha(confined(path / "candidate/outputs", file).read_bytes()) != expected:
            raise ValueError("Candidate output bytes changed")
    if sha((path / "candidate/execution.log").read_bytes()) != execution["log_sha256"]:
        raise ValueError("Candidate log changed")
    for dd, filename in OUTPUTS.items():
        matches = [
            (k, v)
            for k, v in afters(decoded, "after").items()
            if v["descriptor"]["dd"] == dd
        ]
        if len(matches) != 1 or filename not in execution["outputs"]:
            reasons.append("Required bound output unavailable.")
            continue
        key, item = matches[0]
        binding = item["descriptor"]["binding"]
        try:
            candidate = from_ascii_fixed(
                load_copybook(ROOT / binding["copybook"]),
                (path / "candidate/outputs" / filename).read_bytes(),
                codec=item["descriptor"]["codec"],
            )
            paths = ignored.get(key, [])
            if any(p not in binding["timestamp_fields"] for p in paths):
                raise ValueError("Unqualified normalization field")
            for records in (candidate, item["records"]):
                if any(
                    not is_timestamp(f["value"])
                    for r in records
                    for f in r["fields"]
                    if f["path"] in paths
                ):
                    raise ValueError(
                        "Normalized field no longer matches timestamp pattern"
                    )
            comparisons[key] = compare_records(
                item["records"], candidate, binding, ignored=paths
            )
        except ValueError:
            reasons.append(
                "Output decoding, unique keys or normalization preconditions failed."
            )
    verdict = (
        "indeterminate"
        if reasons
        else (
            "equivalent"
            if comparisons and all(v["identical"] for v in comparisons.values())
            else "divergent"
        )
    )
    return dict(
        schema="zos-intcalc-verdict/1",
        verdict=verdict,
        as_of=at.isoformat(),
        run_sha256=decoded["run_sha256"],
        execution_sha256=execution["content_sha256"],
        input_manifest_sha256=manifest["content_sha256"],
        datasets=comparisons,
        reasons=sorted(set(reasons)),
        base_rules=[],
        normalization_source="verified-tower-decisions-only",
        approved_normalization_sha256=(
            sha(canonical(normalizations)) if normalizations else None
        ),
        tower_key_sha256=sha(tower_key) if tower_key else None,
        tower_head=tower_head,
        implementation=implementation_hashes(),
        evidence_class="local-java-versus-delivered-records",
        intake_review="operator review requested; not independent",
        no_mainframe_execution_performed=True,
    )


def verdict(path, public_key, signer, **options):
    if options.get("normalizations"):
        write_json(
            Path(path) / "candidate/normalizations.json", options["normalizations"]
        )
    result = signer.sign(compute_verdict(path, public_key, **options))
    write_json(Path(path) / "verdict.json", result)
    if result["verdict"] == "divergent":
        from lightyear_control_tower.carddemo_policy import write_request, registry

        summary = dict(
            schema="zos-difference-review/1",
            source_sha256=result["run_sha256"],
            target_sha256=result["execution_sha256"],
            diagnostic_sha256=result["content_sha256"],
            **{
                key: sum(d[key] for d in result["datasets"].values())
                for key in ("added", "deleted", "changed")
            },
        )
        write_request(
            ROOT,
            "difference-disposition",
            {key: summary for key in registry().get("difference-disposition").hashes},
        )
    return result


def replay(path, public_key, *, tower_key=None):
    result = read_json(Path(path) / "verdict.json")
    if not verify_envelope(result, public_key):
        raise ValueError("Verdict signature failed")
    rules_path = Path(path) / "candidate/normalizations.json"
    rules = read_json(rules_path) if result["approved_normalization_sha256"] else None
    computed = compute_verdict(
        path,
        public_key,
        normalizations=rules,
        tower_key=tower_key,
        tower_head=result["tower_head"],
        at=datetime.fromisoformat(result["as_of"]),
    )
    signed_body = {
        k: v for k, v in result.items() if k not in ("signature", "content_sha256")
    }
    if canonical(computed) != canonical(signed_body):
        raise ValueError("Offline replay did not reproduce the signed verdict")
    return dict(
        schema="zos-offline-replay/1",
        status="verified",
        verdict=result["verdict"],
        verdict_sha256=result["content_sha256"],
        original_bytes_verified=True,
        candidate_execution_repeated=False,
    )
