"""Offline unsigned F8 preparation checks. Never signs, exports, or runs a model."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from lightyear_execution.contracts import ExecutionPolicy
from lightyear_factory.contracts import WorkOrder, canonical_hash

ROOT = Path(__file__).resolve().parents[1]
RECORD = "docs/factory/copau-f2-preparation-2026-10-22/request.json"
WINDOW = {"start": "2026-10-30T08:00:00-07:00", "end": "2026-10-30T20:00:00-07:00"}
MODEL = {"provider": "openai-responses", "model": "gpt-5.4-2026-03-05"}
SHA = re.compile(r"[0-9a-f]{64}")
WRITE_ROOT = "factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/authorization"


def require(value, code):
    if not value:
        raise ValueError(code)


def bound_bytes(root, binding):
    require(set(binding) == {"path", "sha256"}, "binding-shape")
    path = binding["path"]
    require(isinstance(path, str) and path.startswith("docs/factory/")
            and all(part not in {"", ".", ".."} for part in path.split("/"))
            and "\\" not in path and ":" not in path, "public-record-path")
    require(isinstance(binding["sha256"], str) and SHA.fullmatch(binding["sha256"]), "binding-hash")
    target = Path(root) / path
    require(target.resolve().is_relative_to(Path(root).resolve()), "public-record-root")
    cursor = target
    while cursor != Path(root):
        require(not cursor.is_symlink() and not getattr(cursor, "is_junction", lambda: False)(), "record-link")
        cursor = cursor.parent
    require(target.is_file() and target.stat().st_size <= 262144, "record-size")
    raw = target.read_bytes()
    require(sha256(raw).hexdigest() == binding["sha256"], "record-digest")
    return raw


def public_fingerprint(pem):
    # SHA-256 of exact published PEM bytes, also parse and require the Tower key type.
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    require(isinstance(pem, bytes) and 0 < len(pem) <= 4096
            and pem.startswith(b"-----BEGIN PUBLIC KEY-----"), "tower-public-pem")
    require(isinstance(load_pem_public_key(pem), Ed25519PublicKey), "tower-key-type")
    return sha256(pem).hexdigest()


def review(request, root=ROOT, public_pem=None):
    """Return readiness only after real final plan/contract files have been bound."""
    require(request["schema"] == "copau-f2-preparation/1", "request-schema")
    require(request["scope"] == "first-copau-factory-run"
            and request["g3_included"] is False, "first-run-only")
    require(request["window"] == WINDOW and request["timezone"] == "America/Los_Angeles", "window")
    require(request["roles"] == {r: MODEL for r in ("planner", "builder", "analyst")}, "roles")
    require(type(request["request_ready"]) is bool and request["run_authorized"] is False, "unsigned-preparation")
    order = WorkOrder.from_dict(request["work_order"])
    require(order.to_dict() == request["work_order"], "work-order-roundtrip")
    require(order.allowed_paths == (WRITE_ROOT,) and order.max_attempts == 3
            and order.max_model_calls == 8 and order.max_model_cost_usd == 10
            and order.max_elapsed_seconds == 28800 and not order.allow_network, "order-caps")
    require(order.max_model_tokens == 1100000 and order.max_model_input_bytes == 400000, "token-budget")
    require(order.baseline_first and len(order.gates) == 1
            and not order.gates[0].expose_output_to_builder, "worker-gates")
    refs = request["bindings"]
    require(set(refs) == {"scope", "freeze", "workspace", "retention", "image", "policy_basis", "evidence"}, "input-set")
    inputs = {name: json.loads(bound_bytes(root, row)) for name, row in refs.items()}
    require(len(inputs["workspace"]) == 403, "workspace-count")
    require(all(isinstance(p, str) and isinstance(h, str) and SHA.fullmatch(h)
                for p, h in inputs["workspace"].items()), "workspace-hashes")
    require(inputs["retention"]["workspace_files"] == 403
            and inputs["retention"]["capsule_files"] == 380, "retention")
    policy = deepcopy(request["execution_policy"])
    require(policy["runtime"]["image"] == inputs["image"]["selection"]["image"]
            and policy["runtime"]["image_digest"] == inputs["image"]["selection"]["image_digest"], "image-pin")
    pending = []
    keys = policy["admission"]["trusted_key_ids"]
    if not keys:
        pending.append("Howard: provisioned work-order trust key IDs and public custody record (distinct from Tower PEM)")
        # Parser-only shape check. Never emitted, designated, signed or admitted.
        policy["admission"]["trusted_key_ids"] = ["schema-validation-only"]
    else:
        require(isinstance(keys, list) and len(set(keys)) == len(keys)
                and all(isinstance(k, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}", k) for k in keys), "trust-ids")
    basis = deepcopy(inputs["policy_basis"]["proposed_policy_fields"])
    basis.update(id="lightyear:copau:first-run")
    basis["runtime"].update(image=policy["runtime"]["image"], image_digest=policy["runtime"]["image_digest"])
    basis["admission"].update(trusted_key_ids=policy["admission"]["trusted_key_ids"], max_ttl_seconds=28800)
    require(policy == basis, "policy-basis")
    parsed = ExecutionPolicy.from_dict(policy)
    require(parsed.to_dict() == policy and parsed.max_work_order_ttl_seconds == 28800, "policy-roundtrip")
    cap = "work/f8-public-worker-capsule"
    command = ["mvn", "-o", "-B", "-ntp", "-C", "-s", cap + "/settings.xml",
               "-gs", cap + "/settings.xml", "-f", cap + "/pom.xml",
               "-Dmaven.repo.local=/tmp/factory-build/" + cap + "/m2",
               "-Duser.home=/tmp/factory-build/" + cap + "/home", "test"]
    require(list(order.gates[0].command) == command and order.gates[0].timeout_seconds == 3600, "offline-command")
    estimate = request["estimate"]
    require(estimate["input_usd_per_million"] == 5.5
            and estimate["output_usd_per_million"] == 24.75
            and estimate["max_output_tokens_per_call"] == 25000
            and estimate["automatic_retries"] == 0, "estimate-rates")
    reserve_input = 2 * order.max_model_input_bytes + order.max_model_calls * 1024
    reserve_output = order.max_model_calls * estimate["max_output_tokens_per_call"]
    cost = (reserve_input * 5.5 + reserve_output * 24.75) / 1000000
    require(estimate["reserved_input_tokens"] == reserve_input
            and estimate["reserved_output_tokens"] == reserve_output
            and estimate["reserved_cost_microusd"] == round(cost * 1000000)
            and cost <= 10, "estimate-arithmetic")
    tower = request["operator"]["tower"]
    require(set(tower) == {"pem_sha256", "journal_head_sha256", "source"}, "tower-fields")
    if public_pem is None or not tower["pem_sha256"]:
        pending.append("Howard: public PEM and its confirmed SHA-256 fingerprint")
    else:
        require(public_fingerprint(public_pem) == tower["pem_sha256"], "tower-fingerprint-mismatch")
    if not tower["journal_head_sha256"] or not tower["source"]:
        pending.append("Howard: current journal head and public provenance")
    else:
        require(SHA.fullmatch(tower["journal_head_sha256"]) is not None, "journal-head")
    private = request["operator"]["private_expected_values"]
    require(set(private) == {"sha256", "size_bytes", "count", "source"}, "private-metadata-only")
    if any(private[k] is None for k in ("sha256", "size_bytes", "count")) or not private["source"]:
        pending.append("Howard: private expected-bundle digest, size and count only")
    else:
        require(isinstance(private["sha256"], str) and SHA.fullmatch(private["sha256"])
                and type(private["size_bytes"]) is int and 1 <= private["size_bytes"] <= 262144
                and type(private["count"]) is int and 1 <= private["count"] <= 64, "private-binding")
    config = request["model_config"]
    require(config == {"default": "copau", "models": {"copau": {
        "provider": "openai", "model": MODEL["model"], "input_usd_per_million": 5.5,
        "output_usd_per_million": 24.75, "max_output_tokens": 25000}}}, "model-config")
    final = request["final_binding"]
    if final is None:
        pending.append("Engineering: additive final policy/WorkOrder/plan/contract and exact executable binding after operator inputs")
    else:
        validate_final(request, final, root)
    require(request["request_ready"] == (not pending), "readiness-claim")
    return {"schema": "copau-f2-review/1", "request_ready": not pending,
            "run_authorized": False, "pending": pending,
            "reserved_cost_microusd": round(cost * 1000000)}


def validate_final(request, final, root):
    """Validate actual unsigned runtime records; no Tower inbox or proof is accessed."""
    from lightyear_control_tower.factory_policy import validate_contract
    require(set(final) == {"plan", "contract", "work_order", "execution_policy", "model_config"}, "final-fields")
    data = {name: json.loads(bound_bytes(root, ref)) for name, ref in final.items()}
    require(data["work_order"] == request["work_order"]
            and data["execution_policy"] == request["execution_policy"]
            and data["model_config"] == request["model_config"], "final-runtime-bytes")
    order = WorkOrder.from_dict(data["work_order"])
    ExecutionPolicy.from_dict(data["execution_policy"])
    plan, contract = data["plan"], data["contract"]
    validate_contract(contract, root)
    require(contract["kind"] == "engineering-run-approval" and contract["program"] == "factory", "final-kind")
    require(plan["schema"] == "factory-build-plan/1"
            and plan["content_sha256"] == canonical_hash(plan, {"content_sha256"})
            and plan["work_order_sha256"] == order.content_sha256, "final-plan")
    require(plan["roles"] == request["roles"] and plan["model_config"] == final["model_config"], "final-roles")
    expected_inputs = {k: request["bindings"][k] for k in ("scope", "freeze", "workspace")}
    expected_inputs["execution_policy"] = final["execution_policy"]
    require(plan["bound_inputs"] == expected_inputs, "final-inputs")
    require(plan["private_expected_values"] == {k: request["operator"]["private_expected_values"][k]
            for k in ("sha256", "size_bytes", "count")}, "final-private")
    caps = {"max_attempts": 3, "max_repair_loops": 2, "max_elapsed_seconds": 28800,
            "max_model_calls": 8, "max_model_tokens": 1100000, "cost_cap_microusd": 10000000}
    require(plan["caps"] == caps and contract["details"]["caps"] == caps
            and contract["details"]["window"] == WINDOW
            and contract["details"]["request_seal"] == plan["content_sha256"], "final-seal")
    require(plan["executable_commit"] == contract["details"]["executable_commit"], "final-executable")
    import subprocess
    def git(*args):
        return subprocess.check_output(["git", "--no-optional-locks", *args], cwd=root)
    executable = plan["executable_commit"]
    require(re.fullmatch(r"[0-9a-f]{40}", executable), "executable-sha")
    git("merge-base", "--is-ancestor", executable, "HEAD")
    require(not git("status", "--porcelain=v1", "--untracked-files=all"), "final-clean-checkout")
    allowed = {row["path"] for row in final.values()}
    allowed.add(request["record_path"])
    changed = set(filter(None, git("diff", "--name-only", executable, "HEAD").decode().splitlines()))
    require(changed <= allowed, "final-executable-changed")
    sources = {row["path"]: row for row in contract["sources"]}
    require(set(expected_inputs[name]["path"] for name in expected_inputs) <= set(sources), "final-source-set")
    for row in contract["sources"]:
        raw = bound_bytes(root, {k: row[k] for k in ("path", "sha256")})
        require(git("show", row["commit"] + ":" + row["path"]) == raw, "final-source-commit")
    for name, row in request["engineering_source_bindings"].items():
        require(sha256(git("show", executable + ":" + row["path"])).hexdigest() == row["sha256"], "engineering-source")
    expected = request["engineering_source_bindings"]
    require(contract["details"]["observer_sha256"] == expected["observer"]["sha256"]
            and contract["details"]["class_hashes"] == {k: v["sha256"] for k, v in expected.items() if k != "observer"}, "observer-class-binding")
    require(plan["operator_trust"] == request["operator"]["tower"], "final-operator-binding")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", default=RECORD)
    parser.add_argument("--public-pem")
    args = parser.parse_args()
    pem = Path(args.public_pem).read_bytes() if args.public_pem else None
    result = review(json.loads((ROOT / args.record).read_bytes()), public_pem=pem)
    print(json.dumps(result, indent=2))
