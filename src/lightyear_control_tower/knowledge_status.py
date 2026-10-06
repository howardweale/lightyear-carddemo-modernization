"""Read-only signed knowledge status. Optional per-scope host configuration."""

from pathlib import Path
from .requests import read_json, confined
from .decisions import verify_envelope, digest


def read_status(root, scope):
    config = Path(root) / "factory/knowledge-console.json"
    if not config.exists():
        return dict(available=False)
    c = read_json(config)
    if c["scope"] != scope:
        return dict(available=False)
    value = read_json(confined(root, c["status_file"]))
    key = confined(root, c["public_key"]).read_bytes()
    if (
        not verify_envelope(value, key)
        or value.get("schema") != "factory-knowledge-status/1"
        or value.get("scope") != scope
    ):
        raise ValueError("knowledge status signature or scope")
    return dict(
        available=True,
        **{
            k: value[k]
            for k in ("time", "health", "routing", "search", "content_sha256")
        },
    )


def annotation_view(root, item):
    """Fail closed before reflecting proposal text/anchors to any UI route."""
    unavailable = dict(
        annotation_sha256=item["bound"]["annotation"], text_withheld=True
    )
    try:
        c = read_json(Path(root) / "factory/knowledge-console.json")
        if c["scope"] != item["scope"]:
            return unavailable
        a = read_json(confined(root, item["evidence"]["annotation"]))
        certificates = c.get("annotation_certificates", {})
        path = item["evidence"].get("leak_check") or certificates.get(a["id"])
        cert = read_json(confined(root, path))
        key = confined(root, c["judge_public_key"]).read_bytes()
        if (
            not verify_envelope(cert, key)
            or cert["annotation"] != digest(a)
            or cert["eligible"] is not True
            or cert["inventory_sha256"] != c["inventory_sha256"]
        ):
            return unavailable
        return {
            k: a[k]
            for k in (
                "id",
                "anchors",
                "scope",
                "type",
                "text",
                "source",
                "provenance",
                "evidence",
                "review_after",
            )
        }
    except (ValueError, KeyError, OSError, TypeError):
        return unavailable
