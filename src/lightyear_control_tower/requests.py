"""Read-only scope-confined request inbox, with exact byte-hash evidence bindings."""

import hashlib
import json
import re
from pathlib import Path
from .decisions import canonical, digest, text_field

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_BYTES = 8 * 1024 * 1024


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value) or value in {".", ".."}:
        raise ValueError("Invalid scoped identifier")
    return value


def confined(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Invalid evidence path")
    p = Path(relative)
    if (
        p.is_absolute()
        or any(part in {"..", "."} for part in p.parts)
        or ":" in relative
    ):
        raise ValueError("Evidence path escaped scope")
    target = root / p
    if any(x.is_symlink() for x in (target, *target.parents) if x != root.parent):
        raise ValueError("Symbolic evidence paths are forbidden")
    if not target.resolve().is_relative_to(root):
        raise ValueError("Evidence path escaped scope")
    return target


def read_bytes(path):
    with Path(path).open("rb") as stream:
        value = stream.read(MAX_BYTES + 1)
    if len(value) > MAX_BYTES:
        raise ValueError("Evidence exceeds size bound")
    return value


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    return json.loads(
        read_bytes(path),
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
    )


class RequestInbox:
    def __init__(self, root, scope, registry):
        self.root = Path(root).resolve()
        self.scope = identifier(scope)
        self.registry = registry
        self.directory = self.root / "work/control-tower/requests" / self.scope

    def item(self, request_id):
        name = identifier(request_id)
        path = confined(
            self.root, f"work/control-tower/requests/{self.scope}/{name}.json"
        )
        value = read_json(path)
        if not isinstance(value, dict):
            raise ValueError("Request must be a JSON object")
        if (
            value.get("schema") != "tower-request/1"
            or value.get("scope") != self.scope
            or value.get("id") != name
        ):
            raise ValueError("Request scope or schema mismatch")
        kind = self.registry.get(value.get("kind"))
        bound, evidence = value.get("bound", {}), value.get("evidence", {})
        if (
            not isinstance(bound, dict)
            or not isinstance(evidence, dict)
            or "request" in bound
            or not set(kind.hashes) <= set(bound)
            or set(evidence) != set(bound)
        ):
            raise ValueError("Incomplete evidence bindings")
        for key, sha in bound.items():
            if not isinstance(sha, str) or not SHA.fullmatch(sha):
                raise ValueError("Invalid evidence hash")
            if (
                hashlib.sha256(
                    read_bytes(confined(self.root, evidence[key]))
                ).hexdigest()
                != sha
            ):
                raise ValueError("Evidence hash mismatch")
        text_field(value.get("summary"), "Summary")
        proposed = text_field(value.get("proposed_by"), "Proposer", 200)
        identifier(proposed)
        authors = value.get("authored_by", [])
        if not isinstance(authors, list) or len(authors) > 100:
            raise ValueError("Invalid author list")
        for author in authors:
            identifier(author)
        # The request envelope is itself bound, including summary, proposer and field policy.
        public = {
            k: value[k]
            for k in (
                "schema",
                "scope",
                "id",
                "kind",
                "evidence",
                "summary",
                "proposed_by",
                "authored_by",
                "workload",
                "created_at_utc",
                "requested_by",
            )
            if k in value
        }
        return {
            **public,
            "bound": {**bound, "request": digest(value)},
            "status": "pending",
            "proposed_by": proposed,
            "kind_version": kind.version,
            "item_sha256": digest(value),
        }

    def queue(self):
        result = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                result.append(self.item(path.stem))
            except (ValueError, OSError, KeyError, TypeError):
                # Never reflect an invalid foreign-scope request's contents or paths.
                result.append(
                    {
                        "id": path.stem,
                        "scope": self.scope,
                        "status": "invalid",
                        "reason_code": "request-evidence-invalid",
                        "decidable": False,
                    }
                )
        return result
