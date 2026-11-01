#!/usr/bin/env python3
"""verify_public_evidence.py - independent verifier for LIGHTYEAR public evidence.

Recomputes SHA-256 manifests, receipt self-digests, hash chains and Ed25519
signatures (including Control Tower human-decision proof bundles) from the
published bytes alone.  It never imports, executes or trusts Lightyear code,
never contacts the network, and never trusts a public key unless the person
running it pins that key by its SHA-256 fingerprint on the command line.

Requirements: Python 3.11+, standard library, and `cryptography` (tested with
cryptography==50.0.1) for Ed25519.  See README.md.

Exit codes: 0 = every check passed (SKIP/WARN allowed unless --strict),
            1 = at least one FAIL, 2 = usage or input error,
            3 = --strict and something was skipped or only warned.
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import os
import re
import sys
import tarfile
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:  # pragma: no cover - reported at runtime
    serialization = None

VERSION = "1.0.0"
TESTED_CRYPTOGRAPHY = "50.0.1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ZERO = "0" * 64
CHUNK = 1 << 20

# Directories never read by `all`.  `.git` is VCS metadata; the arrivals area
# holds customer/partner intake and is not public evidence, so it is refused
# unconditionally rather than being an overridable default.
ALWAYS_EXCLUDED = ("work/mainframe/arrivals",)
DEFAULT_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar")
MANIFEST_TEXT_NAMES = re.compile(r"^(SHA256SUMS(\..*)?|.*\.sha256(sums)?)$", re.I)
TOWER_EXPORT_TYPES = {"tower-journal-export/1", "control-tower-session-export"}
NON_HUMAN_ACTOR_KINDS = {"agent", "service"}
PATH_KEYS = ("path", "file", "name", "asset_name")
HASH_KEYS = ("sha256", "file_sha256")


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
@dataclass
class Result:
    status: str  # PASS | FAIL | SKIP | WARN
    check: str
    subject: str
    detail: str = ""

    def as_dict(self):
        return {"status": self.status, "check": self.check, "subject": self.subject, "detail": self.detail}


@dataclass
class Report:
    results: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def add(self, status, check, subject, detail=""):
        self.results.append(Result(status, check, str(subject), detail))

    def count(self, status):
        return sum(1 for r in self.results if r.status == status)


class InputError(Exception):
    """Bad command-line input (exit 2)."""


# --------------------------------------------------------------------------
# Hashing and canonical JSON
# --------------------------------------------------------------------------
def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def _reject_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate JSON key {k!r} (ambiguous evidence)")
        out[k] = v
    return out


def _reject_constant(name):
    raise ValueError(f"non-standard JSON constant {name}")


def load_json(path: Path):
    """Strict JSON: UTF-8, no duplicate keys, no NaN/Infinity."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)


def canonical(value, ascii_only: bool) -> bytes:
    """Lightyear canonical JSON: keys sorted by code point, no whitespace,
    UTF-8.  Two escaping variants are in use: raw UTF-8 (Tower) and
    \\uXXXX-escaped ASCII (data contracts).  Identical for ASCII-only data."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=ascii_only, allow_nan=False).encode("utf-8")


# Self-digest rules, tried in order.  Each returns the bytes that were hashed.
DIGEST_RULES = (
    ("excl-content+signature/utf8", ("content_sha256", "signature"), False),
    ("excl-content+signature/ascii", ("content_sha256", "signature"), True),
    ("excl-content/utf8", ("content_sha256",), False),
    ("excl-content/ascii", ("content_sha256",), True),
)


def self_digest(obj: dict):
    """Return (rule_name, hashed_bytes) if obj['content_sha256'] is a
    recomputable self-digest, else (None, None)."""
    claimed = obj.get("content_sha256")
    for name, excluded, ascii_only in DIGEST_RULES:
        body = {k: v for k, v in obj.items() if k not in excluded}
        raw = canonical(body, ascii_only)
        if sha256_bytes(raw) == claimed:
            return name, raw
    return None, None


def signed_bodies(obj: dict):
    """Candidate byte strings an Ed25519 envelope signature covers."""
    body = {k: v for k, v in obj.items() if k not in ("content_sha256", "signature")}
    return [canonical(body, False), canonical(body, True)]


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------
@dataclass
class PinnedKey:
    path: str
    pem_sha256: str  # SHA-256 of the exact PEM file bytes (Lightyear key_id)
    spki_sha256: str  # SHA-256 of the DER SubjectPublicKeyInfo (openssl-style)
    key: object
    matched_on: str


def key_fingerprints(path: Path):
    if serialization is None:
        raise InputError(f"the 'cryptography' package is required (tested: cryptography=={TESTED_CRYPTOGRAPHY})")
    raw = path.read_bytes()
    if b"PRIVATE KEY" in raw:
        raise InputError(f"{path} contains a PRIVATE key; refusing to read it. Supply the public key only.")
    try:
        key = serialization.load_pem_public_key(raw)
    except ValueError as exc:
        raise InputError(f"{path}: not a PEM public key ({exc})") from None
    if not isinstance(key, Ed25519PublicKey):
        raise InputError(f"{path}: not an Ed25519 public key")
    spki = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, sha256_bytes(raw), sha256_bytes(spki)


def normalise_fp(text: str) -> str:
    fp = text.strip().lower().removeprefix("sha256:").replace(":", "")
    if not HEX64.fullmatch(fp):
        raise InputError(f"fingerprint must be the full 64-hex SHA-256, got {text!r} (prefixes are not accepted)")
    return fp


def pin_key(path_text: str, fingerprint: str) -> PinnedKey:
    path = Path(path_text)
    if not path.is_file():
        raise InputError(f"public key file not found: {path}")
    fp = normalise_fp(fingerprint)
    key, pem_fp, spki_fp = key_fingerprints(path)
    if fp == pem_fp:
        matched = "pem-file-sha256"
    elif fp == spki_fp:
        matched = "spki-der-sha256"
    else:
        raise InputError(
            f"public key {path} does NOT match the fingerprint you supplied.\n"
            f"  supplied:            {fp}\n  PEM file SHA-256:    {pem_fp}\n  SPKI DER SHA-256:    {spki_fp}\n"
            "Stop: obtain the correct key and fingerprint out-of-band.")
    return PinnedKey(str(path), pem_fp, spki_fp, key, matched)


def parse_trust_args(values) -> dict:
    ring = {}
    for v in values or []:
        if "=" not in v:
            raise InputError(f"--trust-key expects PEM_PATH=FINGERPRINT, got {v!r}")
        p, fp = v.rsplit("=", 1)
        k = pin_key(p, fp)
        ring[k.pem_sha256] = k
    return ring


def verify_ed25519(obj: dict, keyring: dict, subject: str, report: Report, check: str, required_kid: str | None = None):
    """Verify a Lightyear Ed25519 envelope signature. Returns True/False/None(skipped)."""
    sig = obj.get("signature")
    kid = str(sig.get("key_id", ""))
    if required_kid is not None and kid != required_kid:
        report.add("FAIL", check, subject, f"signed with key_id {kid[:16]}..., not the pinned key {required_kid[:16]}...")
        # still try: a valid signature under the pinned key with a wrong label is reported, never accepted silently
    try:
        sig_bytes = base64.b64decode(str(sig.get("value", "")), validate=True)
    except (ValueError, TypeError):
        report.add("FAIL", check, subject, "signature value is not valid base64")
        return False
    candidates = [keyring[kid]] if kid in keyring else list(keyring.values())
    if not candidates:
        report.add("SKIP", check, subject, f"Ed25519 key {kid[:16]}... is not pinned (use --trust-key PEM=FINGERPRINT)")
        return None
    for pk in candidates:
        for body in signed_bodies(obj):
            try:
                pk.key.verify(sig_bytes, body)
            except InvalidSignature:
                continue
            if required_kid is not None and kid != required_kid:
                return False
            if kid != pk.pem_sha256:
                report.add("WARN", check, subject, f"valid under pinned key {pk.pem_sha256[:16]}... but key_id label is {kid[:16]}...")
                return True
            report.add("PASS", check, subject, f"Ed25519 signature valid, key {kid[:16]}...")
            return True
    if kid in keyring or required_kid is not None:
        report.add("FAIL", check, subject, f"Ed25519 signature INVALID for key {kid[:16]}...")
        return False
    report.add("SKIP", check, subject, f"Ed25519 key {kid[:16]}... is not pinned (use --trust-key PEM=FINGERPRINT)")
    return None


# --------------------------------------------------------------------------
# Paths and archives
# --------------------------------------------------------------------------
def safe_rel(name: str):
    """Return a PurePosixPath for a manifest entry, or None if unsafe."""
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        return None
    p = PurePosixPath(name)
    if p.is_absolute() or re.match(r"^[A-Za-z]:", name) or any(part == ".." for part in p.parts):
        return None
    return p


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def restricted(path: Path) -> bool:
    s = path.resolve().as_posix()
    return any(f"/{r}/" in s + "/" or s.endswith("/" + r) for r in ALWAYS_EXCLUDED)


class ArchiveIndex:
    """Read-only index of regular-file members in sibling archives. Members are
    hashed in memory; nothing is ever extracted to disk."""

    def __init__(self, directory: Path):
        self.archives = []
        for p in sorted(directory.iterdir()) if directory.is_dir() else []:
            if p.is_file() and p.name.lower().endswith(ARCHIVE_SUFFIXES) and not restricted(p):
                try:
                    self.archives.append((p, self._members(p)))
                except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError):
                    continue

    @staticmethod
    def _stem(p: Path) -> str:
        n = p.name
        for s in ARCHIVE_SUFFIXES:
            if n.lower().endswith(s):
                return n[: -len(s)]
        return n

    @staticmethod
    def _members(p: Path) -> set:
        if p.name.lower().endswith(".zip"):
            with zipfile.ZipFile(p) as z:
                return {i.filename for i in z.infolist() if not i.is_dir()}
        with tarfile.open(p) as t:
            return {m.name for m in t.getmembers() if m.isfile()}

    def locate(self, name: str):
        for arch, members in self.archives:
            if name in members:
                return arch, name
            stem = self._stem(arch)
            parts = name.split("/")
            if stem in parts:
                rest = "/".join(parts[parts.index(stem) + 1:])
                if rest in members:
                    return arch, rest
        return None

    @staticmethod
    def hash_member(arch: Path, member: str) -> tuple[str, int]:
        h, n = hashlib.sha256(), 0
        if arch.name.lower().endswith(".zip"):
            with zipfile.ZipFile(arch) as z, z.open(member) as fh:
                while chunk := fh.read(CHUNK):
                    h.update(chunk)
                    n += len(chunk)
        else:
            with tarfile.open(arch) as t:
                fh = t.extractfile(member)
                while chunk := fh.read(CHUNK):
                    h.update(chunk)
                    n += len(chunk)
        return h.hexdigest(), n


def _read_member(arch: Path, member: str) -> bytes:
    if arch.name.lower().endswith(".zip"):
        with zipfile.ZipFile(arch) as z:
            return z.read(member)
    with tarfile.open(arch) as t:
        return t.extractfile(member).read()


# --------------------------------------------------------------------------
# Manifest parsing
# --------------------------------------------------------------------------
@dataclass
class Entry:
    name: str
    sha256: str
    size: int | None = None
    archive_hint: str | None = None  # member of this named sibling archive


def parse_sha256sums(path: Path):
    entries, errors = [], []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if not m:
            errors.append(f"line {n} is not '<sha256>  <name>'")
            continue
        entries.append(Entry(m.group(2), m.group(1).lower()))
    return entries, errors


def _entries_from_list(items, name_keys=("path", "name", "file"), hash_keys=HASH_KEYS):
    out = []
    for it in items:
        if not isinstance(it, dict):
            return None
        n = next((it[k] for k in name_keys if isinstance(it.get(k), str)), None)
        h = next((it[k] for k in hash_keys if isinstance(it.get(k), str) and HEX64.fullmatch(it[k])), None)
        if n is None or h is None:
            return None
        size = it.get("bytes", it.get("size", it.get("size_in_bytes")))
        out.append(Entry(n, h, size if isinstance(size, int) else None))
    return out


def manifest_entries(doc):
    """Recognise the manifest shapes Lightyear publishes. Returns (kind, entries)
    or (None, None) when the JSON is not a manifest."""
    if not isinstance(doc, dict):
        return None, None
    if isinstance(doc.get("assets"), list) and doc["assets"]:
        e = _entries_from_list(doc["assets"], ("name",))
        if e:
            return "release-assets (" + str(doc.get("schema", "assets[]")) + ")", e
    for key in ("files", "metadata_files"):
        v = doc.get(key)
        if isinstance(v, dict) and v and all(isinstance(h, str) and HEX64.fullmatch(h) for h in v.values()):
            return f"{key}{{path: sha256}}", [Entry(k, h) for k, h in v.items()]
        if isinstance(v, list) and v:
            e = _entries_from_list(v)
            if e:
                return f"{key}[{{path, sha256}}]", e
    if isinstance(doc.get("members"), list) and doc["members"]:
        e = _entries_from_list(doc["members"], ("name", "path"))
        arch = (doc.get("release") or {}).get("asset_name") if isinstance(doc.get("release"), dict) else None
        if e:
            for x in e:
                x.archive_hint = arch
            return "archive-members", e
    if doc and all(isinstance(h, str) and HEX64.fullmatch(h) for h in doc.values()) and all(
            safe_rel(k) is not None and ("." in k or "/" in k) for k in doc):
        return "flat {path: sha256}", [Entry(k, h) for k, h in doc.items()]
    return None, None


def archive_binding(doc, directory: Path):
    """Archive self-bindings inside provenance/publication records."""
    out = []
    if not isinstance(doc, dict):
        return out
    rel = doc.get("release") if isinstance(doc.get("release"), dict) else {}
    if isinstance(doc.get("archive_sha256"), str) and HEX64.fullmatch(doc["archive_sha256"]) and rel.get("asset_name"):
        size = doc.get("archive_bytes", doc.get("size_in_bytes"))
        out.append(Entry(rel["asset_name"], doc["archive_sha256"], size if isinstance(size, int) else None))
    arc = doc.get("archive")
    if isinstance(arc, dict) and isinstance(arc.get("sha256"), str) and HEX64.fullmatch(arc["sha256"]) and isinstance(arc.get("url"), str):
        out.append(Entry(arc["url"].rsplit("/", 1)[-1], arc["sha256"], arc.get("bytes") if isinstance(arc.get("bytes"), int) else None))
    return out


def resolve_entries(entries, manifest_path: Path, target: Path, search_up: int = 8):
    """Resolve entries to files inside `target` (choosing the base directory
    that resolves most entries), falling back to sibling-archive members.
    Returns list of (entry, kind, location) with kind in file|member|missing|unsafe."""
    bases, b = [], target
    for _ in range(search_up + 1):
        bases.append(b)
        if b.parent == b:
            break
        b = b.parent
    if manifest_path.parent not in bases:
        bases.insert(0, manifest_path.parent)

    def hit(base, e):
        rel = safe_rel(e.name)
        if rel is None:
            return None
        p = base.joinpath(*rel.parts)
        return p if p.is_file() and is_within(p, target) and not restricted(p) else None

    best = max(bases, key=lambda base: (sum(1 for e in entries if hit(base, e)), -bases.index(base)))
    archives = None
    out = []
    for e in entries:
        if safe_rel(e.name) is None:
            out.append((e, "unsafe", None))
            continue
        p = hit(best, e)
        if p:
            out.append((e, "file", p))
            continue
        if archives is None:
            archives = ArchiveIndex(target)
        loc = None
        if e.archive_hint:
            for arch, members in archives.archives:
                if arch.name == e.archive_hint and e.name in members:
                    loc = (arch, e.name)
        loc = loc or archives.locate(e.name)
        out.append((e, "member", loc) if loc else (e, "missing", None))
    return out


def canonical_json_digests(read):
    """SHA-256 of the canonical-JSON form of a JSON file (some Lightyear
    references pin the parsed JSON value rather than the raw bytes)."""
    try:
        raw = read()
        if len(raw) > 64 << 20:
            return set()
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError):
        return set()
    return {sha256_bytes(canonical(value, False)), sha256_bytes(canonical(value, True))}


def check_entries(resolved, report: Report, subject: str, missing_status: str = "FAIL",
                  allow_canonical: bool = False, mismatch_status: str = "FAIL"):
    """Hash every resolved entry. Returns (passed, failed, missing, covered_files)."""
    ok = bad = miss = 0
    covered = set()
    for e, kind, loc in resolved:
        label = f"{subject} :: {e.name}"
        if kind == "unsafe":
            report.add("FAIL", "manifest-path", label, "unsafe path (absolute, '..' or backslash)")
            bad += 1
            continue
        if kind == "missing":
            report.add(missing_status, "manifest-missing", label, "listed file not present")
            miss += 1
            continue
        if kind == "file":
            digest, size = sha256_file(loc)
            covered.add(loc.resolve())
            where = ""
        else:
            arch, member = loc
            digest, size = ArchiveIndex.hash_member(arch, member)
            where = f" (member of {arch.name})"
        if digest != e.sha256 and allow_canonical and e.name.lower().endswith(".json"):
            read = (lambda: loc.read_bytes()) if kind == "file" else (lambda: _read_member(*loc))
            if e.sha256 in canonical_json_digests(read):
                report.add("PASS", "manifest-sha256", label, f"sha256 {e.sha256[:16]}... of canonical JSON{where}")
                ok += 1
                continue
        if digest != e.sha256:
            report.add(mismatch_status, "manifest-sha256", label, f"SHA-256 mismatch{where}: expected {e.sha256[:16]}..., got {digest[:16]}...")
            bad += 1
        elif e.size is not None and e.size != size:
            report.add("FAIL", "manifest-size", label, f"size mismatch{where}: expected {e.size}, got {size}")
            bad += 1
        else:
            report.add("PASS", "manifest-sha256", label, f"sha256 {digest[:16]}...{where}")
            ok += 1
    return ok, bad, miss, covered


# --------------------------------------------------------------------------
# Receipts: self-digests, signatures, chains, file references
# --------------------------------------------------------------------------
def iter_dicts(obj, path="$"):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from iter_dicts(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_dicts(v, f"{path}[{i}]")


def iter_lists(obj, path="$", parent=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list):
                yield f"{path}.{k}", v, obj
            yield from iter_lists(v, f"{path}.{k}", obj)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_lists(v, f"{path}[{i}]", obj)


def is_chain(lst) -> bool:
    return bool(lst) and all(
        isinstance(e, dict) and isinstance(e.get("content_sha256"), str)
        and ("previous_sha256" in e or "previous_event_sha256" in e) for e in lst)


def check_chain(lst, parent, label, report: Report):
    """Hash-chain rule: each element's previous_sha256 equals the previous
    element's content_sha256; the first is null or 64 zeros; sequence counts
    1..n; elements may be interleaved journals keyed by journal_id."""
    prev_key = "previous_sha256" if "previous_sha256" in lst[0] else "previous_event_sha256"
    groups = {}
    for e in lst:
        jid = e.get("journal_id")
        if jid is None and isinstance(e.get("payload"), dict):
            jid = e["payload"].get("journal_id")
        groups.setdefault(jid, []).append(e)
    failures = []
    for jid, events in groups.items():
        previous = None
        for i, e in enumerate(events, 1):
            where = f"journal {jid!r} " if jid is not None else ""
            if "sequence" in e and e["sequence"] != i:
                failures.append(f"{where}element {i} has sequence {e['sequence']}")
            want = (None, ZERO) if previous is None else (previous,)
            if e.get(prev_key) not in want:
                failures.append(f"{where}element {i} previous link {str(e.get(prev_key))[:16]}... does not match predecessor")
            p = e.get("payload")
            if isinstance(p, dict) and "previous_event_sha256" in p and p["previous_event_sha256"] != e.get(prev_key):
                failures.append(f"{where}element {i} signed payload links to a different predecessor")
            if isinstance(p, dict) and "event_type" in p and "type" in e and p["event_type"] != e["type"]:
                failures.append(f"{where}element {i} type differs from signed payload")
            previous = e["content_sha256"]
    head = parent.get("journal_head_sha256") if isinstance(parent, dict) else None
    if isinstance(head, str) and len(groups) == 1 and head != lst[-1]["content_sha256"]:
        failures.append(f"journal_head_sha256 {head[:16]}... is not the last element")
    if failures:
        report.add("FAIL", "chain", label, "; ".join(failures[:5]) + (f" (+{len(failures) - 5} more)" if len(failures) > 5 else ""))
        return False
    report.add("PASS", "chain", label, f"{len(lst)} links in {len(groups)} journal(s), head {lst[-1]['content_sha256'][:16]}...")
    return True


def file_references(doc, manifest_keys=()):
    """Every {path|file|name, sha256|file_sha256} object outside manifest lists."""
    refs = []
    skip_ids = {id(doc.get(k)) for k in manifest_keys} if isinstance(doc, dict) else set()

    def walk(o):
        if id(o) in skip_ids:
            return
        if isinstance(o, dict):
            n = next((o[k] for k in PATH_KEYS if isinstance(o.get(k), str)), None)
            h = next((o[k] for k in HASH_KEYS if isinstance(o.get(k), str) and HEX64.fullmatch(o[k])), None)
            if n and h and safe_rel(n) is not None and ("." in n or "/" in n):
                size = o.get("bytes", o.get("size"))
                refs.append(Entry(n, h, size if isinstance(size, int) else None))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(doc)
    return refs


def check_document(doc, label: str, keyring: dict, report: Report, *, explicit: bool):
    """Self-digests, signatures and chains inside one JSON document."""
    stats = {"digest": 0, "sig": 0, "chain": 0}
    chain_members = set()
    for lpath, lst, parent in iter_lists(doc):
        if is_chain(lst):
            for e in lst:
                chain_members.add(id(e))
            stats["chain"] += 1
            check_chain(lst, parent, f"{label} {lpath}", report)
    for dpath, obj in iter_dicts(doc):
        sig = obj.get("signature")
        signed = isinstance(sig, dict) and isinstance(sig.get("algorithm"), str)
        claimed = obj.get("content_sha256")
        sub = f"{label} {dpath}"
        if isinstance(claimed, str) and HEX64.fullmatch(claimed):
            rule, _ = self_digest(obj)
            if rule:
                stats["digest"] += 1
                report.add("PASS", "self-digest", sub, f"content_sha256 recomputed ({rule})")
            elif signed or id(obj) in chain_members:
                report.add("FAIL", "self-digest", sub, f"content_sha256 {claimed[:16]}... does NOT match the recomputed digest")
            elif obj is doc:
                report.add("FAIL" if explicit else "WARN", "self-digest", sub,
                           "root content_sha256 is not a self-digest under any known rule (it may identify other content, or the file was altered); not verified")
            # nested, unsigned, non-chain: a reference to other content, not a seal
        if signed:
            alg = sig["algorithm"]
            if alg == "Ed25519":
                stats["sig"] += 1
                verify_ed25519(obj, keyring, sub, report, "signature")
            elif alg.lower().startswith("hmac"):
                report.add("SKIP", "signature", sub, f"{alg} is a shared-secret MAC; it cannot be verified without Lightyear's private secret")
            else:
                report.add("SKIP", "signature", sub, f"unsupported signature algorithm {alg!r} (key_id {sig.get('key_id')})")
    return stats


def check_references(doc, path: Path, report: Report, label: str, base: Path | None, manifest_keys=()):
    refs = file_references(doc, manifest_keys)
    if not refs:
        return
    # Without --base, only files in the receipt's own directory (or inside a
    # sibling archive) are compared: repository paths elsewhere may legitimately
    # have changed since the receipt pinned a historical version.
    target = base or path.parent
    resolved = resolve_entries(refs, path, target, search_up=0 if base is None else 8)
    present = [r for r in resolved if r[1] in ("file", "member")]
    absent = len(resolved) - len(present)
    sub = Report()
    ok, bad, _, _ = check_entries(present, sub, f"{label} ref", allow_canonical=True)
    report.results.extend(r for r in sub.results if r.status != "PASS")
    if present:
        report.add("PASS" if not bad else "FAIL", "references", label,
                   f"{ok}/{len(present)} referenced files present here match their recorded SHA-256")
    if absent:
        report.add("SKIP", "references", label,
                   f"{absent} referenced file(s) not present in this directory (external or historical; not checked)")


def check_sibling_bindings(doc, path: Path, report: Report, label: str):
    """Run-export bindings between sibling files (paired-campaign exports):
    authorization_sha256 -> authorization.json content_sha256, and
    journal_head_sha256 -> the last event of journal.json.  Other `*_sha256`
    names are not checked: in Lightyear evidence they often pin an earlier
    or differently-shaped object, so a name match is not a binding."""
    if not isinstance(doc, dict):
        return
    for key, value in doc.items():
        if key not in ("authorization_sha256", "journal_head_sha256") or not (isinstance(value, str) and HEX64.fullmatch(value)):
            continue
        stem = key[: -len("_sha256")]
        if stem == "journal_head":
            sib = path.parent / "journal.json"
            if not sib.is_file() or sib == path:
                continue
            try:
                events = load_json(sib).get("events")
            except (ValueError, AttributeError, UnicodeDecodeError):
                continue
            if isinstance(events, list) and events and isinstance(events[-1], dict):
                last = events[-1].get("content_sha256")
                report.add("PASS" if last == value else "FAIL", "binding", f"{label} {key}",
                           "equals the last event of journal.json" if last == value else
                           f"journal.json ends at {str(last)[:16]}..., not {value[:16]}...")
            continue
        sib = path.parent / f"{stem}.json"
        if not sib.is_file() or sib == path:
            continue
        raw = sib.read_bytes()
        candidates = {sha256_bytes(raw)} | canonical_json_digests(lambda: raw)
        try:
            other = load_json(sib)
            if isinstance(other, dict) and isinstance(other.get("content_sha256"), str):
                candidates.add(other["content_sha256"])
        except (ValueError, UnicodeDecodeError):
            pass
        ok = value in candidates
        report.add("PASS" if ok else "FAIL", "binding", f"{label} {key}",
                   f"binds sibling {sib.name}" if ok else f"does not match sibling {sib.name} (file, canonical or content_sha256)")


# --------------------------------------------------------------------------
# Tower decision proofs
# --------------------------------------------------------------------------
def check_decision(proof, label: str, report: Report, pinned: PinnedKey | None, *,
                   expected_head=None, expected_decision=None, expected_bound=None, today=None):
    """Verify a tower-decision-proof/1 bundle from its bytes alone."""
    def fail(check, detail):
        report.add("FAIL", check, label, detail)

    if not isinstance(proof, dict) or proof.get("schema") != "tower-decision-proof/1":
        fail("decision-schema", "not a tower-decision-proof/1 bundle")
        return
    dsha = proof.get("decision_sha256")
    if not (isinstance(dsha, str) and HEX64.fullmatch(dsha)):
        fail("decision-schema", "decision_sha256 missing or not 64 hex")
        return
    if expected_decision and dsha != expected_decision:
        fail("decision-expected", f"bundle is for decision {dsha[:16]}..., you asked for {expected_decision[:16]}...")
    export = proof.get("journal")
    if not isinstance(export, dict) or not isinstance(export.get("events"), list):
        fail("journal", "journal.events missing")
        return
    if export.get("record_type") not in TOWER_EXPORT_TYPES:
        fail("journal", f"unexpected journal record_type {export.get('record_type')!r}")
    kid = pinned.pem_sha256 if pinned else None
    ring = {pinned.pem_sha256: pinned} if pinned else {}

    def envelope(obj, sub):
        rule, _ = self_digest(obj)
        if rule is None or not rule.startswith("excl-content+signature"):
            report.add("FAIL", "self-digest", sub, "content_sha256 does NOT match the recomputed digest")
            ok = False
        else:
            report.add("PASS", "self-digest", sub, f"content_sha256 recomputed ({rule})")
            ok = True
        sig = obj.get("signature")
        if not (isinstance(sig, dict) and sig.get("algorithm") == "Ed25519"):
            report.add("FAIL", "signature", sub, "missing Ed25519 signature")
            return False
        res = verify_ed25519(obj, ring, sub, report, "signature", required_kid=kid)
        return ok and res is not False

    envelope(export, f"{label} journal-export")
    events = export["events"]
    previous, chain_err = ZERO, []
    for i, ev in enumerate(events, 1):
        if not isinstance(ev, dict):
            chain_err.append(f"event {i} is not an object")
            continue
        envelope(ev, f"{label} event {i}")
        if ev.get("sequence") != i:
            chain_err.append(f"event {i} has sequence {ev.get('sequence')}")
        if ev.get("previous_sha256") != previous:
            chain_err.append(f"event {i} previous_sha256 does not equal event {i - 1} content_sha256")
        previous = ev.get("content_sha256")
    # Collapse per-event PASS lines into one; keep FAIL/SKIP detail.
    per_event = [r for r in report.results if r.subject.startswith(f"{label} event ")]
    report.results = [r for r in report.results if not (r.subject.startswith(f"{label} event ") and r.status == "PASS")]
    passes = sum(1 for r in per_event if r.status == "PASS" and r.check == "signature")
    digests = sum(1 for r in per_event if r.status == "PASS" and r.check == "self-digest")
    if events and passes == len(events) and digests == len(events):
        report.add("PASS", "event-signatures", label, f"all {len(events)} journal events: digest recomputed and Ed25519 signature valid")
    elif events and digests == len(events):
        report.add("PASS", "event-digests", label, f"all {len(events)} journal events: content_sha256 recomputed (signatures reported separately)")
    if chain_err:
        fail("chain", "; ".join(chain_err[:4]))
    else:
        report.add("PASS", "chain", label, f"{len(events)} events chained from zero hash; sequence 1..{len(events)}")
    head = export.get("journal_head_sha256")
    if head != (previous if events else ZERO):
        fail("journal-head", f"journal_head_sha256 {str(head)[:16]}... is not the last event")
    else:
        report.add("PASS", "journal-head", label, f"head {str(head)[:16]}... = last event")
    if expected_head:
        if head != expected_head:
            fail("journal-head-expected", f"head {str(head)[:16]}... differs from the head you pinned {expected_head[:16]}...")
        else:
            report.add("PASS", "journal-head-expected", label, "matches the independently obtained journal head")
    matches = [e for e in events if isinstance(e, dict) and e.get("content_sha256") == dsha]
    if len(matches) != 1 or matches[0].get("kind") != "tower_decision":
        fail("decision-in-journal", "decision_sha256 is not exactly one tower_decision event in the journal")
        return
    ev = matches[0]
    rule, _ = self_digest(ev)
    if rule:
        report.add("PASS", "decision-sha256", label, f"recomputed decision_sha256 {dsha[:16]}... from the decision event")
    p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
    problems = []
    if p.get("schema") != "tower-decision/1":
        problems.append("payload schema is not tower-decision/1")
    if p.get("scope") != export.get("scope"):
        problems.append("decision scope differs from journal scope")
    if p.get("actor") != ev.get("actor") or p.get("session_id") != ev.get("session_id"):
        problems.append("payload actor/session differs from the signed event actor/session")
    actor = p.get("actor") if isinstance(p.get("actor"), dict) else {}
    if actor.get("kind") in NON_HUMAN_ACTOR_KINDS:
        problems.append(f"decider kind is {actor.get('kind')!r}, not a human operator")
    if p.get("channel") not in (None, "control-tower"):
        problems.append(f"channel {p.get('channel')!r} is not control-tower")
    if expected_bound:
        bound = p.get("bound") if isinstance(p.get("bound"), dict) else {}
        for k, v in expected_bound.items():
            if bound.get(k) != v:
                problems.append(f"bound.{k} is {str(bound.get(k))[:16]}..., expected {v[:16]}...")
    later = [e for e in events[ev.get("sequence", 0):] if isinstance(e, dict) and e.get("kind") == "tower_decision"
             and isinstance(e.get("payload"), dict) and e["payload"].get("kind") == p.get("kind")
             and e["payload"].get("bound") == p.get("bound") and e["payload"].get("decision_slot") == p.get("decision_slot")]
    if later:
        problems.append(f"superseded by a later {p.get('kind')} decision on the same subject (event {later[0].get('sequence')})")
    if problems:
        fail("decision-semantics", "; ".join(problems))
    else:
        report.add("PASS", "decision-semantics", label,
                   f"kind={p.get('kind')} outcome={p.get('outcome')} recorded for {actor.get('kind')} "
                   f"{actor.get('name') or actor.get('id')!r} at {ev.get('occurred_at')}; scope={p.get('scope')}; not superseded")
        reason = str(p.get("reason", ""))
        report.add("PASS", "decision-record", label,
                   f"reason: {reason[:110]!r}; authentication: {p.get('authentication')}; "
                   f"signature: {export.get('signature_type') or 'Tower service signature'}")
        report.notes.append("The Ed25519 signature is the Tower SERVICE key countersigning what an authenticated "
                            "session did. The actor name/kind inside is recorded by Tower, not a personal signature.")
    ra = p.get("review_after")
    if isinstance(ra, str):
        try:
            if date.fromisoformat(ra[:10]) <= (today or datetime.now(timezone.utc).date()):
                report.add("WARN", "decision-expiry", label, f"review_after {ra} has passed: proves the historical decision, not current authority")
        except ValueError:
            pass
    report.notes.append("A journal export proves the decision existed at its signed head. Whether that head is "
                        "still current must be confirmed out-of-band (--expected-head).")


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def load_manifest_file(path: Path):
    if MANIFEST_TEXT_NAMES.match(path.name):
        entries, errors = parse_sha256sums(path)
        return "SHA256SUMS", entries, errors
    try:
        doc = load_json(path)
    except (ValueError, UnicodeDecodeError) as exc:
        return None, None, [f"unreadable JSON: {exc}"]
    kind, entries = manifest_entries(doc)
    if kind is None:
        return None, None, []
    return kind, entries + archive_binding(doc, path.parent), []


def discover_manifests(directory: Path):
    found = []
    for p in sorted(directory.iterdir()):
        if not p.is_file():
            continue
        if MANIFEST_TEXT_NAMES.match(p.name) or p.suffix.lower() == ".json":
            kind, entries, _ = load_manifest_file(p)
            if kind:
                found.append(p)
    return found


def cmd_manifest(args, report: Report):
    target = Path(args.directory)
    if not target.is_dir():
        raise InputError(f"not a directory: {target}")
    manifests = [Path(m) for m in args.manifest] if args.manifest else discover_manifests(target)
    if not manifests:
        raise InputError(f"no SHA-256 manifest found in {target}; name one with --manifest")
    covered, manifest_files, verified = set(), {}, {}
    for m in manifests:
        if not m.is_file():
            raise InputError(f"manifest not found: {m}")
        kind, entries, errors = load_manifest_file(m)
        for e in errors:
            report.add("FAIL", "manifest-format", m, e)
        if not kind:
            report.add("FAIL", "manifest-format", m, "not a recognised SHA-256 manifest")
            continue
        resolved = resolve_entries(entries, m, target)
        if not args.manifest and not any(k in ("file", "member", "unsafe") for _, k, _ in resolved):
            report.add("SKIP", "manifest", m, f"{kind}: none of its {len(entries)} entries are in this directory "
                       "(it describes files published elsewhere); name it with --manifest to require them")
            continue
        manifest_files[m.resolve()] = m.name
        report.add("PASS", "manifest-format", m, f"{kind}: {len(entries)} entries")
        sub = Report()
        ok, bad, miss, cov = check_entries(resolved, sub, m.name)
        report.results.extend(sub.results)
        covered |= cov
        for r in sub.results:
            if r.status == "PASS" and r.check == "manifest-sha256":
                verified.setdefault(r.detail.split()[1].rstrip("."), r.subject)
    pinned_manifests = {sha256_file(Path(mp))[0]: name for mp, name in manifest_files.items()}
    # Extra files: present in the directory tree but listed by no manifest.
    for p in sorted(target.rglob("*")):
        if not p.is_file() or any(part in DEFAULT_SKIP_DIRS for part in p.relative_to(target).parts) or restricted(p):
            continue
        rp = p.resolve()
        if rp in covered or rp in manifest_files:
            continue
        rel = p.relative_to(target).as_posix()
        digest, _ = sha256_file(p)
        if digest in pinned_manifests:
            report.add("PASS", "manifest-extra", rel, f"byte-identical copy of the manifest {pinned_manifests[digest]}")
            continue
        if digest[:16] in verified:
            report.add("PASS", "manifest-extra", rel, f"not listed by name, but byte-identical to verified entry {verified[digest[:16]]}")
            continue
        anchors = []
        if p.suffix.lower() == ".json" and p.stat().st_size < 4 << 20:
            text = p.read_text(encoding="utf-8", errors="replace")
            anchors = [name for h, name in pinned_manifests.items() if h in text]
        if any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(p.name, g) for g in args.allow_extra or []):
            report.add("WARN", "manifest-extra", rel, "not listed in any manifest (allowed by --allow-extra)")
        elif anchors:
            report.add("WARN", "manifest-extra", rel, f"not covered by a manifest; it records the SHA-256 of {', '.join(anchors)} "
                       "(consistent), but its own contents are unattested")
        else:
            report.add("FAIL", "manifest-extra", rel, "file present but not listed in any manifest")


def cmd_receipt(args, report: Report):
    keyring = parse_trust_args(args.trust_key)
    for f in args.files:
        path = Path(f)
        try:
            doc = load_json(path)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            report.add("FAIL", "json", path, f"cannot parse: {exc}")
            continue
        label = path.name if len(args.files) == 1 else str(path)
        if isinstance(doc, dict) and doc.get("schema") == "tower-decision-proof/1":
            report.notes.append(f"{path} is a Tower decision proof; use the `decision` command to check its human decision.")
        schema = doc.get("schema") or doc.get("record_type") or doc.get("receipt_type") or doc.get("artifact_type") if isinstance(doc, dict) else None
        report.add("PASS", "json", label, f"strict JSON parsed (format: {schema or 'unlabelled'})")
        stats = check_document(doc, label, keyring, report, explicit=True)
        mkind, _ = manifest_entries(doc)
        check_sibling_bindings(doc, path, report, label)
        check_references(doc, path, report, label, Path(args.base) if args.base else None,
                         manifest_keys=("assets", "files", "metadata_files", "members") if mkind else ())
        if not any(stats.values()) and not any(r.check == "references" for r in report.results):
            report.add("WARN", "receipt", label, "no self-digest, signature, chain or file reference found to verify")


def cmd_decision(args, report: Report):
    pinned = pin_key(args.public_key, args.key_sha256)
    report.add("PASS", "key-pin", pinned.path,
               f"public key matches your fingerprint ({pinned.matched_on}); PEM sha256 {pinned.pem_sha256[:16]}..., SPKI sha256 {pinned.spki_sha256[:16]}...")
    expected_bound = {}
    for b in args.expect_bound or []:
        k, _, v = b.partition("=")
        expected_bound[k] = normalise_fp(v)
    for f in args.files:
        path = Path(f)
        try:
            proof = load_json(path)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            report.add("FAIL", "json", path, f"cannot parse: {exc}")
            continue
        check_decision(proof, path.name if len(args.files) == 1 else str(path), report, pinned,
                       expected_head=normalise_fp(args.expected_head) if args.expected_head else None,
                       expected_decision=normalise_fp(args.decision_sha256) if args.decision_sha256 else None,
                       expected_bound=expected_bound or None)


def walk_files(root: Path, excludes):
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        rel_d = d.relative_to(root).as_posix()
        keep = []
        for n in sorted(dirnames):
            rel = f"{rel_d}/{n}" if rel_d != "." else n
            if n in DEFAULT_SKIP_DIRS or restricted(d / n) or any(fnmatch.fnmatch(rel, g) for g in excludes):
                continue
            keep.append(n)
        dirnames[:] = keep
        for n in sorted(filenames):
            rel = f"{rel_d}/{n}" if rel_d != "." else n
            if not any(fnmatch.fnmatch(rel, g) for g in excludes):
                yield d / n, rel


LINK_RE = re.compile(r"(?:\]\(|href=\")([^)\"\s]+)#sha256=([0-9a-f]{64})[)\"]")


def cmd_all(args, report: Report):
    root = Path(args.directory)
    if not root.is_dir():
        raise InputError(f"not a directory: {root}")
    keyring = parse_trust_args(args.trust_key)
    tally, found_keys = {}, {}
    counts = {"json": 0, "manifests": 0, "proofs": 0, "md-links": 0, "pem": 0}
    for path, rel in walk_files(root, args.exclude or []):
        name = path.name.lower()
        if name.endswith(".pem"):
            counts["pem"] += 1
            try:
                _, pem_fp, _ = key_fingerprints(path)
                found_keys.setdefault(pem_fp, []).append(rel)
            except InputError as exc:
                report.notes.append(f"{rel}: {exc}")
            continue
        if name.endswith(".md"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for target, want in LINK_RE.findall(text):
                rel_t = safe_rel(target.split("?")[0])
                p = path.parent.joinpath(*rel_t.parts) if rel_t else None
                if p is None or not p.is_file() or not is_within(p, root):
                    report.add("SKIP", "md-link", rel, f"{target} not present under the walked directory")
                    continue
                counts["md-links"] += 1
                got, _ = sha256_file(p)
                report.add("PASS" if got == want else "FAIL", "md-link", f"{rel} -> {target}",
                           "linked file matches #sha256 in the document" if got == want else
                           f"linked file SHA-256 {got[:16]}... differs from #sha256={want[:16]}...")
            continue
        is_text_manifest = MANIFEST_TEXT_NAMES.match(path.name)
        if not (name.endswith(".json") or is_text_manifest):
            continue
        if is_text_manifest:
            doc, mkind = None, "SHA256SUMS"
        else:
            counts["json"] += 1
            try:
                doc = load_json(path)
            except (ValueError, UnicodeDecodeError) as exc:
                report.add("FAIL", "json", rel, f"cannot parse strictly: {exc}")
                continue
            mkind, _ = manifest_entries(doc)
        if mkind:
            kind, entries, errors = load_manifest_file(path)
            for e in errors:
                report.add("FAIL", "manifest-format", rel, e)
            resolved = resolve_entries(entries, path, path.parent)
            for e, k, _ in resolved:
                if k == "unsafe":
                    report.add("FAIL", "manifest-path", f"{rel} :: {e.name}", "unsafe path (absolute, '..' or backslash)")
            present = [r for r in resolved if r[1] in ("file", "member")]
            if not present:
                report.add("SKIP", "manifest", rel, f"{kind}: none of {len(entries)} listed files are here "
                           "(e.g. Release assets) - download them and run `manifest`")
            elif len(present) == len(resolved):
                counts["manifests"] += 1
                sub = Report()
                ok, bad, miss, _ = check_entries(resolved, sub, rel)
                report.results.extend(r for r in sub.results if r.status != "PASS")
                report.add("PASS" if not bad else "FAIL", "manifest", rel,
                           f"{kind}: {ok}/{len(entries)} entries verified" + (f", {bad} failed" if bad else ""))
            else:
                # Only some listed files are here: the manifest describes a set
                # published elsewhere (CI artifact / Release) or a historical
                # snapshot.  Present files are compared, but a difference is a
                # WARN, because a live file may legitimately have moved on.
                sub = Report()
                ok, bad, _, _ = check_entries(present, sub, rel, mismatch_status="WARN")
                report.results.extend(r for r in sub.results if r.status not in ("PASS",))
                report.add("SKIP", "manifest", rel, f"{kind}: only {len(present)} of {len(entries)} listed files are here "
                           f"({ok} match, {bad} differ); download the full set and run `manifest`")
        if doc is None:
            continue
        if isinstance(doc, dict) and doc.get("schema") == "tower-decision-proof/1":
            counts["proofs"] += 1
            sub = Report()
            exp_sig = (doc.get("journal") or {}).get("signature") if isinstance(doc.get("journal"), dict) else None
            kid = exp_sig.get("key_id") if isinstance(exp_sig, dict) else None
            check_decision(doc, rel, sub, keyring.get(kid))
            # Without a pinned key the signature lines are SKIPs; collapse them.
            skips = [r for r in sub.results if r.status == "SKIP"]
            report.results.extend(r for r in sub.results if r.status != "SKIP")
            if skips:
                report.add("SKIP", "signature", rel, f"{len(skips)} Tower signatures not checked: run `decision` with the pinned Tower key")
            continue
        sub = Report()
        check_document(doc, rel, keyring, sub, explicit=False)
        check_sibling_bindings(doc, path, sub, rel)
        check_references(doc, path, sub, rel, None,
                         manifest_keys=("assets", "files", "metadata_files", "members") if mkind else ())
        for r in sub.results:
            if r.status == "PASS":
                tally[r.check] = tally.get(r.check, 0) + 1
                if r.check == "signature":
                    k = r.detail.rsplit("key ", 1)[-1]
                    tally["sig:" + k] = tally.get("sig:" + k, 0) + 1
        fails = [r for r in sub.results if r.status in ("FAIL", "WARN")]
        report.results.extend(fails)
        n = {s: sub.count(s) for s in ("PASS", "SKIP")}
        if n["PASS"]:
            report.add("PASS", "receipt", rel, f"{n['PASS']} digest/signature/chain/reference checks passed")
        if n["SKIP"]:
            reasons = sorted({r.detail.split(" (")[0][:70] for r in sub.results if r.status == "SKIP"})
            report.add("SKIP", "receipt", rel, f"{n['SKIP']} checks skipped: " + "; ".join(reasons[:2]))
    report.notes.insert(0, f"walked {root}: {counts['json']} JSON files, {counts['manifests']} complete manifests, "
                        f"{counts['proofs']} Tower decision proofs, {counts['md-links']} #sha256 document links, {counts['pem']} PEM files")
    report.notes.insert(1, f"inside receipts: {tally.get('self-digest', 0)} self-digests recomputed, {tally.get('signature', 0)} Ed25519 "
                        f"signatures verified, {tally.get('chain', 0)} hash chains, {tally.get('binding', 0)} sibling bindings, "
                        f"{tally.get('references', 0)} documents whose local file references all match")
    for fp, paths in sorted(found_keys.items(), key=lambda kv: kv[1][0]):
        pinned = "PINNED by you" if fp in keyring else "not trusted (not pinned)"
        report.notes.append(f"public key {fp[:16]}... in {len(paths)} file(s), e.g. {paths[0]}: {pinned}")
    for k in sorted(x for x in tally if x.startswith("sig:")):
        report.notes.insert(2, f"  {tally[k]} signatures verified under pinned key {k[4:]}")


def cmd_keyinfo(args, report: Report):
    for f in args.files:
        key, pem_fp, spki_fp = key_fingerprints(Path(f))
        raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        report.add("PASS", "key", f, f"Ed25519 public key; PEM-file sha256 {pem_fp}; SPKI-DER sha256 {spki_fp}; raw {raw.hex()}")


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def render(results, *, verbose: bool, quiet: bool, collapse_over: int = 8):
    """Text lines. Without --verbose, runs of more than `collapse_over` PASS
    lines for the same check and document are folded into one count line;
    every FAIL, SKIP and WARN is always printed individually."""
    def fmt(r):
        return f"{r.status:<4}  {r.check:<20} {r.subject}" + (f"  -- {r.detail}" if r.detail else "")
    if verbose:
        return [fmt(r) for r in results]
    groups, order = {}, []
    for i, r in enumerate(results):
        if r.status == "PASS":
            key = (r.check, r.subject.split(" ")[0])
            if key not in groups:
                groups[key] = []
                order.append(("g", key))
            groups[key].append(r)
        else:
            order.append(("r", r))
    lines = []
    for kind, item in order:
        if kind == "r":
            lines.append(fmt(item))
        elif not quiet:
            rs = groups[item]
            if len(rs) > collapse_over:
                lines.append(f"PASS  {item[0]:<20} {item[1]}  -- {len(rs)} checks passed (use -v to list each)")
            else:
                lines.extend(fmt(r) for r in rs)
    return lines


def emit(report: Report, args, command: str):
    fails, skips, warns, passes = (report.count(s) for s in ("FAIL", "SKIP", "WARN", "PASS"))
    verdict = "FAIL" if fails else ("INCOMPLETE" if args.strict and (skips or warns) else "PASS")
    if args.json:
        json.dump({"tool": "lightyear_verify", "version": VERSION, "command": command, "verdict": verdict,
                   "summary": {"pass": passes, "fail": fails, "skip": skips, "warn": warns},
                   "results": [r.as_dict() for r in report.results], "notes": report.notes}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for line in render(report.results, verbose=args.verbose, quiet=args.quiet):
            print(line)
        for n in report.notes:
            print(f"NOTE  {n}")
        print("-" * 72)
        print(f"SUMMARY  {passes} passed, {fails} failed, {skips} skipped, {warns} warnings")
        print(f"VERDICT  {verdict}" + ("" if verdict == "PASS" else
              " (one or more checks FAILED)" if verdict == "FAIL" else " (--strict: some checks could not be performed)"))
    return 1 if fails else (3 if verdict == "INCOMPLETE" else 0)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    common.add_argument("--strict", action="store_true", help="treat skipped checks and warnings as failure (exit 3)")
    common.add_argument("-v", "--verbose", action="store_true", help="show every individual PASS line")
    common.add_argument("-q", "--quiet", action="store_true", help="show only FAIL/SKIP/WARN lines and the summary")
    ap = argparse.ArgumentParser(prog="verify_public_evidence.py", description=__doc__.split("\n\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sp = ap.add_subparsers(dest="command", required=True)

    m = sp.add_parser("manifest", parents=[common], help="verify a directory against SHA-256 manifest(s)")
    m.add_argument("directory")
    m.add_argument("--manifest", action="append", help="manifest file (repeatable); default: auto-detect in DIRECTORY")
    m.add_argument("--allow-extra", action="append", metavar="GLOB", help="accept an unlisted file (reported as WARN)")

    r = sp.add_parser("receipt", parents=[common], help="recompute receipt digests, signatures, chains and references")
    r.add_argument("files", nargs="+")
    r.add_argument("--trust-key", action="append", metavar="PEM=FINGERPRINT", help="pin an Ed25519 public key (repeatable)")
    r.add_argument("--base", help="directory against which repository-relative paths in the receipt are resolved")

    d = sp.add_parser("decision", parents=[common], help="verify a Tower human-decision proof bundle")
    d.add_argument("files", nargs="+")
    d.add_argument("--public-key", required=True, help="Tower public key PEM, obtained separately from the bundle")
    d.add_argument("--key-sha256", required=True, help="full SHA-256 fingerprint of that key, obtained out-of-band")
    d.add_argument("--expected-head", help="journal head SHA-256 obtained out-of-band (proves freshness)")
    d.add_argument("--decision-sha256", help="the decision SHA-256 you expect this bundle to prove")
    d.add_argument("--expect-bound", action="append", metavar="KEY=SHA256", help="require payload.bound[KEY] == SHA256")

    a = sp.add_parser("all", parents=[common], help="walk an evidence directory and verify everything recognisable")
    a.add_argument("directory")
    a.add_argument("--trust-key", action="append", metavar="PEM=FINGERPRINT", help="pin an Ed25519 public key (repeatable)")
    a.add_argument("--exclude", action="append", metavar="GLOB", help="relative path glob to skip (repeatable)")

    k = sp.add_parser("keyinfo", parents=[common], help="print fingerprints of a public key for out-of-band comparison")
    k.add_argument("files", nargs="+")
    return ap


def main(argv=None):
    if sys.version_info < (3, 11):
        print("verify_public_evidence.py requires Python 3.11 or newer", file=sys.stderr)
        return 2
    args = build_parser().parse_args(argv)
    if serialization is None:
        print(f"ERROR: install the 'cryptography' package (tested: pip install cryptography=={TESTED_CRYPTOGRAPHY})", file=sys.stderr)
        return 2
    report = Report()
    try:
        {"manifest": cmd_manifest, "receipt": cmd_receipt, "decision": cmd_decision,
         "all": cmd_all, "keyinfo": cmd_keyinfo}[args.command](args, report)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return emit(report, args, args.command)


if __name__ == "__main__":
    sys.exit(main())
