"""Actual gate replay over SQL files or captured runtime observations, never invocation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

from lightyear_data.idempiere_comparison import compare_pair, _totals, policy
from lightyear_data import idempiere_comparison, idempiere_sql, semantic_core, contracts as data_contracts
from lightyear_qualification import protocol
from lightyear_common import io as common_io

from .contracts import (CalibrationError, MAX_CASES, MAX_RECORDS, MAX_UNITS, count, digest,
                        exact, implementation, label, read_json, require, seal, sha, verify)

ADAPTERS = {"oracle-postgresql-sql": ".sql", "transfer-observations": ".json"}
MAX_FILE = 16 * 1024 * 1024
MAX_CORPUS = 512 * 1024 * 1024


def gate_identity(adapter):
    modules = ([idempiere_comparison, idempiere_sql, semantic_core, data_contracts, common_io]
               if adapter == "oracle-postgresql-sql" else [protocol])
    return {"adapter": adapter, "implementation": implementation({m.__name__: Path(m.__file__) for m in modules}),
            "policy": policy() if adapter == "oracle-postgresql-sql" else
            {"contract": "transfer-observation/1", "scope": "accounts, operations and outcomes in captured observations"}}


def inventory(root, suffix):
    require(root.is_dir() and not root.is_symlink(), "Corpus root must be a real directory")
    included, excluded = [], []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Symbolic corpus paths are not admitted")
        if path.is_dir():
            continue
        require(path.is_file(), "Corpus contains a non-regular file")
        rel = path.relative_to(root).as_posix()
        label(rel, 1000)
        (included if path.suffix.lower() == suffix else excluded).append(rel)
        require(len(included) + len(excluded) <= 100000, "Corpus inventory exceeds file bound")
    return included, excluded


def discover(source, target, adapter, corpus_id):
    require(adapter in ADAPTERS, "Unsupported adapter")
    label(corpus_id)
    roots = {"source": source.absolute(), "target": target.absolute()}
    files = {side: inventory(root, ADAPTERS[adapter])[0] for side, root in roots.items()}
    paths = sorted(set(files["source"]) | set(files["target"]))
    require(0 < len(paths) <= MAX_CASES, "Corpus needs 1 to 20000 cases")
    return {"schema_version": "1.0", "corpus_id": corpus_id, "adapter": adapter,
            "roots": {side: str(root) for side, root in roots.items()},
            "cases": [{"id": p, "source": p if p in files["source"] else None,
                       "target": p if p in files["target"] else None} for p in paths]}


def safe_path(root, value):
    label(value, 1000)
    require("\\" not in value and not PurePosixPath(value).is_absolute() and
            all(p not in {".", "..", ""} for p in value.split("/")) and ":" not in value,
            "Unsafe corpus-relative path")
    path = root / value
    require(not any(p.is_symlink() for p in (path, *list(path.parents)[:len(PurePosixPath(value).parts)])), "Symbolic corpus path")
    require(path.resolve().is_relative_to(root.resolve()), "Corpus path escaped root")
    return path


def record(case_id, lane, first, last, kind, status, outcomes, reasons, source):
    return {"id": "unit:" + digest([case_id, lane, first, last, source.get("path")])[:24],
            "case_id": case_id, "lane": lane, "kind": kind, "status": status,
            "outcomes": sorted(set(outcomes)), "reason_codes": sorted(set(reasons)),
            "units": last - first + 1 if first else 0,
            "source": {**source, "first_unit": first, "last_unit": last}}


def sql_records(result, sources):
    rows = []
    for lane, segments in result["segments"].items():
        for segment in segments:
            rows.append(record(result["pair_id"], lane, segment["first_unit"], segment["last_unit"],
                               segment["kind"], {"parsed-and-compared": "decided", "parsed-but-indeterminate": "indeterminate",
                                                 "unparsed": "unsupported", "administrative-excluded": "excluded"}[segment["category"]],
                               segment["outcomes"], segment["reason_codes"],
                               {**sources[lane], "start_line": segment["start_line"], "end_line": segment["end_line"],
                                "unit_hashes_sha256": segment["unit_hashes_sha256"]}))
    if result["verdict"] == "indeterminate" and not any(r["status"] in {"indeterminate", "unsupported"} for r in rows):
        rows.append(record(result["pair_id"], "paired", 0, 0, "empty-comparison", "indeterminate", [],
                           ["no-comparable-sql-units"], {}))
    return rows


def scan(manifest, base=Path(".")):
    exact(manifest, {"schema_version", "corpus_id", "adapter", "roots", "cases"})
    require(manifest["schema_version"] == "1.0" and manifest["adapter"] in ADAPTERS, "Unsupported corpus contract")
    label(manifest["corpus_id"])
    exact(manifest["roots"], {"source", "target"})
    roots = {side: base / label(value, 2000) for side, value in manifest["roots"].items()}
    require(roots["source"].resolve() != roots["target"].resolve(), "Source and target roots must differ")
    cases = manifest["cases"]
    require(isinstance(cases, list) and 0 < len(cases) <= MAX_CASES, "Invalid case count")
    inventories = {side: inventory(root, ADAPTERS[manifest["adapter"]]) for side, root in roots.items()}
    listed, ids = {side: [] for side in roots}, set()
    for case in cases:
        exact(case, {"id", "source", "target"})
        label(case["id"])
        require(case["id"] not in ids, "Duplicate case ID")
        ids.add(case["id"])
        require(case["source"] is not None or case["target"] is not None, "Case has no input")
        for side in roots:
            if case[side] is not None:
                safe_path(roots[side], case[side])
                listed[side].append(case[side])
    for side in roots:
        require(len(listed[side]) == len(set(listed[side])), "A corpus file occurs in multiple cases")
        require(sorted(listed[side]) == inventories[side][0], "Manifest must cover every eligible file: " + side)
    rows, case_results, inputs, total_bytes = [], [], [], 0
    for case in sorted(cases, key=lambda c: c["id"]):
        texts, sources = {}, {}
        for side in roots:
            if case[side] is None:
                texts[side] = None
                sources[side] = {"path": None, "sha256": None}
                continue
            path = safe_path(roots[side], case[side])
            with path.open("rb") as f:
                raw = f.read(MAX_FILE + 1)
            require(len(raw) <= MAX_FILE, "Corpus file exceeds 16 MiB")
            total_bytes += len(raw)
            require(total_bytes <= MAX_CORPUS, "Corpus exceeds 512 MiB")
            raw = raw.replace(b"\r\n", b"\n")
            try:
                texts[side] = raw.decode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise CalibrationError("Corpus must use UTF-8; no partial report published") from exc
            sources[side] = {"path": case[side], "sha256": hashlib.sha256(raw).hexdigest()}
        inputs.append({"case_id": case["id"], **sources})
        if manifest["adapter"] == "oracle-postgresql-sql":
            result = compare_pair(case["id"], texts["source"] or "", texts["target"] or "")
            case_rows = sql_records(result, {"oracle": sources["source"], "postgresql": sources["target"]})
            if None in texts.values():
                missing = "missing-source-file" if texts["source"] is None else "missing-target-file"
                for row in case_rows:
                    if row["status"] != "excluded":
                        row["status"] = "indeterminate" if row["status"] != "unsupported" else "unsupported"
                        row["reason_codes"] = sorted(set(row["reason_codes"] + [missing]))
                if not any(missing in row["reason_codes"] for row in case_rows):
                    case_rows.append(record(case["id"], "paired", 0, 0, "missing-counterpart", "indeterminate", [], [missing], {}))
                result["verdict"] = "indeterminate"
            rows.extend(case_rows)
            case_results.append({"id": case["id"], "verdict": result["verdict"]})
        else:
            verdict, reasons = "indeterminate", []
            values = {}
            for side in roots:
                try:
                    require(texts[side] is not None, "missing-observation-file")
                    values[side] = protocol.strict_json(texts[side])
                    # Admit both lanes before comparing; never coerce a missing source to empty.
                    protocol.normalize(values[side])
                except (CalibrationError, protocol.ObservationError, KeyError, TypeError) as exc:
                    reasons.append(side + ":" + str(exc))
            if not reasons:
                result = protocol.compare(protocol.normalize(values["source"]), values["target"])
                verdict = {"passed": "equivalent", "failed": "divergent", "indeterminate": "indeterminate"}[result["verdict"]]
                if result["reason"]:
                    reasons.append(result["reason"])
            rows.append(record(case["id"], "paired", 1, 1, "transfer-observation", "indeterminate" if reasons else "decided",
                               [] if reasons else [verdict], reasons, {"captures": sources}))
            case_results.append({"id": case["id"], "verdict": verdict})
        require(len(rows) <= MAX_RECORDS, "Record bound exceeded")
    require(sum(r["units"] for r in rows) <= MAX_UNITS, "Unit bound exceeded")
    return {"corpus_id": manifest["corpus_id"], "adapter": manifest["adapter"],
            "corpus_sha256": digest({"adapter": manifest["adapter"], "inputs": inputs}),
            "gate": gate_identity(manifest["adapter"]), "cases": case_results, "records": rows,
            "provenance": {"mode": "local-gate-replay", "runtime_invocations": 0, "source_authentication": "not-established",
                           "inputs": inputs, "excluded_files": {side: inventories[side][1] for side in roots},
                           "scope": "all eligible files in the declared roots; other extensions explicitly excluded"}}


def import_idempiere(report, manifest):
    """Account for a retained gate run; hashes prove integrity, never authenticity or replay."""
    verify(report)
    verify(manifest)
    require(report.get("artifact_type") == "lightyear-idempiere-semantic-comparison" and
            report.get("schema_version") == "1.0" and report.get("scope") == "all-current-pairs",
            "Expected complete iDempiere comparison report")
    require(report["bindings"]["pairing_manifest_sha256"] == manifest["content_sha256"], "Pairing manifest binding mismatch")
    require(report["bindings"]["source_commit"] == manifest["source"]["commit"] and
            report["bindings"]["source_tree"] == manifest["source"]["tree"], "Source identity mismatch")
    pairs = manifest["pairs"]
    results = report["results"]
    require(isinstance(results, list) and 0 < len(results) <= MAX_CASES, "Invalid result count")
    pair_map = {p["pair_id"]: p for p in pairs}
    require(len(pair_map) == len(pairs) and len(results) == len(pairs) and
            len({r["pair_id"] for r in results}) == len(results) and
            set(pair_map) == {r["pair_id"] for r in results}, "Incomplete or duplicated pair scope")
    rows, cases = [], []
    for result in results:
        verify(result)
        label(result["pair_id"])
        pair = pair_map[result["pair_id"]]
        count(result["compared_effect_count"])
        require(type(result["ordered_effects_aligned"]) is bool, "Invalid alignment status")
        for lane in ("oracle", "postgresql"):
            next_unit, prior_line = 1, 0
            for segment in result["segments"][lane]:
                first, last = count(segment["first_unit"]), count(segment["last_unit"])
                start, end = count(segment["start_line"]), count(segment["end_line"])
                require(first == next_unit and last >= first and 0 < start <= end <= pair[lane]["lines"] + 1 and start >= prior_line,
                        "Invalid segment continuity or source range")
                next_unit, prior_line = last + 1, end
                reasons, outcomes, category = segment["reason_codes"], segment["outcomes"], segment["category"]
                require(isinstance(reasons, list) and len(reasons) <= 100 and len(reasons) == len(set(reasons)), "Invalid reason list")
                for reason in reasons:
                    label(reason)
                label(segment["kind"])
                sha(segment["unit_hashes_sha256"])
                require(isinstance(outcomes, list) and set(outcomes) <= {"equivalent", "divergent", "indeterminate"}, "Invalid outcomes")
                require(category in {"parsed-and-compared", "parsed-but-indeterminate", "unparsed", "administrative-excluded"}, "Unknown coverage category")
                if category == "parsed-and-compared":
                    require(bool(outcomes) and "indeterminate" not in outcomes, "Decided unit has open reasons")
                elif category == "parsed-but-indeterminate":
                    require(bool(reasons) and "indeterminate" in outcomes, "Unexplained indeterminate")
                elif category == "unparsed":
                    require(bool(reasons) and not outcomes and segment["kind"] == "unparsed", "Unsupported coverage promotion")
                else:
                    require(not reasons and not outcomes and segment["kind"] == "client-or-registration", "Invalid exclusion")
            from lightyear_data.idempiere_comparison import _coverage
            require(result["coverage"][lane] == _coverage(result["segments"][lane]), "Coverage count mismatch")
        case_rows = sql_records(result, {lane: {"path": pair[lane]["path"], "sha256": pair[lane]["logical_sha256"]}
                                         for lane in ("oracle", "postgresql")})
        has_difference = any("divergent" in r["outcomes"] for r in case_rows)
        unresolved = any(r["status"] in {"indeterminate", "unsupported"} for r in case_rows)
        expected = "divergent" if has_difference else "equivalent" if not unresolved and result["ordered_effects_aligned"] and result["compared_effect_count"] else "indeterminate"
        require(result["verdict"] == expected, "Retained verdict contradicts coverage")
        rows.extend(case_rows)
        cases.append({"id": result["pair_id"], "verdict": result["verdict"]})
    require(report["statistics"] == _totals(results), "Retained statistics mismatch")
    require(len(rows) <= MAX_RECORDS and sum(r["units"] for r in rows) <= MAX_UNITS, "Retained corpus exceeds bounds")
    return {"corpus_id": report["project_id"], "adapter": "oracle-postgresql-sql",
            "corpus_sha256": digest({k: report["bindings"][k] for k in ("pairing_manifest_sha256", "source_commit", "source_tree")}),
            "gate": {"adapter": "oracle-postgresql-sql", "retained_bindings": report["bindings"]},
            "cases": sorted(cases, key=lambda c: c["id"]), "records": rows,
            "provenance": {"mode": "retained-gate-report", "runtime_invocations": 0, "gate_replayed": False,
                           "source_authentication": "not-established", "input_report_sha256": report["content_sha256"],
                           "pairing_manifest_sha256": manifest["content_sha256"],
                           "scope": "paired current SQL migration scripts only; excludes the wider application estate"}}
