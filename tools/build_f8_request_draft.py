"""Retain unsigned F2 drafts and their byte hashes in CI; no private input."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from lightyear_factory.contracts import WorkOrder
from tools.check_f8_request import RECORD, ROOT, review

OUTPUT = ROOT / "work/f8-unsigned-request"
PREREQUISITES = "docs/factory/copau-f2-prerequisites-2026-10-22.md"


def main():
    request = json.loads((ROOT / RECORD).read_bytes())
    result = review(request)
    order = WorkOrder.from_dict(request["work_order"])
    OUTPUT.mkdir(parents=True, exist_ok=False)
    files = {}

    def emit(name, value):
        raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
        (OUTPUT / name).write_bytes(raw)
        files[name] = {"bytes": len(raw), "sha256": sha256(raw).hexdigest()}

    head = subprocess.check_output(
        ["git", "--no-optional-locks", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    emit("execution-policy.draft.json", request["execution_policy"])
    emit("work-order.json", order.to_dict())
    emit("model-config.json", request["model_config"])
    emit("estimate.json", request["estimate"])
    emit("review.json", result)
    emit("unsigned-bindings.json", {
        "schema": "copau-f2-unsigned-draft-bindings/1",
        "publication_commit": head,
        "request": {"path": RECORD, "sha256": sha256((ROOT / RECORD).read_bytes()).hexdigest()},
        "private_prerequisites": {
            "path": PREREQUISITES,
            "sha256": sha256((ROOT / PREREQUISITES).read_bytes()).hexdigest(),
        },
        "scope": request["scope"], "g3_included": request["g3_included"],
        "roles": request["roles"], "window": request["window"],
        "timezone": request["timezone"],
        "work_order_sha256": order.content_sha256,
        "bound_inputs": request["bindings"],
        "engineering_source_bindings": request["engineering_source_bindings"],
        "operator": request["operator"], "final_binding": request["final_binding"],
        "request_ready": result["request_ready"], "run_authorized": False,
        "execution_policy_trust_unbound": not bool(request["execution_policy"]["admission"]["trusted_key_ids"]),
        "limitation": "Unadmitted draft; operator trust/private metadata and final sealed records remain pending.",
    })
    emit("manifest.json", {
        "schema": "copau-f2-ci-draft-manifest/1", "publication_commit": head,
        "request_ready": result["request_ready"], "run_authorized": False,
        "files": dict(files), "self_excluded": True,
    })
    for name, row in files.items():
        raw = (OUTPUT / name).read_bytes()
        assert len(raw) == row["bytes"] and sha256(raw).hexdigest() == row["sha256"]
    print(json.dumps({"head": head, "request_ready": result["request_ready"],
                      "output": "work/f8-unsigned-request", "files": files}, sort_keys=True))


if __name__ == "__main__":
    main()
