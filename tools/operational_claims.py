"""Incremental operational-prose evidence checks; never executes receipt code.

This is a lexical evidence-link gate, not a natural-language truth verifier.
Unchanged history remains immutable and is reported by the additive audit.
"""
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re
import subprocess
from urllib.parse import unquote, urlsplit


PATTERNS = {
    "installation": r"\b(?:installed|activated|deployed|installation accepted|activation complete)\b",
    "decision": r"\b(?:signed|approved|authorized|accepted)\b",
    "execution": r"\b(?:executed|ran|has run|have run|run completed|verified on z/OS|verified on zOS)\b",
    "ci": r"\b(?:tests? passed|checks? passed|checks? completed successfully|CI passed|CI succeeded)\b",
}
MARKER = re.compile(r"^(?:planned|not yet|not performed|not executed|not installed|not activated|not deployed|not signed|not approved|not authorized|not accepted)\b", re.I)
LINK = re.compile(r"\[[^\]]+\]\(([^\s)]+)\)")
HTML_LINK = re.compile(r'<a\s+[^>]*href=[\"\x27]([^\"\x27]+)[\"\x27]', re.I)
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
PUBLIC = "https://github.com/howardweale/lightyear-carddemo-modernization/"
SCHEMA_KINDS = {
    "factory-first-install-acceptance/1": {"installation"},
    "public-operational-receipt/1": None,
}


class ClaimRefused(ValueError):
    """Fixed diagnostic code; never echo receipt content."""


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL)


def in_scope(path):
    return (path.startswith("docs/") or path == "index.html") and PurePosixPath(path).suffix in {".md", ".html", ".json"}


def units(text):
    """Line-local prose units; fenced executable examples are not assertions.

    Each semicolon/contrast-separated clause needs its own marker/evidence.
    A planned sentence cannot exempt an actual claim later on the same line.
    JSON string values are checked independently; machine keys are not prose.
    """
    fence = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        opening = re.match(r"^(`{3,}|~{3,})", line)
        if opening:
            token = opening.group(1)
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1]:
                fence = None
            continue
        if fence or not line or line.startswith("<!--"):
            continue
        if re.match(r'^"[^"\n]+"\s*:', line):
            try:
                value = json.loads("{" + line.rstrip(",") + "}")
                value = next(iter(value.values()))
                if not isinstance(value, str):
                    continue
                line = value
            except ValueError:
                # Multi-line JSON containers have no complete prose value here.
                continue
        line = re.sub(r"^[#>*\-\d.)\s]+", "", line)
        # Do not split periods inside URLs or decimal numbers.
        for clause in re.split(r";\s*|\s+(?:but|however)\s+|(?<=[.!?])\s+(?=[A-Z])", line):
            plain = LINK.sub("", clause)
            plain = re.sub(r"<[^>]*>", " ", plain).strip(" |")
            categories = sorted(k for k, pattern in PATTERNS.items() if re.search(pattern, plain, re.I))
            if categories:
                yield dict(line=number, text=clause, kinds=categories,
                           planned=bool(MARKER.match(plain)),
                           sha256=sha256(clause.encode("utf-8")).hexdigest())


def public_url(value):
    if not isinstance(value, str) or not value.startswith(PUBLIC):
        raise ClaimRefused("operational-public-url")
    suffix = value[len(PUBLIC):]
    if not re.fullmatch(r"(?:actions/runs/\d+(?:/artifacts/\d+)?|pull/\d+#issuecomment-\d+|issues/\d+#issuecomment-\d+|releases/download/[^/?#]+/[^/?#]+)", suffix):
        raise ClaimRefused("operational-public-url")


def receipt_kinds(payload):
    """Validate public metadata shape, not signatures or present-day authority."""
    try:
        schema = payload["schema"]
        if schema not in SCHEMA_KINDS:
            raise ClaimRefused("operational-receipt-schema")
        if schema == "factory-first-install-acceptance/1":
            if not COMMIT.fullmatch(payload["install_commit"]) or not SHA.fullmatch(payload["bundle_manifest_sha256"]):
                raise ClaimRefused("operational-install-binding")
            if not payload["task"]["name"] or not payload["task"]["account"]:
                raise ClaimRefused("operational-install-binding")
            if payload["listener"]["address"] != "127.0.0.1" or payload["listener"]["count"] != 1:
                raise ClaimRefused("operational-install-binding")
            public_url(payload["public_authority"]["source_url"])
            if not SHA.fullmatch(payload["public_authority"]["journal_head_sha256"]):
                raise ClaimRefused("operational-install-binding")
            # The observation explicitly does not prove a signed acceptance.
            return {"installation"}
        kind = payload["kind"]
        if kind not in PATTERNS or payload["status"] != "completed" or payload["historical_only"] is not True:
            raise ClaimRefused("operational-receipt-kind")
        if not COMMIT.fullmatch(payload["source_commit"]) or not SHA.fullmatch(payload["evidence_sha256"]):
            raise ClaimRefused("operational-receipt-binding")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})", payload["observed_at"]):
            raise ClaimRefused("operational-receipt-time")
        public_url(payload["public_url"])
        if kind == "ci" and ("/actions/runs/" not in payload["public_url"] or payload["conclusion"] != "success"):
            raise ClaimRefused("operational-ci-binding")
        return {kind}
    except ClaimRefused:
        raise
    except (KeyError, TypeError, ValueError):
        raise ClaimRefused("operational-receipt-schema") from None


def receipt_path(document, target):
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.query or not parsed.fragment.startswith("sha256="):
        raise ClaimRefused("operational-receipt-link")
    expected = parsed.fragment[len("sha256="):]
    if not SHA.fullmatch(expected):
        raise ClaimRefused("operational-receipt-digest")
    name = unquote(parsed.path)
    if not name or "\\" in name or ":" in name or name.startswith("/"):
        raise ClaimRefused("operational-receipt-path")
    parts = list(PurePosixPath(document).parent.parts)
    for part in name.split("/"):
        if part == "..":
            if not parts:
                raise ClaimRefused("operational-receipt-path")
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    path = "/".join(parts)
    if not path.startswith("docs/") or not path.endswith(".json"):
        raise ClaimRefused("operational-receipt-path")
    return path, expected


def supported(unit, document, read_blob):
    if unit["planned"]:
        return True
    kinds = set()
    for target in LINK.findall(unit["text"]) + HTML_LINK.findall(unit["text"]):
        if "#sha256=" not in target:
            continue
        path, expected = receipt_path(document, target)
        raw = read_blob(path)
        if len(raw) > 1024 * 1024 or sha256(raw).hexdigest() != expected:
            raise ClaimRefused("operational-receipt-bytes")
        try:
            kinds.update(receipt_kinds(json.loads(raw)))
        except (UnicodeError, ValueError) as exc:
            if isinstance(exc, ClaimRefused):
                raise
            raise ClaimRefused("operational-receipt-json") from None
    return set(unit["kinds"]) <= kinds


def added_lines(patch):
    result, cursor = set(), None
    for line in patch.splitlines():
        header = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if header:
            cursor = int(header.group(1))
        elif cursor is not None:
            if line.startswith("+"):
                result.add(cursor)
                cursor += 1
            elif line.startswith(" "):
                cursor += 1
    return result


def check(root, base):
    changed_names = set(git(root, "diff", "--no-renames", "--name-only", "-z", base, "HEAD").decode("utf-8").split("\0")) - {""}
    present = set(git(root, "ls-tree", "-rz", "--name-only", "HEAD").decode("utf-8").split("\0")) - {""}
    linked = subprocess.run(["git", "grep", "-l", "-z", "-F", "#sha256=", "HEAD", "--", "docs", "index.html"],
                            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    if linked.returncode not in (0, 1):
        raise ClaimRefused("operational-link-inventory")
    linked_names = {p.removeprefix("HEAD:") for p in linked.stdout.decode("utf-8").split("\0") if p}
    def read_blob(path):
        entry = git(root, "ls-tree", "-z", "HEAD", "--", path)
        if not entry.startswith((b"100644 blob ", b"100755 blob ")) or entry.count(b"\0") != 1:
            raise ClaimRefused("operational-receipt-regular-file")
        return git(root, "show", "HEAD:" + path)
    checked = []
    # Recheck an unchanged linked assertion when its receipt changes/disappears.
    # Never allow the link digest to become stale merely because prose is old.
    for name in sorted(n for n in present & (changed_names | linked_names) if in_scope(n)):
        raw = read_blob(name)
        if name not in changed_names and b"#sha256=" not in raw:
            continue
        changed = (added_lines(git(root, "diff", "--no-renames", "--unified=0", base, "HEAD", "--", name).decode("utf-8"))
                   if name in changed_names else set())
        for unit in units(raw.decode("utf-8")):
            dependencies = [receipt_path(name, target)[0] for target in LINK.findall(unit["text"]) + HTML_LINK.findall(unit["text"]) if "#sha256=" in target]
            if unit["line"] not in changed and not changed_names.intersection(dependencies):
                continue
            if not supported(unit, name, read_blob):
                raise ClaimRefused("operational-claim-evidence-required:" + name + ":" + str(unit["line"]))
            checked.append(dict(path=name, line=unit["line"], kinds=unit["kinds"], planned=unit["planned"], sha256=unit["sha256"]))
    return checked


# Immutable historical Windows-1252 files, independently byte/hash reviewed.
# Applies only to additive audit decoding; incremental checks stay strict UTF-8.
LEGACY_AUDIT_CP1252 = {'docs/calibration/idempiere-ms94/stage-b-06/preparation/generated-class-alternative-r2.md': '2f3742ea4fe8c1e5a325d6233c07f40faddbc0dca03e043313dc5d9e4bb06805', 'docs/calibration/idempiere-ms94/stage-b-06/preparation/review-r3/README.md': '4faf27e1e62ad94c3d61d64f357aeb3fccf7dcf135627f0b3f2e1e556f53a840', 'docs/factory/graph-review-r3/README.md': 'e9413fa8823f78a16c08731f4a205486faecfe8b26d88a7907990c79734df35a'}


def audit_text(path, raw):
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        if LEGACY_AUDIT_CP1252.get(path) != sha256(raw).hexdigest():
            raise
        text = raw.decode("cp1252")
        if text.encode("cp1252") != raw:
            raise ClaimRefused("historical-encoding-roundtrip")
        return text, "cp1252"


def audit(root, revision):
    """Additive inventory of old unsupported lexical claims; no exemptions file.

    The caller retains this report once for review. It grants no authority and
    cannot exempt a newly added or changed claim, including a backdated file.
    """
    names = git(root, "ls-tree", "-rz", "--name-only", revision).decode("utf-8").split("\0")
    def read_blob(path):
        entry = git(root, "ls-tree", "-z", revision, "--", path)
        if not entry.startswith((b"100644 blob ", b"100755 blob ")) or entry.count(b"\0") != 1:
            raise ClaimRefused("operational-receipt-regular-file")
        return git(root, "show", revision + ":" + path)
    rows, errors, legacy_decodings = [], [], []
    for path in sorted(n for n in names if n and in_scope(n)):
        try:
            raw = read_blob(path)
            text, encoding = audit_text(path, raw)
            if encoding != "utf-8":
                legacy_decodings.append(dict(path=path, file_sha256=sha256(raw).hexdigest(), encoding=encoding))
            claims = []
            for unit in units(text):
                try:
                    ok = supported(unit, path, read_blob)
                except (ClaimRefused, subprocess.CalledProcessError):
                    ok = False
                if not ok:
                    claims.append({k: unit[k] for k in ("line", "kinds", "sha256")})
            if claims:
                rows.append(dict(path=path, file_sha256=sha256(raw).hexdigest(), claims=claims))
        except (UnicodeError, ClaimRefused, subprocess.CalledProcessError):
            errors.append(dict(path=path, error="source-unavailable"))
    return dict(schema="operational-claim-audit/1", revision=revision, rows=rows,
                unsupported_count=sum(len(r["claims"]) for r in rows), errors=errors, legacy_decodings=legacy_decodings,
                authority_granted=False, scope="lexical claims without a recognized, digest-bound receipt on the same clause")
