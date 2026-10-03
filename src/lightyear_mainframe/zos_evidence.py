"""Local chain of custody. Private values never leave the ignored arrival tree."""

import base64
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from lightyear_control_tower.decisions import canonical, digest, verify_envelope
from .source import sha
from .zos_bindings import ROOT

ARRIVALS = ROOT / "work/mainframe/arrivals"


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        Path(path).read_bytes(),
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
    )


def confined(root, relative):
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or ":" in relative
    ):
        raise ValueError("Unsafe relative path")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Unsafe relative path")
    root = Path(root).resolve()
    target = root / rel
    for part in [target, *target.parents]:
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("Links and junctions are forbidden")
    if not target.resolve().is_relative_to(root):
        raise ValueError("Path escaped evidence root")
    return target


def private_path(path):
    path = Path(path).absolute()
    try:
        relative = path.relative_to(ARRIVALS.absolute())
    except ValueError as exc:
        raise ValueError(
            "Derived data must remain under work/mainframe/arrivals"
        ) from exc
    return confined(ARRIVALS, relative.as_posix())


def write_json(path, value):
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Immutable stage products: a repeated invocation must agree or use a fresh intake.
    payload = canonical(value) + b"\n"
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("Refusing to replace an existing evidence product")
        return
    with path.open("xb") as stream:
        stream.write(payload)


class Signer:
    def __init__(self, private_key):
        from cryptography.hazmat.primitives import serialization

        self.key = serialization.load_pem_private_key(
            Path(private_key).read_bytes(), password=None
        )
        self.public = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def sign(self, body):
        return {
            **body,
            "content_sha256": digest(body),
            "signature": dict(
                algorithm="Ed25519",
                key_id=sha(self.public),
                value=base64.b64encode(self.key.sign(canonical(body))).decode(),
            ),
        }


def initialize_key(path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    path = Path(path).resolve()
    if path.is_relative_to(ARRIVALS.resolve()) or (
        path.is_relative_to(ROOT) and not path.is_relative_to(ROOT / "work")
    ):
        raise ValueError(
            "Signing keys must be outside arrivals and tracked source paths"
        )
    public_path = path.with_suffix(".public.pem")
    if path.exists() or public_path.exists():
        raise ValueError("Refusing to replace signing identity")
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as stream:
        stream.write(raw)
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return public_path


def freeze(folder, source_description, signer):
    folder = Path(folder)
    if folder.is_symlink() or (hasattr(folder, "is_junction") and folder.is_junction()):
        raise ValueError("Delivery root cannot be a link or junction")
    folder = folder.resolve()
    if not folder.is_dir() or folder.is_relative_to(ARRIVALS.resolve()):
        raise ValueError("Intake needs a delivery folder outside arrivals")
    arrival = ARRIVALS / (
        "arrival-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
        + uuid4().hex[:12]
    )
    arrival.mkdir(parents=True)
    files = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("Delivery links are forbidden")
        if path.is_dir():
            continue
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("Delivery contains a non-regular file")
        relative = path.relative_to(folder).as_posix()
        target = confined(arrival / "original", relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = path.read_bytes()
        with target.open("xb") as stream:
            stream.write(raw)
        target.chmod(
            stat.S_IREAD | (stat.S_IRGRP | stat.S_IROTH if os.name != "nt" else 0)
        )
        files.append(dict(path=relative, bytes=len(raw), sha256=sha(raw)))
    if not files:
        raise ValueError("Empty delivery")
    manifest = signer.sign(
        dict(
            schema="zos-arrival/1",
            arrival_id=arrival.name,
            arrived_at_utc=now(),
            source_description=source_description,
            files=files,
        )
    )
    write_json(arrival / "manifest.json", manifest)
    (arrival / "signer.public.pem").write_bytes(signer.public)
    return arrival, manifest


def verify_arrival(arrival, public_key):
    arrival = private_path(arrival)
    manifest = read_json(arrival / "manifest.json")
    if manifest.get("schema") != "zos-arrival/1" or not verify_envelope(
        manifest, public_key
    ):
        raise ValueError("Arrival signature does not match trusted key")
    expected = {f["path"] for f in manifest["files"]}
    actual = {
        p.relative_to(arrival / "original").as_posix()
        for p in (arrival / "original").rglob("*")
        if p.is_file()
    }
    if actual != expected:
        raise ValueError("Arrival file inventory changed")
    for item in manifest["files"]:
        raw = confined(arrival / "original", item["path"]).read_bytes()
        if len(raw) != item["bytes"] or sha(raw) != item["sha256"]:
            raise ValueError("Original delivery bytes changed")
    return manifest


def load_run(path, public_key):
    path = private_path(path)
    arrival = path.parent.parent
    manifest = verify_arrival(arrival, public_key)
    index = read_json(arrival / "intake.json")
    if (
        not verify_envelope(index, public_key)
        or index["arrival_sha256"] != manifest["content_sha256"]
    ):
        raise ValueError("Intake signature/binding failed")
    run = read_json(path / "run.json")
    if index["runs"].get(path.name) != sha((path / "run.json").read_bytes()):
        raise ValueError("Run index changed")
    return arrival, run
