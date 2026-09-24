"""MS76: source-bound qualification of existing runtime acceptance code."""
import json
from pathlib import Path

from lightyear_common.io import normalize_logical_source, write_json, write_text
from lightyear_data.contracts import seal

from .campaign import ROOT, digest
from . import carddemo_gate, cloudbank_gate


def identity():
    import hashlib
    paths = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "src/lightyear_data/packs").glob("*.json")) + [
        ROOT / "spec/comparison-normalizations.json",
        ROOT / "factory/verifier-qualification/contract.json",
        ROOT / "factory/verifier-qualification/runtime-gates.json"]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(normalize_logical_source(p.read_bytes())).hexdigest()
            for p in paths if "__pycache__" not in p.parts}


def run():
    before = identity()
    contract = json.loads((ROOT / "factory/verifier-qualification/runtime-gates.json").read_text())
    if (contract["cloudbank"]["critical_methods"] != list(cloudbank_gate.METHODS)
            or contract["cloudbank"]["faults"] != list(cloudbank_gate.FAULTS)
            or contract["carddemo"]["faults"] != list(carddemo_gate.FAULTS)):
        raise ValueError("runtime gate campaign differs from its declared scope")
    gates = [cloudbank_gate.campaign(), carddemo_gate.campaign()]
    unchanged = before == identity()
    return seal({"kind": "ms76-existing-runtime-gate-qualification-v1",
                 "status": "passed" if unchanged and all(g["status"] == "passed" for g in gates) else "failed",
                 "files": before, "source_identity_sha256": digest(before),
                 "source_unchanged_during_campaign": unchanged, "gates": gates,
                 "contract": contract,
                 "claims": {"selected_existing_gate_paths_challenged": True,
                            "whole_cloudbank_gate_qualified": False, "partner_qualified": False,
                            "independent_blind_validation": False, "production_ready": False,
                            "native_runtime_reexecuted": False}})


def save(report, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "report.json", report)
    lines = ["# MS76 — existing runtime gate qualification", "", f"Result: **{report['status']}**.", "",
             "| Existing gate | Correct cases | Witnessed defects detected | Result |", "|---|---:|---:|---|"]
    for gate in report["gates"]:
        lines.append(f"| {gate['gate']} | {sum(r['verdict'] == 'passed' for r in gate['correct'])}/{len(gate['correct'])} | "
                     f"{sum(r['fault_outcome'] == 'detected' for r in gate['faults'])}/{len(gate['faults'])} | {gate['status']} |")
    lines += ["", "CloudBank: real local processes and three directly witnessed SQLite defects; five existing journey methods.",
              "CardDemo: actual oracle execution and seven persisted output mutations through the existing compare CLI.",
              "These denominators describe different experiments and must not be combined into a general detection rate.", ""]
    for gate in report["gates"]:
        lines += [f"Scope exclusions for `{gate['gate']}`: " + "; ".join(gate["excluded"]) + ".", ""]
        for fault in gate["faults"]:
            lines.append(f"- {fault.get('fault') or fault.get('id')}: {fault['fault_outcome']}")
        lines.append("")
    lines += ["Missing/malformed observations block acceptance. Correct representation alternatives remain acceptable.",
              "No independent review, partner qualification, native CloudBank deployment, or production claim.",
              "Raw evidence, gate results, witnesses and source identities are retained in report.json.", "",
              f"Report SHA-256: `{report['content_sha256']}`", ""]
    write_text(output / "report.md", "\n".join(lines))
