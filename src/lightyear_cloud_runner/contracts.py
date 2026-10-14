"""Fail-closed GCP admission with portable content and signature contracts.

This produces a plan, not an execution authorization. Phase 2 must implement the
atomic cloud claim and observed-resource checks before using any create API.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

from .signing import canonical, require, seal, sha256, verify

HEX = r"[0-9a-f]{64}"
SCOPES = {"engineering", "qualification", "factory"}


def timestamp(value: str) -> datetime:
    require(isinstance(value, str) and value.endswith("Z"), "Timestamp must be UTC with Z")
    result = datetime.fromisoformat(value[:-1] + "+00:00")
    return result


def fields(value: dict, expected: str) -> None:
    require(isinstance(value, dict) and set(value) == set(expected.split()), "Unexpected/missing fields")


def hash_value(value: str) -> None:
    require(isinstance(value, str) and bool(re.fullmatch(HEX, value)), "Invalid SHA-256")


def object_ref(ref: dict, bucket: str) -> None:
    fields(ref, "bucket name generation sha256 size")
    hash_value(ref["sha256"])
    require(ref["bucket"] == bucket, "Cross-account/bucket input refused")
    require(ref["name"] == "sha256/" + ref["sha256"], "Input must be content-addressed")
    require(isinstance(ref["generation"], str) and bool(re.fullmatch(r"[1-9][0-9]*", ref["generation"])),
            "An immutable object generation is required")
    require(type(ref["size"]) is int and ref["size"] >= 0, "Invalid object size")


def verify_object(ref: dict, bucket: str, generation: str, data: bytes) -> None:
    object_ref(ref, bucket)
    require(generation == ref["generation"], "Fetched generation differs")
    require(len(data) == ref["size"] and sha256(data) == ref["sha256"], "Fetched input bytes differ")


def admission(request: dict, go: dict, witness: dict, policy: dict, now: datetime) -> dict:
    """Public policy must be reviewed/pinned outside the submitted request bundle."""
    fields(policy, "project bucket region zones machine_types images commits keys min_memory_gib min_disk_gib max_seconds max_witness_age_seconds")
    require(now.tzinfo is not None, "Use an aware clock")
    require(set(policy["keys"]) == SCOPES, "All three trust scopes are required")
    fingerprints = []
    for keys in policy["keys"].values():
        fields(keys, "go witness")
        fingerprints.extend(sha256(pem.encode()) for pem in keys.values())
    require(len(set(fingerprints)) == 6, "Go/witness and scope authorities must be distinct")
    for key in ("min_memory_gib", "min_disk_gib", "max_seconds", "max_witness_age_seconds"):
        require(type(policy[key]) is int and policy[key] > 0, "Invalid policy limit")
    fields(request, "schema attempt_id scope commit project data_project region zone machine_type image containers inputs memory_witness not_before deadline max_seconds")
    require(request["schema"] == "lightyear.cloud-request.v1", "Unknown request schema")
    require(bool(re.fullmatch(r"[a-z][a-z0-9-]{0,49}", request["attempt_id"])), "Invalid attempt ID")
    scope = request["scope"]
    require(scope in SCOPES, "Unknown request scope")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", request["commit"])) and request["commit"] in policy["commits"],
            "Unreviewed commit")
    require(request["project"] == request["data_project"] == policy["project"],
            "Customer data and execution must stay in the approved project")
    require(request["region"] == policy["region"] and request["zone"] in policy["zones"]
            and request["zone"].startswith(request["region"] + "-"), "Region/zone differs")
    require(request["machine_type"] in policy["machine_types"], "Unapproved machine type")
    fields(request["image"], "project name id build_manifest_sha256")
    require(request["image"]["project"] == policy["project"], "Image must be copied into the approved project")
    require(bool(re.fullmatch(r"[1-9][0-9]*", request["image"]["id"])), "Numeric image ID required")
    require(bool(re.fullmatch(r"[a-z][-a-z0-9]{0,61}[a-z0-9]", request["image"]["name"])), "Invalid image name")
    hash_value(request["image"]["build_manifest_sha256"])
    require(request["image"] in policy["images"], "Unreviewed image identity/build manifest")
    require(isinstance(request["containers"], list) and len(request["containers"]) > 0, "No container pins")
    require(len(set(request["containers"])) == len(request["containers"]), "Duplicate container pin")
    for image in request["containers"]:
        require(bool(re.fullmatch(r"[a-z0-9][a-z0-9./:_-]*@sha256:" + HEX, image)), "Container must be pinned by digest")
    require(isinstance(request["inputs"], list) and len(request["inputs"]) > 0, "No immutable inputs")
    for ref in request["inputs"] + [request["memory_witness"]]:
        object_ref(ref, policy["bucket"])
    require(len({ref["name"] for ref in request["inputs"]}) == len(request["inputs"]), "Duplicate inputs")
    start, end = timestamp(request["not_before"]), timestamp(request["deadline"])
    require(start <= now < end, "Outside the signed launch window")
    duration = request["max_seconds"]
    require(type(duration) is int and 0 < duration <= policy["max_seconds"], "Attempt duration exceeds policy")
    require((end - now).total_seconds() >= duration, "Too late for the full bounded attempt")
    witness_bytes = canonical(witness)
    require(sha256(witness_bytes) == request["memory_witness"]["sha256"]
            and len(witness_bytes) == request["memory_witness"]["size"], "Witness object binding differs")
    measured = verify(witness, policy["keys"][scope]["witness"])
    fields(measured, "purpose scope provider project region machine_type image observed_at free_memory_gib free_disk_gib")
    require(measured["purpose"] == "cloud-memory-witness" and measured["provider"] == "gcp",
            "A new GCP memory witness is required; laptop witness does not transfer")
    for key in ("scope", "project", "region", "machine_type", "image"):
        require(measured[key] == request[key], "Memory witness configuration differs: " + key)
    age = (now - timestamp(measured["observed_at"])).total_seconds()
    require(0 <= age <= policy["max_witness_age_seconds"], "Memory witness is stale or future-dated")
    for metric, limit in (("free_memory_gib", "min_memory_gib"), ("free_disk_gib", "min_disk_gib")):
        require(type(measured[metric]) in (int, float) and measured[metric] >= policy[limit], "Insufficient cloud " + metric)
    accepted = verify(go, policy["keys"][scope]["go"])
    fields(accepted, "purpose scope request_sha256 attempt_id commit not_before deadline")
    require(accepted["purpose"] == "cloud-run-go" and accepted["request_sha256"] == seal(request),
            "Go does not authorize this request")
    for key in ("scope", "attempt_id", "commit", "not_before", "deadline"):
        require(accepted[key] == request[key], "Go binding differs: " + key)
    return {"schema": "lightyear.cloud-launch-plan.v1", "mode": "plan-only",
            "request_sha256": seal(request), "policy_sha256": seal(policy),
            "go_sha256": seal(go), "attempt_id": request["attempt_id"],
            "project": request["project"], "zone": request["zone"],
            "claim": {"bucket": policy["bucket"], "name": "attempts/" + request["attempt_id"],
                      "ifGenerationMatch": 0},
            "instance": {"name": "ly-" + request["attempt_id"], "machine_type": request["machine_type"],
                         "image": request["image"], "max_seconds": duration,
                         "external_ip": False, "automatic_restart": False},
            "validated_at": now.astimezone(timezone.utc).isoformat(),
            "execution_enabled": False}


def cleanup_observation(attempt_id: str, project: str, instance_id: str,
                        expected_disks: list[str], pages: list[dict], operation: dict) -> dict:
    """Require complete instance+disk inventory after a successful delete.

    An API error, partial success, missing page or ambiguous deletion stays open.
    The eventual adapter must fetch every page in both inventories freshly.
    """
    require(operation.get("status") == "DONE" and not operation.get("error"), "Delete operation incomplete")
    require(operation.get("operationType") == "delete"
            and operation.get("targetId") == instance_id and operation.get("project") == project,
            "Delete operation identity differs")
    deleted_at = timestamp(operation["completed_at"])
    require(set(page["kind"] for page in pages) == {"instances", "disks"}, "Both inventories required")
    require(len(expected_disks) == len(set(expected_disks)), "Duplicate disk identity")
    for kind in ("instances", "disks"):
        group = [page for page in pages if page["kind"] == kind]
        token = ""
        for page in group:
            require(page["project"] == project and page["request_page_token"] == token
                    and not page.get("unreachable") and not page.get("warnings"), "Incomplete provider inventory")
            require(timestamp(page["observed_at"]) >= deleted_at, "Inventory predates deletion")
            for item in page["items"]:
                require(item.get("attempt_id") != attempt_id, "Attempt resource still present")
                require(not (kind == "instances" and str(item["id"]) == instance_id), "VM still present")
                require(not (kind == "disks" and str(item["id"]) in expected_disks), "Disk still present")
            token = page["next_page_token"]
            require(token or page is group[-1], "Inventory chain ended before its last page")
        require(token == "", "Provider inventory has unconsumed pages")
    return {"purpose": "cloud-cleanup-observation", "attempt_id": attempt_id, "project": project,
            "instance_id": instance_id, "disk_ids": expected_disks,
            "provider_observation_sha256": seal({"pages": pages, "operation": operation}),
            "claim": "Provider inventory observation; not independent attestation",
            "cleanup_complete": True}
