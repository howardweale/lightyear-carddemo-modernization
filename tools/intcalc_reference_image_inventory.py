"""Hash-only identity extraction from a locally built public OCI archive."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def inventory(path):
    with tarfile.open(path, "r:") as archive:
        def read(name, limit=1048576):
            matches = [m for m in archive.getmembers() if m.name == name]
            if len(matches) != 1 or not matches[0].isfile() or matches[0].size > limit:
                raise ValueError("oci-entry")
            return archive.extractfile(matches[0]).read()
        def blob(digest):
            if not isinstance(digest, str) or not digest.startswith("sha256:"):
                raise ValueError("oci-digest")
            value = digest[7:]
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("oci-digest")
            raw = read("blobs/sha256/" + value)
            if hashlib.sha256(raw).hexdigest() != value:
                raise ValueError("oci-hash")
            return raw
        index = read("index.json")
        rows = json.loads(index)["manifests"]
        candidates = []
        for entry in rows:
            raw = blob(entry["digest"])
            manifest = json.loads(raw)
            # Nested index emitted by buildx is traversed, not assumed a manifest.
            if "manifests" in manifest:
                for child in manifest["manifests"]:
                    child_raw = blob(child["digest"])
                    candidates.append((child["digest"], json.loads(child_raw)))
            else:
                candidates.append((entry["digest"], manifest))
        actual = []
        for digest, manifest in candidates:
            if "config" not in manifest:
                continue
            config_raw = blob(manifest["config"]["digest"])
            config = json.loads(config_raw)
            if config.get("os") == "linux" and config.get("architecture") == "amd64":
                actual.append({"manifest": digest, "config": manifest["config"]["digest"]})
        if len(actual) != 1:
            raise ValueError("oci-platform-inventory")
        return {"schema": "reference-built-image/1", "platform": "linux/amd64",
                **actual[0], "index_sha256": hashlib.sha256(index).hexdigest(),
                "qualified": False, "licence_and_isam_review": "PENDING"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    value = inventory(args.archive)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
