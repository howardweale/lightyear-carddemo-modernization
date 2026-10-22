"""Howard-only, read-only Factory journal verification; prints only the head."""
import argparse
import base64
import hashlib
import json
import sqlite3
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def verified_head(root, public_key):
    pem = Path(public_key).read_bytes()
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Expected Ed25519 public key")
    key_id = hashlib.sha256(pem).hexdigest()
    control = Path(root) / "work/control-tower"
    ownership = json.loads((control / "workspace-ownership.json").read_bytes())
    if ownership != {"scope": "factory", "public_key_sha256": key_id}:
        raise ValueError("Factory ownership/public key mismatch")
    database = control / "scopes/factory/decisions.sqlite3"
    # mode=ro refuses absent databases; retain SQLite WAL handling for a live snapshot.
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    previous = "0" * 64
    count = 0
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        for count, (sequence, raw) in enumerate(connection.execute(
                "SELECT sequence,envelope FROM events ORDER BY sequence"), 1):
            event = json.loads(raw)
            if (sequence != count or type(event.get("sequence")) is not int
                    or event["sequence"] != count or event.get("previous_sha256") != previous
                    or event.get("record_type") != "control-tower-decision-event"
                    or event.get("schema_version") != "1.0"):
                raise ValueError("Journal sequence/type/chain mismatch")
            signature = event["signature"]
            if signature["algorithm"] != "Ed25519" or signature["key_id"] != key_id:
                raise ValueError("Journal signature identity mismatch")
            body = {k: v for k, v in event.items() if k not in {"signature", "content_sha256"}}
            canonical = json.dumps(body, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False, allow_nan=False).encode()
            previous = hashlib.sha256(canonical).hexdigest()
            if event["content_sha256"] != previous:
                raise ValueError("Journal content digest mismatch")
            key.verify(base64.b64decode(signature["value"], validate=True), canonical)
    finally:
        connection.close()
    if not count:
        raise ValueError("Empty journal cannot establish backfill trust")
    return previous


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--public-key", required=True, type=Path)
    args = parser.parse_args()
    try:
        head = verified_head(args.root, args.public_key)
    except Exception:
        # Never echo a journal envelope, file contents, actor or session identifier.
        parser.exit(1, "Factory journal verification refused; inspect privately.\n")
    print(head)
