"""Download an approved GitHub bundle, verify every byte, then stage without running it."""
import argparse
import hashlib
import io
import json
import re
import stat
import subprocess
import zipfile
from pathlib import Path

REPOSITORY = "howardweale/lightyear-carddemo-modernization"
SHA = re.compile(r"[0-9a-f]{64}")
LIMIT = 512 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_name(name):
    parts = name.split("/")
    require(all(p and p not in {".", ".."} and not p.endswith((".", " "))
                and not re.search(r'[\\:<>"|?*\x00-\x1f]', p)
                and not re.fullmatch(r"(?i:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?", p)
                for p in parts), "Unsafe bundle path")
    return name


def verify_archive(raw, commit, manifest_sha, zip_sha):
    require(SHA.fullmatch(manifest_sha) and SHA.fullmatch(zip_sha), "Expected approved SHA-256 values")
    require(len(raw) <= LIMIT and hashlib.sha256(raw).hexdigest() == zip_sha, "Bundle ZIP digest mismatch")
    archive = zipfile.ZipFile(io.BytesIO(raw))
    entries = archive.infolist()
    require(0 < len(entries) <= 10000 and sum(e.file_size for e in entries) <= LIMIT, "Bundle size limit")
    names = [safe_name(e.filename) for e in entries]
    require(len({n.casefold() for n in names}) == len(names), "Duplicate bundle path")
    for entry in entries:
        mode = entry.external_attr >> 16
        require(not entry.is_dir() and not entry.flag_bits & 1
                and stat.S_IFMT(mode) in {0, stat.S_IFREG}, "Nonregular or encrypted bundle entry")
    manifest_raw = archive.read("manifest.json")
    require(hashlib.sha256(manifest_raw).hexdigest() == manifest_sha, "Manifest digest mismatch")
    manifest = json.loads(manifest_raw)
    require(manifest["schema"] == "factory-install-bundle/1"
            and manifest["source_commit"] == commit
            and manifest["keys_created"] is False
            and manifest["signed_only_activated"] is False, "Manifest provenance mismatch")
    inventory = manifest["files"]
    paths = [safe_name(row["path"]) for row in inventory]
    require(len({p.casefold() for p in paths}) == len(paths)
            and "manifest.json" not in paths and set(names) == set(paths) | {"manifest.json"},
            "Manifest inventory mismatch")
    payload = {"manifest.json": manifest_raw}
    for row in inventory:
        data = archive.read(row["path"])
        require(type(row["bytes"]) is int and len(data) == row["bytes"]
                and SHA.fullmatch(row["sha256"])
                and hashlib.sha256(data).hexdigest() == row["sha256"], "Payload digest mismatch")
        payload[row["path"]] = data
    # Reject file/directory collisions, including Windows case aliases, before writing.
    folded = {p.casefold() for p in payload}
    require(all("/".join(p.split("/")[:i]).casefold() not in folded
                for p in payload for i in range(1, len(p.split("/")))), "Bundle path collision")
    return payload


def gh(route):
    # Binary pipe, never PowerShell text redirection of ZIP bytes. No login command.
    return subprocess.run(["gh", "api", f"repos/{REPOSITORY}/{route}"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


def stage(args):
    require(re.fullmatch(r"[0-9a-f]{40}", args.commit), "Expected full approved commit")
    require(not args.stage.exists() and args.stage.parent.is_dir(), "Staging folder must be new with an existing parent")
    run = json.loads(gh(f"actions/runs/{args.run_id}"))
    artifact = json.loads(gh(f"actions/artifacts/{args.artifact_id}"))
    name = "factory-first-install-" + args.commit
    require(run["head_sha"] == args.commit and run["status"] == "completed"
            and run["conclusion"] == "success" and run["event"] == "pull_request"
            and run["path"] == ".github/workflows/factory-first-install.yml"
            and run["repository"]["full_name"] == REPOSITORY
            and run["head_repository"]["full_name"] == REPOSITORY, "Workflow provenance mismatch")
    require(artifact["name"] == name and not artifact["expired"]
            and artifact["workflow_run"]["id"] == args.run_id
            and artifact["workflow_run"]["head_sha"] == args.commit
            and artifact["size_in_bytes"] <= LIMIT, "Artifact provenance mismatch")
    raw = gh(f"actions/artifacts/{args.artifact_id}/zip")
    require(len(raw) == artifact["size_in_bytes"] and artifact["digest"] == "sha256:" + args.zip_sha256,
            "Artifact archive metadata mismatch")
    payload = verify_archive(raw, args.commit, args.manifest_sha256, args.zip_sha256)
    args.stage.mkdir()  # Exclusive; preserve an existing or partially written staging folder.
    for name, data in payload.items():
        target = args.stage.joinpath(*name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    print(json.dumps({"source_commit": args.commit, "artifact_name": artifact["name"],
                      "manifest_sha256": args.manifest_sha256, "zip_sha256": args.zip_sha256,
                      "staging_folder": str(args.stage), "payload_files": len(payload) - 1}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("commit", "manifest-sha256", "zip-sha256"):
        parser.add_argument("--" + option, required=True)
    for option in ("run-id", "artifact-id"):
        parser.add_argument("--" + option, required=True, type=int)
    parser.add_argument("--stage", required=True, type=Path)
    try:
        stage(parser.parse_args())
    except Exception:
        parser.exit(1, "Bundle staging refused; preserve any partial folder and inspect the approved inputs.\n")
