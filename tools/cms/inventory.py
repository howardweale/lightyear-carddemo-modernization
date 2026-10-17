"""Filename/size inventory of pinned CMS archives; never execute an archive."""
import argparse
import collections
import gzip
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path


def inventory(data, prefix="", depth=0):
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            path = prefix + member.filename
            rows.append({"path": path, "size_bytes": member.file_size})
            if depth < 2 and member.filename.endswith((".zip", ".jar", ".exe")):
                nested = archive.read(member)
                if zipfile.is_zipfile(io.BytesIO(nested)):
                    rows.extend(inventory(nested, path + "!/", depth + 1))
    return rows


def source_members(data):
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            text = archive.read(member).decode("cp1252")
            active = "\n".join(line[7:72] for line in text.splitlines()
                               if len(line) > 6 and line[6] not in "*/")
            match = re.search(r"PROGRAM-ID\.\s*([\w-]+)", active, re.I)
            kind = "program" if match else "documentation" if member.filename in ("README", "MANIFEST") else "copybook" if re.search(r"^\s*(?:01|77)\s", active, re.M) else "rate-data"
            calls = []
            if match:
                for literal, symbol in re.findall(r"^\s*CALL\s+(?:['\"]([^'\"]+)['\"]|([\w-]+))", active, re.I | re.M):
                    binding = re.search(r"\b" + re.escape(symbol) + r"\s+PIC\s+X\([^\)]+\)\s+VALUE\s+['\"]([^'\"]+)", active, re.I) if symbol else None
                    calls.append(literal or (binding[1] if binding else "UNRESOLVED:" + symbol))
            rows.append({"name": member.filename, "size_bytes": member.file_size,
                         "kind": kind, "program_id": match[1] if match else None,
                         "calls": sorted(set(calls)),
                         "copybooks": sorted(set(re.findall(r"^\s*COPY\s+([\w-]+)", active, re.I | re.M))) if kind != "documentation" else []})
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pins", type=Path, required=True)
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventories, sources, counts = {}, {}, {}
    for pin in json.loads(args.pins.read_text()):
        name = pin["url"].rsplit("/", 1)[1]
        data = (args.downloads / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != pin["sha256"]:
            raise ValueError("Download hash mismatch: " + name)
        inventories[name] = inventory(data)
        counts[name] = {"member_files_including_nested": len(inventories[name])}
        if name in ("files-fy-20215-software-release.zip", "cy-20212-esrd-main-frame-pricing-programs.zip"):
            sources[name] = source_members(data)
            counts[name]["source_categories"] = dict(collections.Counter(row["kind"] for row in sources[name]))
    args.output.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(inventories, indent=2) + "\n").encode()
    (args.output / "inventory.json.gz").write_bytes(gzip.compress(payload, mtime=0))
    for name, value in [("source-inventory.json", sources), ("inventory-counts.json", counts)]:
        (args.output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
