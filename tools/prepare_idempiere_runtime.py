"""Inspect pinned seed inputs without interpreting a dump as native execution."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

from lightyear_calibration.contracts import read_json, require, seal, verify
from lightyear_common.io import normalize_logical_source

SOURCE_COMMIT = "731515dcdd5278b843db33b9d3109d155b881951"
SEED_COMMIT = "30af25e9db302a6cdefd9e6c3846f7cedc5ce4d0"
SEEDS = {
    "postgresql": ("Adempiere_pg.jar", "f6e5f409791c9eb576caf3c36e0bf9747d59d261ff9bdd743e55fcb125b21b9c"),
    "oracle": ("Adempiere.jar", "a98f32665e1926b858e8dcc10f2c535dde8a5441f9792b2b26a3124ce333234b"),
}


def registrations(text):
    """Read exactly one pg_dump COPY section; never execute or guess dump SQL."""
    matches = list(re.finditer(
        r"^COPY adempiere\.ad_migrationscript \(([^\n]+)\) FROM stdin;\n(.*?)\n\\\.$",
        text.replace("\r\n", "\n"), re.MULTILINE | re.DOTALL))
    require(len(matches) == 1, "Expected one migration registration COPY section")
    cols = matches[0][1].split(", ")
    require(len(cols) == len(set(cols)), "Duplicate registration columns")
    require({"filename", "name", "isapply", "status"} <= set(cols), "Missing registration columns")
    result = []
    for line in matches[0][2].splitlines():
        cells = line.split("\t")
        require(len(cells) == len(cols), "Malformed registration row")
        row = dict(zip(cols, cells))
        # These fields in the pinned seed are plain ASCII. Reject escapes rather
        # than silently comparing an encoded COPY value with a source filename.
        require(all("\\" not in row[k] for k in ("filename", "name", "isapply", "status")),
                "Unsupported registration field escape")
        result.append({k: row[k] for k in ("filename", "name", "isapply", "status")})
    return result


def classify_pairs(pairs, rows):
    by_file = {}
    for row in rows:
        by_file.setdefault(row["filename"], []).append(row)
    result = []
    for pair in sorted(pairs, key=lambda p: p["pair_id"]):
        path = PurePosixPath(pair["postgresql"]["path"])
        hits = by_file.get("postgresql/" + path.name, [])
        applied = (len(hits) == 1 and hits[0]["name"] == path.name
                   and hits[0]["isapply"] == "Y" and hits[0]["status"] == "CO")
        status = "seed-declares-applied" if applied else "registration-ambiguous" if hits else "not-in-seed-register"
        result.append({"pair_id": pair["pair_id"], "postgresql_path": str(path),
                       "seed_registration_status": status,
                       "post_migration_maintenance": "processes_post_migration" in path.parts,
                       "native_execution_eligible": None})
    return result


def prepare(root, source, seeds):
    manifest = read_json(root / "factory/idempiere-divergence-audit/pairing-manifest.json")
    measurement = read_json(root / "docs/calibration/idempiere/measurement.json")
    verify(manifest); verify(measurement)
    require(manifest["source"]["commit"] == SOURCE_COMMIT == measurement["source_commit"], "Wrong source pin")
    require(measurement["pairing_manifest_sha256"] == manifest["content_sha256"], "Baseline pairing drift")
    source = source.resolve()
    for pair in manifest["pairs"]:
        for lane in ("oracle", "postgresql"):
            record = pair[lane]
            path = (source / record["path"]).resolve()
            require(path.is_relative_to(source), "Source escapes root")
            require(hashlib.sha256(normalize_logical_source(path.read_bytes())).hexdigest()
                    == record["logical_sha256"], "Pinned migration source changed")
    seed_records = {}
    for lane, (name, expected) in SEEDS.items():
        data = (seeds / name).read_bytes()
        require(hashlib.sha256(data).hexdigest() == expected, "Pinned seed hash mismatch: " + name)
        with zipfile.ZipFile(seeds / name) as archive:
            members = [{"name": i.filename, "bytes": i.file_size} for i in archive.infolist()]
            if lane == "postgresql":
                rows = registrations(archive.read("Adempiere_pg.dmp").decode("utf-8"))
        seed_records[lane] = {"archive": name, "sha256": expected, "bytes": len(data), "members": members,
            "url": f"https://raw.githubusercontent.com/idempiere/binary.file/{SEED_COMMIT}/database/13/{name}"}
    cases = classify_pairs(manifest["pairs"], rows)
    counts = {s: sum(c["seed_registration_status"] == s for c in cases) for s in
              ("seed-declares-applied", "not-in-seed-register", "registration-ambiguous")}
    return seal({"schema_version": "1.0", "artifact_type": "lightyear-idempiere-runtime-preflight",
        "status": "prepared-not-executed", "source_commit": SOURCE_COMMIT, "seed_commit": SEED_COMMIT,
        "pairing_manifest_sha256": manifest["content_sha256"], "baseline_sha256": measurement["content_sha256"],
        "baseline_counts": measurement["counts"]["after"], "baseline_pair_counts": measurement["case_counts"]["after"],
        "seed_inputs": seed_records, "postgresql_seed_register_rows": len(rows), "seed_registration_counts": counts,
        "cases": cases, "native_catalog_captures": 0, "native_migration_executions": 0,
        "oracle_seed_register_verified": False, "historical_entry_states_verified": False,
        "customer_equivalence_claim": False,
        "boundaries": ["Seed registration is an offline dump observation, not a live database result.",
            "No pair is execution-eligible until both live registers and its entry state are checked.",
            "A release-13 catalog cannot stand in for the historical entry state of every migration.",
            "The calibration gate remains unchanged; no new decidability measurement is claimed."]})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--seeds", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = prepare(args.root, args.source, args.seeds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "seed_registration_counts": result["seed_registration_counts"]}))


if __name__ == "__main__":
    main()
