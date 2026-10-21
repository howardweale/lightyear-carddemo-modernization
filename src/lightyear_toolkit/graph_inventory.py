"""Full projection scan for operator-side acceptance; never send watch values to MCP."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import re

from lightyear_factory.contracts import ContractError
from lightyear_factory.isolation_scan import (
    scan, _decoded_views, _normalized, MAX_BYTES, MAX_DEPTH, MAX_VIEWS,
)

def encoded(raw):
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def scan_inventory(projection, *, canaries, protected_values, projection_sha256):
    """Scan every member, including unknown extensions. No tool-result sampling."""
    if not re.fullmatch("[0-9a-f]{64}", projection_sha256):
        raise ValueError("graph-projection-hash")
    if not isinstance(projection, dict) or not projection.get("nodes"):
        raise ValueError("graph-inventory-empty")
    if not isinstance(projection.get("edges"), list):
        raise ValueError("graph-inventory-edges")
    if len(encoded(projection)) > 64 * 1024 * 1024:
        raise ContractError("isolation-scan-limit")
    rows = []
    for key, value in sorted(projection.items()):
        values = value if isinstance(value, list) and value else [value]
        for index, item in enumerate(values):
            # Names contain no untrusted node ids, text, or watch values.
            name = sha256(key.encode()).hexdigest() + "/" + str(index)
            rows.append((name, encoded({key: item})))
    protected_values = tuple(protected_values)
    if any(not isinstance(v, str) or not v or len(v.encode()) > MAX_BYTES for v in protected_values):
        raise ValueError("graph-watch-values")
    result = scan(rows, canaries, protected_values)
    # L10's expected-output window is 40 characters. Verify's record fields may
    # be shorter; apply exact normalized matching to the same bounded decoded views.
    short = {_normalized(v) for v in protected_values if len(v) < 40}
    short.discard("")
    for _, raw in rows:
        pending = [(raw.decode("utf-8"), 0)]
        seen = set()
        total = 0
        while pending:
            view, depth = pending.pop()
            if view in seen:
                continue
            seen.add(view)
            total += len(view.encode("utf-8"))
            if len(seen) > MAX_VIEWS or total > MAX_BYTES * 4:
                raise ContractError("isolation-scan-limit")
            if any(v in _normalized(view) for v in short):
                raise ContractError("isolation-breach")
            try:
                for child in _decoded_views(view):
                    if child != view and child not in seen:
                        if depth >= MAX_DEPTH or len(pending) >= MAX_VIEWS:
                            raise ContractError("isolation-scan-limit")
                        pending.append((child, depth + 1))
            except UnicodeError:
                raise ContractError("isolation-scan-encoding") from None
    return dict(
        schema="verify-graph-inventory-scan/1",
        observed_at=datetime.now(timezone.utc).isoformat(),
        status="passed", projection_sha256=projection_sha256,
        inventory_sha256=sha256(encoded(result["scanned"])).hexdigest(),
        records_scanned=len(rows), nodes=len(projection["nodes"]),
        edges=len(projection["edges"]),
        source_excerpts=sum(len(n.get("source", [])) for n in projection["nodes"]),
        guidance_records=len(projection.get("annotations", [])),
        all_projection_members_scanned=True, scanner=result["normalization"],
        short_protected_values_scanned=True, model_calls=0,
    )
