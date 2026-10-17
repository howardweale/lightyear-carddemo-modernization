"""Offline committed-public-artifact importer; no authority or credential access."""
import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path
from .requests import confined, read_bytes, MAX_BYTES
from .factory_policy import require, write_request
from .decisions import canonical
from .factory_history import historical_path, original_date


def committed(repository, commit, path):
    require(path.startswith("docs/factory/") and ".." not in path.split("/"))
    require(len(commit) == 40 and all(c in "0123456789abcdef" for c in commit))
    mode = subprocess.check_output(["git", "ls-tree", commit, "--", path], cwd=repository, text=True)
    require(mode.startswith("100644 blob ") or mode.startswith("100755 blob "), "public-regular-blob-required")
    raw = subprocess.check_output(["git", "show", commit + ":" + path], cwd=repository)
    require(len(raw) <= MAX_BYTES, "public-artifact-too-large")
    return raw


def historical_contract(repository, commit):
    paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", commit, "docs/factory"], cwd=repository, text=True).splitlines()
    paths = sorted(p for p in paths if historical_path(p))
    require(bool(paths), "backfill-no-historical-records")
    sources, records = [], []
    for path in paths:
        raw = committed(repository, commit, path)
        value = json.loads(raw)
        date = original_date(path, value)
        sources.append(dict(path=path, commit=commit, sha256=sha256(raw).hexdigest()))
        # The entire original document is retained, including every decision,
        # original date, condition and bound hash. No inferred authority mapping.
        records.append(dict(path=path, original_date=date, record=value))
    return dict(schema="factory-contract/1", kind="factory-decision-backfill", program="factory",
        sources=sources, details=dict(records=records, activation="signed-factory-decisions-only", historical_only=True))


def import_request(repository, root, contract, *, journal=None, public_key=None, trusted_head=None):
    # Validate all files before writing any bytes. Fetch only exact public Git blobs.
    from .factory_policy import validate_contract
    from .factory_order import intake
    intake(contract,journal=journal,public_key=public_key,trusted_head=trusted_head)
    validate_contract(contract, repository)
    if contract["kind"] == "factory-decision-backfill":
        require(len({s["commit"] for s in contract["sources"]}) == 1, "backfill-one-commit")
        require(contract == historical_contract(repository, contract["sources"][0]["commit"]), "backfill-complete-inventory-required")
    payload = {}
    for source in contract["sources"]:
        raw = committed(repository, source["commit"], source["path"])
        require(sha256(raw).hexdigest() == source["sha256"], "public-commit-byte-mismatch")
        target = confined(root, source["path"])
        if target.exists():
            require(read_bytes(target) == raw, "immutable-public-source-conflict")
        payload[target] = raw
    for target, raw in payload.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with target.open("xb") as stream:
                stream.write(raw)
    return write_request(root, contract,journal=journal,public_key=public_key,trusted_head=trusted_head)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--journal",type=Path)
    parser.add_argument("--public-key",type=Path)
    parser.add_argument("--trusted-head")
    args = parser.parse_args()
    trust=dict(journal=json.loads(read_bytes(args.journal)) if args.journal else None,
        public_key=read_bytes(args.public_key) if args.public_key else None,trusted_head=args.trusted_head)
    print(json.dumps(import_request(args.repository, args.root, json.loads(read_bytes(args.contract)),**trust), indent=2))


if __name__ == "__main__":
    main()
