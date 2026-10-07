"""Read only the annotation slice of an already approved graph projection."""

from datetime import datetime, timezone, date
from lightyear_control_tower.decisions import canonical


def guidance(projection, roots, *, now=None, cap=4096, include_inferred=False, revocations=None):
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
    if projection.get('annotations') and revocations is None:
        raise ValueError('live revocation channel required for guidance')
    revoked=revocations.read() if revocations is not None else set()
    below={r:0 for r in roots}
    todo=list(roots);children={}
    for e in projection['edges']:
        if e['relation']=='CONTAINS':children.setdefault(e['source'],[]).append(e['target'])
    for n in todo:
        for child in children.get(n,[]):
            if child not in below:below[child]=below[n]+1;todo.append(child)
    rows = []
    for a in projection.get("annotations", []):
        if (
            a['id'] in revoked or
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
        eligible=(set(below) if a['type']=='pitfall' else roots) if a['scope']=='node' else parents
        if set(a["anchors"]) & eligible:
            rows.append(a)
    rows.sort(
        key=lambda a: (
            min((below.get(n,1000000) for n in a['anchors']),default=1000000),
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
