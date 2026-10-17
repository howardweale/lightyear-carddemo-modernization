"""Dated, hash-bound scope decisions; prose is only a consistency tripwire."""
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SCOPES = {"twin-and-zos", "host-compiler-scoped"}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_decisions(root=ROOT):
    paths = sorted((root/"docs/factory").glob("claim-scope-decisions-*.json"))
    if not paths:
        return {"arguments": [], "acceptances": []}
    value = json.loads(paths[-1].read_bytes())
    if digest({k:v for k,v in value.items() if k != "content_sha256"}) != value["content_sha256"]:
        raise ValueError("claim-scope-decision-hash")
    for kind in ("arguments", "acceptances"):
        seen = set()
        for row in value[kind]:
            key = (row["id"], row["record_sha256"], row["source_sha256"])
            if key in seen or row["claim_scope"] not in SCOPES:
                raise ValueError("claim-scope-decision-inventory")
            seen.add(key)
    return value


def declared_scope(records, identifier, record, source):
    matches = [r for r in records if (r["id"], r["record_sha256"], r["source_sha256"]) ==
               (identifier, digest(record), source)]
    return matches[0]["claim_scope"] if len(matches) == 1 else None


def check_consistency(argument, scope):
    text = argument.get("argument", "")
    host = bool(argument.get("compiler_storage_semantics") or argument.get("compiler_runtime_contract"))
    host |= bool(re.search(r"not (?:native )?z/OS(?!-specific)|host CEE3ABD terminating shim", text))
    if host and scope != "host-compiler-scoped":
        raise ValueError("claim-scope-host-semantics-unclassified")
