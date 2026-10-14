"""Verify an offline Packer payload before installation. Never downloads or executes it."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def check(root: Path, manifest_sha256: str) -> dict:
    root = root.resolve()
    manifest_path = root / "manifest.json"
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256):
        raise ValueError("An exact bundle manifest SHA-256 is required")
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != manifest_sha256:
        raise ValueError("Bundle manifest hash differs")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if set(manifest) != {"schema", "files"} or manifest["schema"] != "lightyear.image-bundle.v1":
        raise ValueError("Unknown image bundle")
    files = manifest["files"]
    required = {"jdk21.tar.gz", "docker-static.tgz", "requirements.lock"}
    if not required.issubset(files) or not any(p.startswith("debs/") for p in files) or not any(p.startswith("wheels/") for p in files):
        raise ValueError("Bundle lacks offline runtime dependencies")
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Bundle symlinks are refused")
        if path.is_file() and path != manifest_path:
            actual.add(path.relative_to(root).as_posix())
    if actual != set(files):
        raise ValueError("Unlisted or missing bundle files")
    for name, expected in files.items():
        if not re.fullmatch(r"[a-zA-Z0-9_.+/-]+", name) or ".." in name.split("/") or name.startswith("/"):
            raise ValueError("Invalid bundle path")
        path = root / name
        if not path.resolve().is_relative_to(root) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Invalid bundle file binding")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError("Bundle hash differs: " + name)
    return {"verified": True, "files": len(files), "manifest_sha256": manifest_sha256}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.root, args.manifest_sha256), sort_keys=True))
