"""Bound public-file access. Approval is by exact bytes, never by filename alone."""

import hashlib
import json
import os
import stat
from pathlib import Path

from lightyear_control_tower.fileio import regular_reader
from lightyear_mainframe.records import compile_copybook, decode_fixed, decode_rdw
from lightyear_mainframe.zos_logs import observe

FILE_LIMIT = 4 * 1024 * 1024
ARTIFACT_LIMIT = 64 * 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Refused(ValueError):
    """Only closed codes are sent over either transport."""


class Workspace:
    def __init__(self, root, public_manifest, catalogue=None):
        self.root = Path(root).absolute()
        if any(
            p.is_symlink() or getattr(p, "is_junction", lambda: False)()
            for p in (self.root, *self.root.parents)
        ):
            raise Refused("workspace-invalid")
        self.public = public_manifest
        self.catalogue = catalogue

    def read(self, name, *, limit=FILE_LIMIT, purpose=None):
        if not isinstance(name, str) or not name or "\\" in name or ":" in name:
            raise Refused("path-refused")
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts or len(rel.parts) > 24:
            raise Refused("path-refused")
        path = self.root / rel
        if purpose and self.public.get(name, {}).get("purpose") != purpose:
            raise Refused("public-file-unbound")
        for p in (path, *path.parents):
            if p == self.root:
                break
            if p.is_symlink() or getattr(p, "is_junction", lambda: False)():
                raise Refused("path-refused")
        if os.name == "posix":
            # Every component is opened relative to an already-open directory.
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for part in rel.parts[:-1]:
                    nxt = os.open(
                        part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                    )
                    os.close(fd)
                    fd = nxt
                data = os.open(
                    rel.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
                )
                with os.fdopen(data, "rb") as f:
                    info = os.fstat(f.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                        raise Refused("file-refused")
                    raw = f.read(limit + 1)
            finally:
                os.close(fd)
        else:
            with regular_reader(path) as f:
                if os.fstat(f.fileno()).st_size > limit:
                    raise Refused("file-refused")
                raw = f.read(limit + 1)
        if len(raw) > limit:
            raise Refused("file-too-large")
        if purpose and sha(raw) != self.public[name]["sha256"]:
            raise Refused("public-file-changed")
        return raw

    def layout(self, name):
        return compile_copybook(
            self.read(name, purpose="copybook").decode("utf-8"), name
        )

    def describe(self, name):
        return self.layout(name).manifest()

    def decode(self, name, copybook, codec, framing):
        if codec not in {"cp037", "cp500", "cp1140"} or framing not in {"fixed", "rdw"}:
            raise Refused("format-refused")
        raw = self.read(name, purpose="development-records")
        if self.public[name].get("copybook") != copybook:
            raise Refused("copybook-binding-refused")
        records = (decode_fixed if framing == "fixed" else decode_rdw)(
            self.layout(copybook), raw, codec=codec
        )
        value = {"records": records, "sha256": sha(raw)}
        if len(json.dumps(value)) > FILE_LIMIT:
            raise Refused("response-too-large")
        return value

    def log(self, name):
        return observe(self.read(name, purpose="development-log").decode("utf-8"))

    def lane(self, source, target):
        from lightyear_control_tower.catalogue import read_catalogue

        if source != "CBACT04C" or target != "Java":
            raise Refused("lane-unavailable")
        # A catalogue is not manufactured from a successful development run.
        if self.catalogue is None:
            return {
                "source": source,
                "target": target,
                "status": "unqualified",
                "evidence": "catalogue-unavailable",
                "limits": "INTCALC-only",
            }
        c = self.catalogue
        view = read_catalogue(
            c["root"],
            Path(c["public_key"]).read_bytes(),
            qualification_key=Path(c["qualification_key"]).read_bytes(),
            scope=c["scope"],
        )
        entry = next((e for e in view["entries"] if e["id"] == c["entry_id"]), None)
        if entry is None:
            raise Refused("lane-unavailable")
        return {
            "source": source,
            "target": target,
            "status": entry["status"],
            "catalogue_sha256": view["catalogue_sha256"],
            "limits": "INTCALC-only; see accepted qualification",
            "evidence_sha256": entry["record_sha256"],
        }
