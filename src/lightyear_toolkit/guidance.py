"""Read only the annotation slice of an already approved graph projection."""

from datetime import datetime, timezone, date
from lightyear_control_tower.decisions import canonical


def guidance(projection, roots, *, now=None, cap=4096, include_inferred=False):
    roots = set(roots)
    ids = {n["id"] for n in projection["nodes"]}
    if not roots <= ids:
        raise ValueError("guidance roots outside projection")
    parents = set(roots)
    while True:
        more = {
            e["source"]
            for e in projection["edges"]
            if e["relation"] == "CONTAINS" and e["target"] in parents
        }
        if more <= parents:
            break
        parents |= more
    today = (now or datetime.now(timezone.utc)).date()
    rows = []
    for a in projection.get("annotations", []):
        if (
            a["provenance"]
            not in (
                {"verified", "asserted", "inferred"}
                if include_inferred
                else {"verified", "asserted"}
            )
            or a["visibility"] != "implementer"
            or date.fromisoformat(a["review_after"]) <= today
            or a["customer_id"] != projection["customer_id"]
            and not a["portable"]
            or not set(a["anchors"]) <= ids
        ):
            continue
        if set(a["anchors"]) & (roots if a["scope"] == "node" else parents):
            rows.append(a)
    rows.sort(
        key=lambda a: (
            ("node", "subtree", "workload", "customer").index(a["scope"]),
            {"verified": 0, "asserted": 1, "inferred": 2}[a["provenance"]],
            -a["outcome_strength"],
            a["id"],
        )
    )
    result = dict(items=[], truncated=False)
    for row in rows:
        if len(canonical(dict(items=[*result["items"], row], truncated=True))) > cap:
            result["truncated"] = True
            break
        result["items"].append(row)
    return result
