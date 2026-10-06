"""Closed graph review guidance; toolkit still verifies signer trust independently."""
import re
from .requests import read_json, confined


def projection_review(root, item):
    report = read_json(confined(root, item["evidence"]["leak_check"]))
    lane = read_json(confined(root, item["evidence"]["lane"]))
    if (report.get("schema") != "verify-graph-leak/1" or
            type(report.get("passed")) is not bool or
            not isinstance(report.get("matches"), list) or
            report["passed"] != (not report["matches"]) or
            report.get("projection_sha256") != item["bound"]["projection"] or
            report.get("lane_sha256") != item["bound"]["lane"]):
        raise ValueError("graph-review-report-invalid")
    exceptions = set()
    protected = False
    for match in report["matches"]:
        if (not isinstance(match, dict) or match.get("classification") not in {"source-literal", "protected"} or
                not re.fullmatch(r"[a-f0-9]{64}", match.get("value_sha256", ""))):
            raise ValueError("graph-review-match-invalid")
        if match["classification"] == "protected":
            protected = True
        else:
            exceptions.add("source-literal:" + match["value_sha256"])
    return dict(public_fixture_only=lane.get("public_fixture_only") is True,
                customer_id=lane.get("customer_id"),
                eligible=not protected and lane.get("public_fixture_only") is True
                         and lane.get("customer_id") == "carddemo-reference",
                protected_matches=protected,
                required_acknowledgments=sorted(exceptions),
                expires_at="00:00 UTC on review_after",
                expiry_effect="Judge refuses submissions; toolkit removes graph tools.")


def validate_approval(root, item, payload):
    if payload["outcome"] != "approved":
        return  # Rejection never grants graph access.
    review = projection_review(root, item)
    if not review["eligible"]:
        raise ValueError("Graph projection has protected matches or an unsupported lane")
    tokens = set(payload["reason"].split())
    if not set(review["required_acknowledgments"]) <= tokens:
        raise ValueError("Acknowledge every public-source hash in the reason")
