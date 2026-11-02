#!/usr/bin/env python3
"""verify_public_evidence.py - independent verifier for LIGHTYEAR public evidence.

Recomputes SHA-256 manifests, receipt self-digests, hash chains and Ed25519
signatures (including Control Tower human-decision proof bundles) from the
published bytes alone.  It never imports, executes or trusts Lightyear code,
never contacts the network, never follows symbolic links, and never trusts a
public key unless the person running it pins that key by its full SHA-256
fingerprint on the command line.

Requirements: Python 3.11+ and the standard library.  The `cryptography`
package (tested with cryptography==50.0.1) is needed only for Ed25519 work:
`decision`, `keyinfo`, and `--trust-key`.  Without it, `manifest` and `all`
still run and report signatures as skipped.

Exit codes: 0 = every check passed and at least one check verified evidence,
            1 = at least one FAIL,
            2 = usage, input or internal error (nothing is claimed),
            3 = INCOMPLETE: nothing was verified, or --strict and something
                was skipped or only warned.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import stat
import sys
import tarfile
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from urllib.parse import unquote

VERSION = "1.1.0"
TESTED_CRYPTOGRAPHY = "50.0.1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ZERO = "0" * 64
CHUNK = 1 << 20

# Directories never read.  `.git` is VCS metadata; the arrivals area holds
# customer/partner intake and is not public evidence, so it is refused
# unconditionally (matched on both the literal and the resolved path, case-
# insensitively) rather than being an overridable default.
ALWAYS_EXCLUDED = ("work/mainframe/arrivals",)
DEFAULT_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar")
MANIFEST_TEXT_NAMES = re.compile(r"^(SHA256SUMS(\..*)?|.*\.sha256(sums)?)$", re.I)
TOWER_EXPORT_TYPES = {"tower-journal-export/1", "control-tower-session-export"}
# Tower identity kinds (src/lightyear_control_tower/console.py): human,
# customer, agent; "service" is the local authority administrator.  Only the
# first two may make a human decision: anything else, or no kind, FAILs.
HUMAN_ACTOR_KINDS = {"human", "customer"}
NON_HUMAN_ACTOR_KINDS = {"agent", "service"}
DECISION_CHANNEL = "control-tower"
# Journal event kinds written by Control Tower (src/lightyear_control_tower).
KNOWN_TOWER_EVENTS = {"roles_assigned", "session_started", "session_ended", "tower_item_viewed",
                      "tower_decision", "tower_proposal"}
PATH_KEYS = ("path", "file", "name", "asset_name")
HASH_KEYS = ("sha256", "file_sha256")
SYNTHETIC_RE = re.compile(r"(?<![a-z0-9])(tests?|testing|fixtures?|demo|synthetic|sample|dummy|example)(?![a-z0-9])", re.I)
# Results that record parsing or context but verify nothing by themselves.  A
# run whose only PASS lines are of these kinds is INCOMPLETE, never PASS.
NON_EVIDENCE_CHECKS = {"json", "manifest-format", "key-pin", "decision-record", "synthetic-fixture"}


@dataclass
class Limits:
    json_bytes: int = 64 << 20        # largest JSON document parsed
    json_depth: int = 256             # deepest JSON nesting accepted
    text_bytes: int = 16 << 20        # SHA256SUMS and Markdown files
    pem_bytes: int = 64 << 10
    archive_members: int = 200_000    # members per archive
    archive_bytes: int = 16 << 30     # declared uncompressed bytes per archive
    tar_header_bytes: int = 1 << 20   # one pax / GNU long-name header
    run_member_bytes: int = 64 << 30  # archive member bytes decompressed per run


DEFAULT_LIMITS = Limits()
LIMITS = Limits()


# --------------------------------------------------------------------------
# Optional cryptography (imported only when Ed25519 work is needed)
# --------------------------------------------------------------------------
_CRYPTO = None


def crypto():
    """The cryptography primitives, or None if the package is not installed."""
    global _CRYPTO
    if _CRYPTO is None:
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError:
            _CRYPTO = False
        else:
            _CRYPTO = SimpleNamespace(InvalidSignature=InvalidSignature, serialization=serialization,
                                      Ed25519PublicKey=Ed25519PublicKey)
    return _CRYPTO or None


def require_crypto(why: str):
    c = crypto()
    if c is None:
        raise InputError(f"{why} needs the 'cryptography' package "
                         f"(tested: pip install cryptography=={TESTED_CRYPTOGRAPHY})")
    return c


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
@dataclass
class Result:
    status: str  # PASS | FAIL | SKIP | WARN
    check: str
    subject: str
    detail: str = ""
    anchored: bool = False  # PASS checked against a key, manifest or head the runner supplied

    def as_dict(self):
        return {"status": self.status, "check": self.check, "subject": self.subject, "detail": self.detail,
                "anchored": self.anchored}


@dataclass
class Report:
    results: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def add(self, status, check, subject, detail="", anchored=False):
        self.results.append(Result(status, check, str(subject), detail, anchored and status == "PASS"))

    def count(self, status):
        return sum(1 for r in self.results if r.status == status)


class InputError(Exception):
    """Bad command-line input (exit 2)."""


class TooLarge(ValueError):
    """Input exceeds a configured resource limit; it was not read in full."""


MALFORMED = (ValueError, TypeError, KeyError, AttributeError, IndexError, OSError, RuntimeError,
             NotImplementedError, zipfile.BadZipFile, tarfile.TarError, EOFError, zlib.error)


def guarded(report: Report, subject, fn, *args, too_large="FAIL", **kwargs):
    """Run one per-file check.  Malformed or unreadable evidence becomes a FAIL
    result for that file (never an escaped traceback, never a PASS)."""
    try:
        return fn(*args, **kwargs)
    except InputError:
        raise
    except TooLarge as exc:
        report.add(too_large, "limits", subject, f"not checked: {exc}")
    except MALFORMED as exc:
        report.add("FAIL", "malformed", subject, f"could not be checked: {type(exc).__name__}: {str(exc)[:200]}")
    return None


# --------------------------------------------------------------------------
# Bounded reads, hashing and canonical JSON
# --------------------------------------------------------------------------
def open_regular(path: Path):
    """Open without following a final symlink (O_NOFOLLOW where the OS has it),
    and refuse anything that is not a regular file (FIFOs, devices)."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"{Path(path).name} is not a regular file")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def read_bounded(path: Path, limit: int) -> bytes:
    with open_regular(path) as fh:
        raw = fh.read(limit + 1)
    if len(raw) > limit:
        raise TooLarge(f"{path.name} is larger than the {limit:,}-byte limit")
    return raw


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    with open_regular(path) as fh:
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


def _check_depth(value, limit: int):
    stack = [(value, 1)]
    while stack:
        v, d = stack.pop()
        if d > limit:
            raise ValueError(f"JSON nested deeper than {limit} levels")
        if isinstance(v, dict):
            stack.extend((x, d + 1) for x in v.values())
        elif isinstance(v, list):
            stack.extend((x, d + 1) for x in v)


def parse_json_bytes(raw: bytes):
    """Strict JSON: UTF-8 (optional BOM), no duplicate keys, no NaN/Infinity,
    bounded size and depth."""
    if len(raw) > LIMITS.json_bytes:
        raise TooLarge(f"JSON is larger than the {LIMITS.json_bytes:,}-byte limit")
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except RecursionError:
        raise ValueError("JSON nested too deeply to parse") from None
    _check_depth(value, LIMITS.json_depth)
    return value


def load_json(path: Path):
    return parse_json_bytes(read_bounded(path, LIMITS.json_bytes))


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


class _Budget:
    """Bytes of canonical JSON serialised for one document.  Nested self-digests
    re-serialise their subtree, so a hostile document with a digest at every
    level would otherwise cost depth x size."""
    left = None

    @classmethod
    def start(cls, doc):
        cls.left = 16 * len(canonical(doc, False)) + (16 << 20)

    @classmethod
    def spend(cls, n):
        if cls.left is not None:
            cls.left -= n
            if cls.left < 0:
                raise TooLarge("document needs too much re-serialisation to check (nested digests)")


def _canon_counted(value, ascii_only):
    raw = canonical(value, ascii_only)
    _Budget.spend(len(raw))
    return raw


def self_digest(obj: dict):
    """Return (rule_name, hashed_bytes) if obj['content_sha256'] is a
    recomputable self-digest, else (None, None)."""
    claimed = obj.get("content_sha256")
    if not (isinstance(claimed, str) and HEX64.fullmatch(claimed)):
        return None, None
    for name, excluded, ascii_only in DIGEST_RULES:
        body = {k: v for k, v in obj.items() if k not in excluded}
        raw = _canon_counted(body, ascii_only)
        if sha256_bytes(raw) == claimed:
            return name, raw
    return None, None


def signed_bodies(obj: dict):
    """Candidate byte strings an Ed25519 envelope signature covers."""
    body = {k: v for k, v in obj.items() if k not in ("content_sha256", "signature")}
    return [_canon_counted(body, False), _canon_counted(body, True)]


# --------------------------------------------------------------------------
# Paths: restriction and symlink policy
# --------------------------------------------------------------------------
def restricted(path: Path) -> bool:
    """True if the literal OR the resolved path lies in an always-excluded
    area.  Case-insensitive, so a case-folding filesystem cannot bypass it."""
    candidates = [os.path.abspath(path)]
    try:
        candidates.append(str(path.resolve()))
    except (OSError, RuntimeError):
        pass
    for c in candidates:
        s = unicodedata.normalize("NFKC", Path(c).as_posix().replace("\\", "/")).casefold()
        # Windows ignores trailing dots and spaces in names: "arrivals. " is "arrivals".
        s = "/".join(part.rstrip(". ") for part in s.split("/")) + "/"
        if any(f"/{r}/" in s for r in ALWAYS_EXCLUDED):
            return True
    return False


def hard_linked(path: Path) -> bool:
    """A regular file with more than one name may alias a file elsewhere,
    including a restricted one, so it is never read."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and st.st_nlink > 1


def refuse_restricted(path: Path, what: str):
    if restricted(path):
        raise InputError(f"{what} {path} is inside {ALWAYS_EXCLUDED[0]}/ (customer/partner intake); refusing to read it")


def named_file(text: str, what: str) -> Path:
    """A file named on the command line: must exist, be a regular file, not a
    symbolic link, and not be restricted."""
    p = Path(text)
    refuse_restricted(p, what)
    if p.is_symlink():
        raise InputError(f"{what} {p} is a symbolic link; symlinks are never followed - name the real file")
    if not p.is_file():
        raise InputError(f"{what} not found or not a regular file: {p}")
    if hard_linked(p):
        raise InputError(f"{what} {p} has more than one hard link; copy it to a plain file first")
    return p


def named_dir(text: str, what: str = "directory") -> Path:
    p = Path(text)
    refuse_restricted(p, what)
    if p.is_symlink():
        raise InputError(f"{what} {p} is a symbolic link; symlinks are never followed - name the real directory")
    if not p.is_dir():
        raise InputError(f"not a directory: {p}")
    return p


def safe_rel(name: str):
    """Return a PurePosixPath for a manifest entry, or None if unsafe."""
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        return None
    p = PurePosixPath(name)
    if p.is_absolute() or re.match(r"^[A-Za-z]:", name) or any(part == ".." for part in p.parts):
        return None
    return p


def lexically_within(child: Path, parent: Path) -> bool:
    c, p = os.path.normpath(os.path.abspath(child)), os.path.normpath(os.path.abspath(parent))
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def symlink_below(path: Path, root: Path) -> bool:
    """True if `path` itself, or any directory between `root` (exclusive) and
    it, is a symbolic link.  `root` is the directory the user named."""
    rel = os.path.relpath(os.path.normpath(os.path.abspath(path)), os.path.normpath(os.path.abspath(root)))
    cur = Path(os.path.abspath(root))
    for part in Path(rel).parts:
        if part in (".", ""):
            continue
        cur = cur / part
        if cur.is_symlink():
            return True
    return False


def classify(path: Path, root: Path) -> str:
    """outside | symlink | restricted | hardlink | file | absent | special, without following links."""
    if not lexically_within(path, root):
        return "outside"
    if symlink_below(path, root):
        return "symlink"
    if restricted(path):
        return "restricted"
    if path.is_file():
        return "hardlink" if hard_linked(path) else "file"
    return "absent" if not path.exists() else "special"


def iter_tree(root: Path, excludes=(), errors=None):
    """Yield (path, rel, kind) under root without following symbolic links.
    kind is file | symlink | hardlink | special.  Skipped and restricted directories are
    pruned; unreadable directories are appended to `errors`."""
    def excluded(rel):
        return any(fnmatch.fnmatch(rel, g) for g in excludes)

    def onerror(exc):
        if errors is not None:
            errors.append(exc)

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=onerror):
        d = Path(dirpath)
        rel_d = d.relative_to(root).as_posix()
        keep = []
        for n in sorted(dirnames):
            rel = n if rel_d == "." else f"{rel_d}/{n}"
            p = d / n
            if n in DEFAULT_SKIP_DIRS or excluded(rel):
                continue
            if p.is_symlink():
                yield p, rel, "symlink"
                continue
            if restricted(p):
                continue
            keep.append(n)
        dirnames[:] = keep
        for n in sorted(filenames):
            rel = n if rel_d == "." else f"{rel_d}/{n}"
            p = d / n
            if excluded(rel):
                continue
            if p.is_symlink():
                yield p, rel, "symlink"
            elif restricted(p):
                continue
            elif p.is_file():
                yield p, rel, "hardlink" if hard_linked(p) else "file"
            else:
                yield p, rel, "special"


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
    c = require_crypto("reading an Ed25519 public key")
    raw = read_bounded(path, LIMITS.pem_bytes)
    if b"PRIVATE KEY" in raw:
        raise InputError(f"{path} contains a PRIVATE key; refusing to read it. Supply the public key only.")
    try:
        key = c.serialization.load_pem_public_key(raw)
    except ValueError as exc:
        raise InputError(f"{path}: not a PEM public key ({exc})") from None
    if not isinstance(key, c.Ed25519PublicKey):
        raise InputError(f"{path}: not an Ed25519 public key")
    spki = key.public_bytes(c.serialization.Encoding.DER, c.serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, sha256_bytes(raw), sha256_bytes(spki)


def normalise_fp(text: str) -> str:
    fp = text.strip().lower().removeprefix("sha256:").replace(":", "")
    if not HEX64.fullmatch(fp):
        raise InputError(f"fingerprint must be the full 64-hex SHA-256, got {text!r} (prefixes are not accepted)")
    return fp


def pin_key(path_text: str, fingerprint: str) -> PinnedKey:
    path = named_file(path_text, "public key file")
    fp = normalise_fp(fingerprint)
    try:
        key, pem_fp, spki_fp = key_fingerprints(path)
    except TooLarge as exc:
        raise InputError(f"{path}: {exc}") from None
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
        why = "is not pinned (use --trust-key PEM=FINGERPRINT)" if crypto() else \
            "cannot be checked: the 'cryptography' package is not installed"
        report.add("SKIP", check, subject, f"Ed25519 key {kid[:16]}... {why}")
        return None
    c = crypto()
    for pk in candidates:
        for body in signed_bodies(obj):
            try:
                pk.key.verify(sig_bytes, body)
            except (c.InvalidSignature, ValueError):
                continue
            if required_kid is not None and kid != required_kid:
                return False
            if kid != pk.pem_sha256:
                report.add("WARN", check, subject, f"valid under pinned key {pk.pem_sha256[:16]}... but key_id label is {kid[:16]}...")
                return True
            report.add("PASS", check, subject, f"Ed25519 signature valid, key {kid[:16]}...", anchored=True)
            return True
    if kid in keyring or required_kid is not None:
        report.add("FAIL", check, subject, f"Ed25519 signature INVALID for key {kid[:16]}...")
        return False
    report.add("SKIP", check, subject, f"Ed25519 key {kid[:16]}... is not pinned (use --trust-key PEM=FINGERPRINT)")
    return None


# --------------------------------------------------------------------------
# Archives (read in memory, never extracted, bounded)
# --------------------------------------------------------------------------
@dataclass
class Archive:
    path: Path
    members: dict  # normalised name -> declared uncompressed size
    duplicates: set  # normalised names that occur more than once
    originals: dict = None  # normalised name -> name as stored in the archive

    @property
    def name(self):
        return self.path.name


def norm_member(name: str):
    """The path an extractor would write: './a', '/a' and 'x/../a' all mean 'a'."""
    n = posixpath.normpath(name.replace("\\", "/").lstrip("/"))
    return None if n in (".", "") or n.startswith("../") or n == ".." else n


def _is_archive(name: str) -> bool:
    return name.lower().endswith(ARCHIVE_SUFFIXES)


class BoundedTarInfo(tarfile.TarInfo):
    """Refuses oversized pax and GNU long-name headers before tarfile buffers them."""

    def _proc_member(self, tarfile_):
        if self.type in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.SOLARIS_XHDTYPE,
                         tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK) and self.size > LIMITS.tar_header_bytes:
            raise TooLarge(f"tar extended header of {self.size:,} bytes exceeds the {LIMITS.tar_header_bytes:,}-byte limit")
        return super()._proc_member(tarfile_)


@contextlib.contextmanager
def _open_tar(p: Path):
    with open_regular(p) as fh, tarfile.open(fileobj=fh, tarinfo=BoundedTarInfo) as t:
        yield t


def read_archive(p: Path) -> Archive:
    """List regular-file members, enforcing member-count and declared-size
    limits as the listing proceeds.  Names are normalised before the
    duplicate check, so an appended './a' or '/a' cannot shadow 'a'."""
    members, originals, dups, count, total = {}, {}, set(), 0, 0

    def add(name, size, regular=True):
        nonlocal count, total
        count += 1
        total += max(size, 0)
        if count > LIMITS.archive_members:
            raise TooLarge(f"{p.name} has more than {LIMITS.archive_members:,} members")
        if total > LIMITS.archive_bytes:
            raise TooLarge(f"{p.name} declares more than {LIMITS.archive_bytes:,} uncompressed bytes")
        n = norm_member(name)
        if n is None:
            return
        if n in members or n in originals:
            dups.add(n)
        if regular:
            members[n] = size
        originals.setdefault(n, name)

    if p.name.lower().endswith(".zip"):
        with open_regular(p) as fh, zipfile.ZipFile(fh) as z:
            for i in z.infolist():
                add(i.filename, i.file_size, not i.is_dir())
    else:
        with _open_tar(p) as t:
            for m in t:  # lazy: headers are read one at a time, so limits bite early
                add(m.name, m.size if m.isfile() else 0, m.isfile())
    return Archive(p, members, dups, originals)


class ArchiveIndex:
    """Read-only index of regular-file members in archives directly inside a
    directory.  Archive files that are symlinks, hard links or restricted are
    ignored; unreadable or over-limit archives are recorded in `refused`."""

    def __init__(self, directory: Path):
        self.archives, self.refused = [], []
        try:
            entries = sorted(directory.iterdir()) if directory.is_dir() else []
        except OSError:
            entries = []
        for p in entries:
            if not _is_archive(p.name) or p.is_symlink() or not p.is_file() or restricted(p) or hard_linked(p):
                continue
            try:
                self.archives.append(read_archive(p))
            except TooLarge as exc:
                self.refused.append((p.name, str(exc)))
            except MALFORMED as exc:
                self.refused.append((p.name, f"unreadable ({type(exc).__name__})"))

    @staticmethod
    def _stem(name: str) -> str:
        for s in ARCHIVE_SUFFIXES:
            if name.lower().endswith(s):
                return name[: -len(s)]
        return name

    def locate(self, name: str, hint: str | None = None):
        n = norm_member(name)
        if n is None:
            return None
        for a in self.archives:
            if hint is not None and a.name != hint:
                continue
            if n in a.members:
                return a, n
            parts = n.split("/")
            stem = self._stem(a.name)
            if stem in parts:
                rest = "/".join(parts[parts.index(stem) + 1:])
                if rest in a.members:
                    return a, rest
        return None


_MEMBER_DIGESTS = {}
_MEMBER_BYTES = [0]


def _spend_member_bytes(n):
    _MEMBER_BYTES[0] += n
    if _MEMBER_BYTES[0] > LIMITS.run_member_bytes:
        raise TooLarge(f"more than {LIMITS.run_member_bytes:,} archive bytes decompressed in this run")


def _open_member(arch: Archive, member: str, stack):
    original = arch.originals[member]
    if arch.name.lower().endswith(".zip"):
        z = stack.enter_context(zipfile.ZipFile(stack.enter_context(open_regular(arch.path))))
        return z.open(original)
    t = stack.enter_context(_open_tar(arch.path))
    fh = t.extractfile(t.getmember(original))
    if fh is None:
        raise ValueError(f"member {member} is not a regular file")
    return fh


def hash_member(arch: Archive, member: str) -> tuple[str, int]:
    """Stream a member through SHA-256, reading at most its declared size + 1.
    Each member is decompressed at most once per run."""
    key = (str(arch.path), member)
    if key in _MEMBER_DIGESTS:
        return _MEMBER_DIGESTS[key]
    declared = arch.members[member]
    h, n = hashlib.sha256(), 0
    with contextlib.ExitStack() as stack:
        fh = _open_member(arch, member, stack)
        while chunk := fh.read(CHUNK):
            n += len(chunk)
            _spend_member_bytes(len(chunk))
            if n > declared:
                raise ValueError(f"member {member} yields more bytes than its declared size {declared}")
            h.update(chunk)
    _MEMBER_DIGESTS[key] = (h.hexdigest(), n)
    return _MEMBER_DIGESTS[key]


def read_member(arch: Archive, member: str, limit: int) -> bytes:
    if arch.members[member] > limit:
        raise TooLarge(f"member {member} is larger than the {limit:,}-byte limit")
    with contextlib.ExitStack() as stack:
        raw = _open_member(arch, member, stack).read(limit + 1)
    _spend_member_bytes(len(raw))
    if len(raw) > limit:
        raise TooLarge(f"member {member} is larger than the {limit:,}-byte limit")
    return raw


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
    text = read_bounded(path, LIMITS.text_bytes).decode("utf-8")
    for n, line in enumerate(text.splitlines(), 1):
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
        out.append(Entry(n, h, size if isinstance(size, int) and not isinstance(size, bool) else None))
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
                x.archive_hint = arch if isinstance(arch, str) else None
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
    if isinstance(doc.get("archive_sha256"), str) and HEX64.fullmatch(doc["archive_sha256"]) and isinstance(rel.get("asset_name"), str):
        size = doc.get("archive_bytes", doc.get("size_in_bytes"))
        out.append(Entry(rel["asset_name"], doc["archive_sha256"], size if isinstance(size, int) else None))
    arc = doc.get("archive")
    if isinstance(arc, dict) and isinstance(arc.get("sha256"), str) and HEX64.fullmatch(arc["sha256"]) and isinstance(arc.get("url"), str):
        out.append(Entry(arc["url"].rsplit("/", 1)[-1], arc["sha256"], arc.get("bytes") if isinstance(arc.get("bytes"), int) else None))
    return out


def duplicate_names(entries):
    seen, dups = set(), []
    for e in entries:
        if e.name in seen:
            dups.append(e.name)
        seen.add(e.name)
    return dups


def resolve_entries(entries, manifest_path: Path, target: Path, search_up: int = 8):
    """Resolve entries to files inside `target` (choosing the base directory
    that resolves most entries), falling back to sibling-archive members.
    Returns list of (entry, kind, location) with kind in
    file | member | duplicate | symlink | hardlink | restricted | missing | unsafe."""
    bases, b = [], target
    for _ in range(search_up + 1):
        bases.append(b)
        if b.parent == b:
            break
        b = b.parent
    if manifest_path.parent not in bases:
        bases.insert(0, manifest_path.parent)

    def place(base, e):
        rel = safe_rel(e.name)
        if rel is None:
            return "unsafe", None
        p = base.joinpath(*rel.parts)
        return classify(p, target), p

    best = max(bases, key=lambda base: (sum(1 for e in entries if place(base, e)[0] == "file"), -bases.index(base)))
    archives = None
    out = []
    for e in entries:
        kind, p = place(best, e)
        if kind in ("unsafe", "file", "symlink", "hardlink", "restricted"):
            out.append((e, kind, p))
            continue
        if archives is None:
            archives = ArchiveIndex(target)
        loc = (archives.locate(e.name, e.archive_hint) if e.archive_hint else None) or archives.locate(e.name)
        if loc:
            arch, member = loc
            out.append((e, "duplicate" if member in arch.duplicates else "member", loc))
        else:
            why = "; ".join(f"archive {n} refused: {r}" for n, r in archives.refused)
            out.append((e, "missing", why or None))
    return out


def canonical_json_digests(read, size: int | None = None):
    """SHA-256 of the canonical-JSON form of a JSON file (some Lightyear
    references pin the parsed JSON value rather than the raw bytes)."""
    if size is not None and size > LIMITS.json_bytes:
        return set()
    try:
        value = parse_json_bytes(read())
    except (ValueError, UnicodeDecodeError):
        return set()
    return {sha256_bytes(canonical(value, False)), sha256_bytes(canonical(value, True))}


ENTRY_FAILURES = {
    "unsafe": ("manifest-path", "unsafe path (absolute, '..' or backslash)"),
    "symlink": ("manifest-symlink", "listed path is (or passes through) a symbolic link; symlinks are never followed"),
    "restricted": ("manifest-restricted", f"listed path is inside {ALWAYS_EXCLUDED[0]}/; refused, not read"),
    "hardlink": ("manifest-hardlink", "listed file has more than one hard link (it may alias another file); not read"),
    "duplicate": ("archive-duplicate", "archive contains this member name more than once (ambiguous evidence)"),
}


def check_entries(resolved, report: Report, subject: str, missing_status: str = "FAIL",
                  allow_canonical: bool = False, mismatch_status: str = "FAIL", verified: dict | None = None,
                  anchored: bool = False):
    """Hash every resolved entry. Returns (passed, failed, missing, covered_files).
    If `verified` is given, each matching full SHA-256 is recorded in it."""
    ok = bad = miss = 0
    covered = set()
    for e, kind, loc in resolved:
        label = f"{subject} :: {e.name}"
        if kind in ENTRY_FAILURES:
            check, detail = ENTRY_FAILURES[kind]
            if kind == "duplicate":
                detail = f"{loc[0].name}: {detail}"
            report.add("FAIL", check, label, detail)
            bad += 1
            continue
        if kind == "missing":
            report.add(missing_status, "manifest-missing", label, "listed file not present" + (f" ({loc})" if loc else ""))
            miss += 1
            continue
        try:
            if kind == "file":
                digest, size = sha256_file(loc)
                covered.add(loc.resolve())
                where = ""
            else:
                arch, member = loc
                digest, size = hash_member(arch, member)
                where = f" (member of {arch.name})"
        except MALFORMED as exc:
            report.add("FAIL", "manifest-sha256", label, f"could not be read: {type(exc).__name__}: {str(exc)[:160]}")
            bad += 1
            continue
        if digest != e.sha256 and allow_canonical and e.name.lower().endswith(".json"):
            if kind == "file":
                def read(p=loc):
                    return read_bounded(p, LIMITS.json_bytes)
            else:
                def read(a=loc[0], m=loc[1]):
                    return read_member(a, m, LIMITS.json_bytes)
            try:
                canon = canonical_json_digests(read, size)
            except TooLarge:
                canon = set()
            if e.sha256 in canon:
                report.add("PASS", "manifest-sha256", label, f"sha256 {e.sha256[:16]}... of canonical JSON{where}",
                           anchored=anchored)
                ok += 1
                continue
        if digest != e.sha256:
            report.add(mismatch_status, "manifest-sha256", label, f"SHA-256 mismatch{where}: expected {e.sha256[:16]}..., got {digest[:16]}...")
            bad += 1
        elif e.size is not None and e.size != size:
            report.add("FAIL", "manifest-size", label, f"size mismatch{where}: expected {e.size}, got {size}")
            bad += 1
        else:
            report.add("PASS", "manifest-sha256", label, f"sha256 {digest[:16]}...{where}", anchored=anchored)
            if verified is not None:
                verified.setdefault(digest, label)
            ok += 1
    return ok, bad, miss, covered


# --------------------------------------------------------------------------
# Receipts: self-digests, signatures, chains, file references
# --------------------------------------------------------------------------
def fmt_path(path: tuple) -> str:
    """A short JSON path for messages; keys are clipped so a hostile document
    cannot make labels (or memory) grow with nesting depth x key length."""
    out = "$" + "".join(f"[{k}]" if isinstance(k, int) else "." + str(k)[:40] for k in path)
    return out if len(out) <= 200 else out[:96] + "..." + out[-96:]


def iter_dicts(obj, path=()):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from iter_dicts(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_dicts(v, path + (i,))


def iter_lists(obj, path=(), parent=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list):
                yield path + (k,), v, obj
            yield from iter_lists(v, path + (k,), obj)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_lists(v, path + (i,), obj)


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
        groups.setdefault(json.dumps(jid, sort_keys=True), []).append(e)
    failures = []
    for jkey, events in groups.items():
        jid = json.loads(jkey)
        previous = None
        for i, e in enumerate(events, 1):
            where = f"journal {jid!r} " if jid is not None else ""
            if "sequence" in e and e["sequence"] != i:
                failures.append(f"{where}element {i} has sequence {str(e['sequence'])[:20]}")
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
                refs.append(Entry(n, h, size if isinstance(size, int) and not isinstance(size, bool) else None))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(doc)
    return refs


def check_document(doc, label: str, keyring: dict, report: Report, *, explicit: bool):
    """Self-digests, signatures and chains inside one JSON document."""
    _Budget.start(doc)
    stats = {"digest": 0, "sig": 0, "chain": 0}
    chain_members = set()
    for lpath, lst, parent in iter_lists(doc):
        if is_chain(lst):
            for e in lst:
                chain_members.add(id(e))
            stats["chain"] += 1
            check_chain(lst, parent, f"{label} {fmt_path(lpath)}", report)
    for dpath, obj in iter_dicts(doc):
        sig = obj.get("signature")
        signed = isinstance(sig, dict) and isinstance(sig.get("algorithm"), str)
        claimed = obj.get("content_sha256")
        sub = f"{label} {fmt_path(dpath)}"
        if isinstance(sig, dict) and not signed and ("value" in sig or "key_id" in sig):
            # An envelope signature whose algorithm was removed or mangled must not be ignored.
            # (Other "signature" objects, such as recorded cosign results, carry neither field.)
            report.add("FAIL", "signature", sub, "signature object has no algorithm; it cannot be checked")
        if "content_sha256" in obj and not (isinstance(claimed, str) and HEX64.fullmatch(claimed)) \
                and (signed or id(obj) in chain_members or obj is doc):
            report.add("FAIL" if (explicit or signed or id(obj) in chain_members) else "WARN", "self-digest", sub,
                       "content_sha256 is not a lowercase 64-hex SHA-256; not verifiable")
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
                report.add("SKIP", "signature", sub, f"unsupported signature algorithm {alg[:40]!r} (key_id {str(sig.get('key_id'))[:20]})")
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
    present = [r for r in resolved if r[1] not in ("missing",)]
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
        sib = path.parent / ("journal.json" if stem == "journal_head" else f"{stem}.json")
        if sib == path or sib.is_symlink() or restricted(sib) or not sib.is_file():
            continue
        try:
            raw = read_bounded(sib, LIMITS.json_bytes)
        except TooLarge:
            report.add("SKIP", "binding", f"{label} {key}", f"sibling {sib.name} exceeds the JSON size limit; not checked")
            continue
        try:
            other = parse_json_bytes(raw)
        except (ValueError, UnicodeDecodeError):
            other = None
        if stem == "journal_head":
            events = other.get("events") if isinstance(other, dict) else None
            if isinstance(events, list) and events and isinstance(events[-1], dict):
                last = events[-1].get("content_sha256")
                if last == value and self_digest(events[-1])[0] is None:
                    report.add("FAIL", "binding", f"{label} {key}",
                               "journal.json's last event claims this digest but its content does not recompute to it")
                    continue
                report.add("PASS" if last == value else "FAIL", "binding", f"{label} {key}",
                           "equals the recomputed last event of journal.json" if last == value else
                           f"journal.json ends at {str(last)[:16]}..., not {value[:16]}...")
            continue
        candidates = {sha256_bytes(raw)}
        if other is not None:
            candidates |= {sha256_bytes(canonical(other, False)), sha256_bytes(canonical(other, True))}
            if isinstance(other, dict) and self_digest(other)[0] is not None:
                candidates.add(other["content_sha256"])  # only a digest that recomputes, never a bare claim
        ok = value in candidates
        report.add("PASS" if ok else "FAIL", "binding", f"{label} {key}",
                   f"binds sibling {sib.name}" if ok else f"does not match sibling {sib.name} (file, canonical or content_sha256)")


# --------------------------------------------------------------------------
# Tower decision proofs
# --------------------------------------------------------------------------
def parse_ts(text):
    if not isinstance(text, str):
        return None
    try:
        t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else None


def synthetic_indicators(label: str, export: dict, events: list, p: dict) -> list:
    """Labels that mark a proof as a test/demo fixture rather than a real decision."""
    hits = []
    actor = p.get("actor") if isinstance(p.get("actor"), dict) else {}
    for where, text in (("file name", Path(label).name), ("scope", export.get("scope")),
                        ("decision reason", p.get("reason")), ("decider name", actor.get("name"))):
        if isinstance(text, str) and SYNTHETIC_RE.search(text):
            hits.append(f"{where} {text[:60]!r}")
    for e in events:
        if isinstance(e, dict) and e.get("kind") == "roles_assigned" and isinstance(e.get("payload"), dict):
            r = e["payload"].get("reason")
            if isinstance(r, str) and SYNTHETIC_RE.search(r):
                hits.append(f"role-grant reason {r[:60]!r}")
                break
    return hits


def check_decision(proof, label: str, report: Report, pinned: PinnedKey | None, *,
                   expected_head=None, expected_decision=None, expected_bound=None, today=None):
    """Verify a tower-decision-proof/1 bundle from its bytes alone."""
    _Budget.start(proof)

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
        fail("journal", f"unexpected journal record_type {str(export.get('record_type'))[:40]!r}")
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

    export_ok = envelope(export, f"{label} journal-export")
    events = export["events"]
    previous, chain_err = ZERO, []
    for i, ev in enumerate(events, 1):
        if not isinstance(ev, dict):
            chain_err.append(f"event {i} is not an object")
            continue
        envelope(ev, f"{label} event {i}")
        if ev.get("sequence") != i:
            chain_err.append(f"event {i} has sequence {str(ev.get('sequence'))[:20]}")
        if ev.get("previous_sha256") != previous:
            chain_err.append(f"event {i} previous_sha256 does not equal event {i - 1} content_sha256")
        previous = ev.get("content_sha256")
    # Collapse per-event PASS lines into one; keep FAIL/SKIP detail.
    per_event = [r for r in report.results if r.subject.startswith(f"{label} event ")]
    report.results = [r for r in report.results if not (r.subject.startswith(f"{label} event ") and r.status == "PASS")]
    passes = sum(1 for r in per_event if r.status == "PASS" and r.check == "signature")
    digests = sum(1 for r in per_event if r.status == "PASS" and r.check == "self-digest")
    if events and passes == len(events) and digests == len(events):
        report.add("PASS", "event-signatures", label, f"all {len(events)} journal events: digest recomputed and Ed25519 signature valid",
                   anchored=True)
    elif events and digests == len(events):
        report.add("PASS", "event-digests", label, f"all {len(events)} journal events: content_sha256 recomputed (signatures reported separately)")
    authenticated = bool(pinned) and export_ok and bool(events) and passes == len(events) and digests == len(events)
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
            report.add("PASS", "journal-head-expected", label, "matches the independently obtained journal head",
                       anchored=authenticated)
    matches = [i for i, e in enumerate(events) if isinstance(e, dict) and e.get("content_sha256") == dsha]
    if len(matches) != 1 or events[matches[0]].get("kind") != "tower_decision":
        fail("decision-in-journal", "decision_sha256 is not exactly one tower_decision event in the journal")
        return
    idx = matches[0]
    ev = events[idx]
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
    # Identity: an allow-list, so a missing or unknown kind is refused.
    actor = p.get("actor") if isinstance(p.get("actor"), dict) else {}
    if not (isinstance(actor.get("id"), str) and actor["id"].strip()):
        problems.append("decider identity (actor.id) is missing")
    if actor.get("kind") not in HUMAN_ACTOR_KINDS:
        problems.append(f"decider kind is {str(actor.get('kind'))[:30]!r}; only {'/'.join(sorted(HUMAN_ACTOR_KINDS))} "
                        "identities make human decisions")
    if p.get("channel") != DECISION_CHANNEL:
        problems.append(f"channel {str(p.get('channel'))[:30]!r} is not {DECISION_CHANNEL!r}")
    roles = p.get("roles_held")
    if not (isinstance(roles, list) and roles and all(isinstance(r, str) and r for r in roles)):
        problems.append("roles_held is missing or empty")
    else:
        # Tower's rule: the latest roles_assigned for this identity (and scope) is the grant in force.
        grant = next((e for e in reversed(events[:idx]) if isinstance(e, dict) and e.get("kind") == "roles_assigned"
                      and isinstance(e.get("payload"), dict) and e["payload"].get("actor_id") == actor.get("id")
                      and e["payload"].get("scope", export.get("scope")) == export.get("scope")), None)
        granted = grant["payload"].get("roles") if grant else None
        if not isinstance(granted, list):
            problems.append("no role grant for the decider earlier in this journal")
        elif not set(roles) <= set(granted):
            problems.append(f"roles_held {sorted(roles)} are not all in the decider's latest grant {sorted(map(str, granted))}")
    # Session: opened once, earlier in this journal, by the same identity, and not expired.
    sid = p.get("session_id")
    if not (isinstance(sid, str) and sid):
        problems.append("session_id is missing")
    else:
        starts = [e for e in events[:idx] if isinstance(e, dict) and e.get("kind") == "session_started" and e.get("session_id") == sid]
        if len(starts) != 1:
            problems.append(f"session {sid[:12]}... was not opened exactly once before the decision")
        else:
            s = starts[0]
            if s.get("actor") != ev.get("actor"):
                problems.append("the decision session was opened by a different identity")
            sp = s.get("payload") if isinstance(s.get("payload"), dict) else {}
            began, at, exp = parse_ts(s.get("occurred_at")), parse_ts(ev.get("occurred_at")), parse_ts(sp.get("expires_at"))
            if began is None or at is None or exp is None:
                problems.append("session start, session expiry (expires_at) or decision time is missing or not a timestamp with offset")
            elif not began <= at <= exp:
                problems.append(f"decision at {ev.get('occurred_at')} is outside its session "
                                f"({s.get('occurred_at')} to {sp.get('expires_at')})")
            start_i = events.index(s)
            if any(isinstance(e, dict) and e.get("kind") == "session_ended" and e.get("session_id") == sid
                   for e in events[start_i + 1:idx]):
                problems.append("the decision session had already ended (session_ended) before the decision")
    if expected_bound:
        bound = p.get("bound") if isinstance(p.get("bound"), dict) else {}
        for k, v in expected_bound.items():
            if bound.get(k) != v:
                problems.append(f"bound.{k} is {str(bound.get(k))[:16]}..., expected {v[:16]}...")
    later = [e for e in events[idx + 1:] if isinstance(e, dict) and e.get("kind") == "tower_decision"
             and isinstance(e.get("payload"), dict) and e["payload"].get("kind") == p.get("kind")
             and e["payload"].get("bound") == p.get("bound") and e["payload"].get("decision_slot") == p.get("decision_slot")]
    if later:
        problems.append(f"superseded by a later {str(p.get('kind'))[:40]} decision on the same subject (event {str(later[0].get('sequence'))[:10]})")
    # Tower decides "same subject" with a per-kind rule this verifier cannot reproduce, so a later decision
    # of the same kind that overlaps this one's bound, or any later event of an unknown kind, is flagged.
    bound_items = set((k, json.dumps(v, sort_keys=True)) for k, v in (p.get("bound") or {}).items()) \
        if isinstance(p.get("bound"), dict) else set()
    maybe = []
    for e in events[idx + 1:]:
        if not isinstance(e, dict) or any(e is x for x in later):
            continue
        ep = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if e.get("kind") not in KNOWN_TOWER_EVENTS:
            maybe.append(f"event {str(e.get('sequence'))[:10]} has unknown kind {str(e.get('kind'))[:40]!r}")
        elif e.get("kind") == "tower_decision" and ep.get("kind") == p.get("kind") and isinstance(ep.get("bound"), dict) \
                and bound_items & set((k, json.dumps(v, sort_keys=True)) for k, v in ep["bound"].items()):
            maybe.append(f"event {str(e.get('sequence'))[:10]} is a later {str(p.get('kind'))[:40]} decision "
                         f"(outcome {str(ep.get('outcome'))[:20]}, slot {str(ep.get('decision_slot'))[:20]}) on an overlapping subject")
    if maybe:
        report.add("WARN", "decision-superseded", label, "possibly superseded or affected: " + "; ".join(maybe[:3])
                   + ". Tower's per-kind subject rule decides; confirm out-of-band.")
    if problems:
        fail("decision-semantics", "; ".join(problems))
    elif not authenticated:
        report.add("SKIP", "decision-semantics", label,
                   "structurally consistent, but the proof is NOT authenticated: verify it with `decision` and the "
                   "independently pinned Tower key. An unauthenticated proof proves nothing about who decided.")
    else:
        report.add("PASS", "decision-semantics", label, anchored=True, detail=
                   f"kind={p.get('kind')} outcome={p.get('outcome')} recorded for {actor.get('kind')} "
                   f"{actor.get('name') or actor.get('id')!r} at {ev.get('occurred_at')}; scope={p.get('scope')}; "
                   "session valid; not superseded")
        reason = str(p.get("reason", ""))
        report.add("PASS", "decision-record", label,
                   f"reason: {reason[:110]!r}; authentication: {p.get('authentication')}; "
                   f"signature: {export.get('signature_type') or 'Tower service signature'}")
        report.notes.append("The Ed25519 signature is the Tower SERVICE key countersigning what an authenticated "
                            "session did. The actor name/kind inside is recorded by Tower, not a personal signature.")
    synthetic = synthetic_indicators(label, export, events, p)
    if synthetic:
        report.add("WARN", "synthetic-fixture", label,
                   "labelled as a test/demo fixture (" + "; ".join(synthetic[:3]) + "): proves the verification "
                   "mechanics only, not a real-world decision")
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
        try:
            entries, errors = parse_sha256sums(path)
        except TooLarge as exc:
            return None, None, [str(exc)]
        except (OSError, UnicodeDecodeError) as exc:
            return None, None, [f"unreadable: {type(exc).__name__}"]
        kind = "SHA256SUMS"
    else:
        try:
            doc = load_json(path)
        except TooLarge as exc:
            return None, None, [str(exc)]
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            return None, None, [f"unreadable JSON: {str(exc)[:160]}"]
        kind, entries = manifest_entries(doc)
        if kind is None:
            return None, None, []
        entries = entries + archive_binding(doc, path.parent)
        errors = []
    for name in duplicate_names(entries):
        errors.append(f"entry {name[:80]!r} is listed more than once (ambiguous)")
    return kind, entries, errors


def discover_manifests(directory: Path):
    found = []
    for p in sorted(directory.iterdir()):
        if p.is_symlink() or not p.is_file() or restricted(p):
            continue
        if MANIFEST_TEXT_NAMES.match(p.name) or p.suffix.lower() == ".json":
            kind, entries, _ = load_manifest_file(p)
            if kind:
                found.append(p)
    return found


def cmd_manifest(args, report: Report):
    target = named_dir(args.directory)
    manifests = [named_file(m, "manifest") for m in args.manifest] if args.manifest else discover_manifests(target)
    if not manifests:
        raise InputError(f"no SHA-256 manifest found in {target}; name one with --manifest")
    covered, manifest_files, verified, skipped = set(), {}, {}, set()
    for m in manifests:
        kind, entries, errors = load_manifest_file(m)
        for e in errors:
            report.add("FAIL", "manifest-format", m, e)
        if not kind:
            if not errors:
                report.add("FAIL", "manifest-format", m, "not a recognised SHA-256 manifest")
            continue
        resolved = resolve_entries(entries, m, target)
        if not args.manifest and not any(k not in ("missing",) for _, k, _ in resolved):
            refused = sorted({loc for _, _, loc in resolved if loc})
            report.add("SKIP", "manifest", m, f"{kind}: none of its {len(entries)} entries are in this directory "
                       "(it describes files published elsewhere); name it with --manifest to require them"
                       + (f" [{'; '.join(refused)}]" if refused else ""))
            skipped.add(m.resolve())
            continue
        manifest_files[m.resolve()] = m.name
        if not errors:
            report.add("PASS", "manifest-format", m, f"{kind}: {len(entries)} entries")
        _, _, _, cov = check_entries(resolved, report, m.name, verified=verified, anchored=bool(args.manifest))
        covered |= cov
    pinned_manifests = {sha256_file(Path(mp))[0]: name for mp, name in manifest_files.items()}
    # Extra files: present in the directory tree but listed by no manifest.
    walk_errors = []
    for p, rel, kind in iter_tree(target, errors=walk_errors):
        allowed = any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(p.name, g) for g in args.allow_extra or [])
        if kind != "file":
            what = {"symlink": "symbolic link (never followed)",
                    "hardlink": "file with more than one hard link (not read)"}.get(kind, "special file (not a regular file)")
            report.add("WARN" if allowed else "FAIL", "manifest-extra", rel, f"{what} present but not listed in any manifest")
            continue
        rp = p.resolve()
        if rp in covered or rp in manifest_files or rp in skipped:
            continue
        digest, _ = sha256_file(p)
        if digest in pinned_manifests:
            report.add("PASS", "manifest-extra", rel, f"byte-identical copy of the manifest {pinned_manifests[digest]}")
            continue
        if digest in verified:  # full 64-hex comparison
            report.add("PASS", "manifest-extra", rel, f"not listed by name, but byte-identical to verified entry {verified[digest]}")
            continue
        anchors = []
        if p.suffix.lower() == ".json" and p.stat().st_size < 4 << 20:
            text = p.read_text(encoding="utf-8", errors="replace")
            anchors = [name for h, name in pinned_manifests.items() if h in text]
        if allowed:
            report.add("WARN", "manifest-extra", rel, "not listed in any manifest (allowed by --allow-extra)")
        elif anchors and not args.manifest:
            report.add("WARN", "manifest-extra", rel, f"not covered by a manifest; it records the SHA-256 of {', '.join(anchors)} "
                       "(consistent), but its own contents are unattested")
        else:
            report.add("FAIL", "manifest-extra", rel, "file present but not listed in any manifest")
    for exc in walk_errors:
        report.add("FAIL", "manifest-extra", getattr(exc, "filename", target), "directory could not be read; inventory incomplete")


def _parse_or_fail(path: Path, report: Report, label: str):
    try:
        return True, load_json(path)
    except TooLarge:
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        report.add("FAIL", "json", label, f"cannot parse strictly: {str(exc)[:160]}")
        return False, None


def _receipt_one(path: Path, args, keyring, report: Report, label: str):
    ok, doc = _parse_or_fail(path, report, label)
    if not ok:
        return
    if isinstance(doc, dict) and doc.get("schema") == "tower-decision-proof/1":
        report.notes.append(f"{path} is a Tower decision proof; use the `decision` command to check its human decision.")
    schema = (doc.get("schema") or doc.get("record_type") or doc.get("receipt_type") or doc.get("artifact_type")) if isinstance(doc, dict) else None
    report.add("PASS", "json", label, f"strict JSON parsed (format: {str(schema)[:60] if schema else 'unlabelled'})")
    before = len(report.results)
    stats = check_document(doc, label, keyring, report, explicit=True)
    mkind, _ = manifest_entries(doc)
    check_sibling_bindings(doc, path, report, label)
    check_references(doc, path, report, label, named_dir(args.base, "--base") if args.base else None,
                     manifest_keys=("assets", "files", "metadata_files", "members") if mkind else ())
    if not any(stats.values()) and not any(r.check == "references" for r in report.results[before:]):
        report.add("WARN", "receipt", label, "no self-digest, signature, chain or file reference found to verify")


def cmd_receipt(args, report: Report):
    keyring = parse_trust_args(args.trust_key)
    paths = [named_file(f, "receipt") for f in args.files]
    for path in paths:
        label = path.name if len(paths) == 1 else str(path)
        guarded(report, label, _receipt_one, path, args, keyring, report, label)


def cmd_decision(args, report: Report):
    require_crypto("`decision`")
    pinned = pin_key(args.public_key, args.key_sha256)
    report.add("PASS", "key-pin", pinned.path,
               f"public key matches your fingerprint ({pinned.matched_on}); PEM sha256 {pinned.pem_sha256[:16]}..., SPKI sha256 {pinned.spki_sha256[:16]}...")
    expected_bound = {}
    for b in args.expect_bound or []:
        k, sep, v = b.partition("=")
        if not sep or not k:
            raise InputError(f"--expect-bound expects KEY=SHA256, got {b!r}")
        expected_bound[k] = normalise_fp(v)
    head = normalise_fp(args.expected_head) if args.expected_head else None
    want = normalise_fp(args.decision_sha256) if args.decision_sha256 else None
    paths = [named_file(f, "proof") for f in args.files]
    for path in paths:
        label = path.name if len(paths) == 1 else str(path)
        guarded(report, label, _decision_one, path, label, report, pinned, head, want, expected_bound or None)


def _decision_one(path, label, report, pinned, head, want, expected_bound):
    ok, proof = _parse_or_fail(path, report, label)
    if ok:
        check_decision(proof, label, report, pinned, expected_head=head, expected_decision=want,
                       expected_bound=expected_bound)


LINK_RE = re.compile(r"(?:\]\(|href=\")([^)\"\s]+)#sha256=([0-9a-f]{64})[)\"]")


def _md_links(path: Path, rel: str, root: Path, report: Report, counts: dict):
    text = read_bounded(path, LIMITS.text_bytes).decode("utf-8", errors="replace")
    for target, want in LINK_RE.findall(text):
        clean = unquote(target.split("?")[0])
        subject = f"{rel} -> {target}"
        if re.match(r"^[a-z][a-z0-9+.-]*:", clean, re.I) or clean.startswith("/") or "\\" in clean or "\x00" in clean:
            report.add("SKIP", "md-link", subject, "external or absolute link; not checked")
            continue
        p = Path(os.path.normpath(path.parent / clean))
        kind = classify(p, root)
        if kind == "symlink":
            report.add("SKIP", "md-link", subject, "link target is (or passes through) a symbolic link; not followed")
            continue
        if kind != "file":
            report.add("SKIP", "md-link", subject, "not present under the walked directory" if kind != "restricted"
                       else f"inside {ALWAYS_EXCLUDED[0]}/; not read")
            continue
        counts["md-links"] += 1
        got, _ = sha256_file(p)
        report.add("PASS" if got == want else "FAIL", "md-link", subject,
                   "linked file matches #sha256 in the document" if got == want else
                   f"linked file SHA-256 {got[:16]}... differs from #sha256={want[:16]}...")


def _all_one(path: Path, rel: str, root: Path, keyring: dict, report: Report, tally: dict, found_keys: dict, counts: dict):
    name = path.name.lower()
    if name.endswith(".pem"):
        counts["pem"] += 1
        raw = read_bounded(path, LIMITS.pem_bytes)
        if b"PRIVATE KEY" in raw:
            report.add("FAIL", "private-key", rel, "contains a PRIVATE KEY block; published evidence must never contain private keys")
            return
        if crypto() is None:
            found_keys.setdefault(sha256_bytes(raw), []).append(rel)
            return
        try:
            _, pem_fp, _ = key_fingerprints(path)
            found_keys.setdefault(pem_fp, []).append(rel)
        except InputError as exc:
            report.notes.append(f"{rel}: {exc}")
        return
    if name.endswith(".md"):
        _md_links(path, rel, root, report, counts)
        return
    is_text_manifest = MANIFEST_TEXT_NAMES.match(path.name)
    if not (name.endswith(".json") or is_text_manifest):
        return
    if is_text_manifest:
        doc, mkind = None, "SHA256SUMS"
    else:
        counts["json"] += 1
        try:
            doc = load_json(path)
        except TooLarge:
            raise
        except (ValueError, UnicodeDecodeError) as exc:
            report.add("FAIL", "json", rel, f"cannot parse strictly: {str(exc)[:160]}")
            return
        mkind, _ = manifest_entries(doc)
    if mkind:
        kind, entries, errors = load_manifest_file(path)
        for e in errors:
            report.add("FAIL", "manifest-format", rel, e)
        resolved = resolve_entries(entries or [], path, path.parent)
        present = [r for r in resolved if r[1] != "missing"]
        if not resolved:
            pass
        elif not present:
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
            # Unsafe paths, symlinks, restricted paths and duplicate archive
            # members remain FAILs.
            sub = Report()
            ok, bad, _, _ = check_entries(present, sub, rel, mismatch_status="WARN")
            report.results.extend(r for r in sub.results if r.status != "PASS")
            report.add("SKIP", "manifest", rel, f"{kind}: only {len(present)} of {len(entries)} listed files are here "
                       f"({ok} match, {bad} differ); download the full set and run `manifest`")
    if doc is None:
        return
    if isinstance(doc, dict) and doc.get("schema") == "tower-decision-proof/1":
        counts["proofs"] += 1
        sub = Report()
        exp_sig = doc["journal"].get("signature") if isinstance(doc.get("journal"), dict) else None
        kid = exp_sig.get("key_id") if isinstance(exp_sig, dict) else None
        pinned = keyring.get(kid) if isinstance(kid, str) else None
        if keyring and pinned is None:
            report.add("FAIL", "decision-key", rel, f"decision proof is signed under key_id {str(kid)[:16]}..., "
                       "which is not one of the keys you pinned")
        check_decision(doc, rel, sub, pinned)
        # Without a pinned key the signature lines are SKIPs; collapse them.
        skips = [r for r in sub.results if r.status == "SKIP"]
        report.results.extend(r for r in sub.results if r.status != "SKIP")
        report.notes.extend(n for n in sub.notes if n not in report.notes)
        if skips:
            report.add("SKIP", "signature", rel, f"{len(skips)} Tower signatures not checked: run `decision` with the pinned Tower key")
        return
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
    report.results.extend(r for r in sub.results if r.status in ("FAIL", "WARN"))
    n = {s: sub.count(s) for s in ("PASS", "SKIP")}
    if n["PASS"]:
        report.add("PASS", "receipt", rel, f"{n['PASS']} digest/signature/chain/reference checks passed",
                   anchored=any(r.anchored for r in sub.results))
    if n["SKIP"]:
        reasons = sorted({r.detail.split(" (")[0][:70] for r in sub.results if r.status == "SKIP"})
        report.add("SKIP", "receipt", rel, f"{n['SKIP']} checks skipped: " + "; ".join(reasons[:2]))


def cmd_all(args, report: Report):
    root = named_dir(args.directory)
    keyring = parse_trust_args(args.trust_key)
    tally, found_keys = {}, {}
    counts = {"json": 0, "manifests": 0, "proofs": 0, "md-links": 0, "pem": 0, "symlinks": 0}
    walk_errors = []
    for path, rel, kind in iter_tree(root, args.exclude or [], walk_errors):
        if kind == "symlink":
            counts["symlinks"] += 1
            report.add("SKIP", "symlink", rel, "symbolic link not followed")
            continue
        if kind == "hardlink":
            report.add("SKIP", "hardlink", rel, "file has more than one hard link (it may alias a file elsewhere); not read")
            continue
        if kind != "file":
            continue
        guarded(report, rel, _all_one, path, rel, root, keyring, report, tally, found_keys, counts, too_large="SKIP")
    for exc in walk_errors:
        report.add("SKIP", "walk", str(getattr(exc, "filename", root)), "directory could not be read; not checked")
    if crypto() is None:
        report.notes.insert(0, "the 'cryptography' package is not installed: Ed25519 signatures were reported as SKIP")
    report.notes.insert(0, f"walked {root}: {counts['json']} JSON files, {counts['manifests']} complete manifests, "
                        f"{counts['proofs']} Tower decision proofs, {counts['md-links']} #sha256 document links, "
                        f"{counts['pem']} key files, {counts['symlinks']} symlinks not followed")
    report.notes.insert(1, f"inside receipts: {tally.get('self-digest', 0)} self-digests recomputed, {tally.get('signature', 0)} Ed25519 "
                        f"signatures verified, {tally.get('chain', 0)} hash chains, {tally.get('binding', 0)} sibling bindings, "
                        f"{tally.get('references', 0)} documents whose local file references all match")
    for fp, paths in sorted(found_keys.items(), key=lambda kv: kv[1][0]):
        pinned = "PINNED by you" if fp in keyring else "not trusted (not pinned)"
        report.notes.append(f"public key {fp[:16]}... in {len(paths)} file(s), e.g. {paths[0]}: {pinned}")
    for k in sorted(x for x in tally if x.startswith("sig:")):
        report.notes.insert(2, f"  {tally[k]} signatures verified under pinned key {k[4:]}")


def cmd_keyinfo(args, report: Report):
    c = require_crypto("`keyinfo`")
    for f in args.files:
        path = named_file(f, "public key file")
        try:
            key, pem_fp, spki_fp = key_fingerprints(path)
        except TooLarge as exc:
            raise InputError(f"{path}: {exc}") from None
        raw = key.public_bytes(c.serialization.Encoding.Raw, c.serialization.PublicFormat.Raw)
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
    for r in results:
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


def verdict_of(report: Report, strict: bool, command: str):
    fails, skips, warns = (report.count(s) for s in ("FAIL", "SKIP", "WARN"))
    verified = sum(1 for r in report.results if r.status == "PASS" and r.check not in NON_EVIDENCE_CHECKS)
    anchored = sum(1 for r in report.results if r.anchored)
    if fails:
        return "FAIL", verified, anchored, "one or more checks FAILED"
    if verified == 0:
        return "INCOMPLETE", verified, anchored, "nothing was verified: no check passed"
    if anchored == 0 and command != "keyinfo":
        return "UNANCHORED", verified, anchored, (
            "internally consistent only: nothing was checked against a key (--trust-key / --public-key) or a "
            "manifest (--manifest) you supplied, so a forger could produce the same result")
    if strict and (skips or warns):
        return "INCOMPLETE", verified, anchored, "--strict: some checks could not be performed or only warned"
    return "PASS", verified, anchored, ""


def emit(report: Report, args, command: str):
    fails, skips, warns, passes = (report.count(s) for s in ("FAIL", "SKIP", "WARN", "PASS"))
    verdict, verified, anchored, why = verdict_of(report, args.strict, command)
    if args.json:
        json.dump({"tool": "lightyear_verify", "version": VERSION, "command": command, "verdict": verdict,
                   "summary": {"pass": passes, "fail": fails, "skip": skips, "warn": warns, "verified": verified,
                               "anchored": anchored},
                   "verdict_reason": why,
                   "results": [r.as_dict() for r in report.results], "notes": report.notes}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for line in render(report.results, verbose=args.verbose, quiet=args.quiet):
            print(line)
        for n in report.notes:
            print(f"NOTE  {n}")
        print("-" * 72)
        print(f"SUMMARY  {passes} passed ({verified} verifying evidence, {anchored} anchored to what you supplied), "
              f"{fails} failed, {skips} skipped, {warns} warnings")
        print(f"VERDICT  {verdict}" + (f" ({why})" if why else ""))
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 3, "UNANCHORED": 3}[verdict]


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    common.add_argument("--strict", action="store_true", help="treat skipped checks and warnings as failure (exit 3)")
    common.add_argument("-v", "--verbose", action="store_true", help="show every individual PASS line")
    common.add_argument("-q", "--quiet", action="store_true", help="show only FAIL/SKIP/WARN lines and the summary")
    common.add_argument("--max-json-mb", type=int, default=DEFAULT_LIMITS.json_bytes >> 20, metavar="MB",
                        help="largest JSON document parsed (default %(default)s)")
    common.add_argument("--max-archive-members", type=int, default=DEFAULT_LIMITS.archive_members, metavar="N",
                        help="most members read from one archive (default %(default)s)")
    common.add_argument("--max-archive-mb", type=int, default=DEFAULT_LIMITS.archive_bytes >> 20, metavar="MB",
                        help="most declared uncompressed bytes in one archive (default %(default)s)")
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
    if min(args.max_json_mb, args.max_archive_members, args.max_archive_mb) < 1:
        print("ERROR: resource limits must be positive", file=sys.stderr)
        return 2
    for stream in (sys.stdout, sys.stderr):  # hostile text must never crash the report
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    _MEMBER_DIGESTS.clear()
    _MEMBER_BYTES[0] = 0
    _Budget.left = None
    global LIMITS
    LIMITS = Limits(json_bytes=args.max_json_mb << 20, archive_members=args.max_archive_members,
                    archive_bytes=args.max_archive_mb << 20)
    report = Report()
    try:
        {"manifest": cmd_manifest, "receipt": cmd_receipt, "decision": cmd_decision,
         "all": cmd_all, "keyinfo": cmd_keyinfo}[args.command](args, report)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"ERROR: cannot read input: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # never let an unexpected error look like a verdict
        print(f"ERROR: internal error, nothing verified: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        return emit(report, args, args.command)
    except Exception as exc:
        print(f"ERROR: could not write the report, nothing claimed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
