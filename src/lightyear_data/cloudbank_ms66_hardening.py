"""Governed, content-addressed compatibility hardening for the MS66 Oracle lane.

The pinned upstream checkout is always validated before use and is never edited.
The reviewed patch is applied only to a fresh, isolated materialization.  This
module deliberately calls that result ``pinned-source-plus-governed-hardening``;
it must never be represented as the exact unchanged upstream application.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

from lightyear_common.io import write_json

from .cloudbank_baseline import (
    PINNED_COMMIT,
    PINNED_ROOT_TREE,
    PINNED_SUBTREE,
    PINNED_SUBTREE_TREE,
    validate_source_checkout,
)
from .contracts import content_hash, seal, sign, verify_signature


RELEASE = "0.66.1"
PATCH_RELATIVE_PATH = Path(
    "factory/cloudbank/whole-application-equivalence/oracle-hardening/source-hardening.patch"
)
PATCH_SHA256 = "4ed3146e86aa172e938cb1b14e1e3cc4d228803f3d71acdb9e813f17a66ae9c2"
MATERIALIZATION_RECEIPT = "oracle-hardening.materialization.json"
SOURCE_IMAGE_LOCK_TYPE = "lightyear-cloudbank-ms66-governed-oracle-source-image-lock"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
IMMUTABLE_IMAGE = re.compile(
    r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}$"
)
BUILD_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SERVICES = (
    "azn-server", "customer", "account", "transfer", "checks", "testrunner",
    "creditscore", "chatbot",
)


def source_identity() -> dict[str, str]:
    return {
        "repository": "https://github.com/oracle/microservices-backend.git",
        "commit": PINNED_COMMIT,
        "root_tree": PINNED_ROOT_TREE,
        "subtree": PINNED_SUBTREE,
        "subtree_tree": PINNED_SUBTREE_TREE,
    }


def hardening_contract() -> dict[str, Any]:
    return seal({
        "schema_version": "1.0",
        "contract_type": "lightyear-cloudbank-ms66-governed-oracle-source-hardening",
        "release": RELEASE,
        "source": source_identity(),
        "patch": {
            "path": PATCH_RELATIVE_PATH.as_posix(),
            "sha256": PATCH_SHA256,
            "format": "git-unified-diff",
            "changed_file_count": 16,
        },
        "changes": [
            {
                "id": "restart-safe-synthetic-seeds",
                "classification": "bounded-compatibility-hardening",
                "reason": "prevent-service-restart-from-truncating-live-journey-fixtures",
            },
            {
                "id": "oracle-aq-message-identity-ledger",
                "classification": "bounded-observability-and-idempotency-hardening",
                "reason": "identify-native-aq-delivery-replay-and-crash-redelivery",
            },
            {
                "id": "account-journal-command-deduplication",
                "classification": "bounded-idempotency-hardening",
                "reason": "suppress-aq-redelivery-double-effect",
            },
            {
                "id": "insufficient-funds-business-rejection",
                "classification": "bounded-api-semantics-hardening",
                "reason": "return-422-without-journal-mutation-and-settle-no-effect-lra-callbacks",
            },
            {
                "id": "isolated-account-service-address",
                "classification": "bounded-deployment-hardening",
                "reason": "make-checks-failure-injection-explicit-and-recoverable",
            },
        ],
        "preserved_native_runtime": {
            "database": "oracle-free",
            "messaging": "oracle-aq-jms",
            "distributed_transactions": "oracle-microtx-lra",
        },
        "source_checkout_mutated": False,
        "materialized_application_identity": "pinned-source-plus-governed-hardening",
        "exact_unchanged_upstream_application": False,
        "production_approved": False,
    })


HARDENING_CONTRACT_SHA256 = hardening_contract()["content_sha256"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        size = path.stat().st_size
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def validate_hardening(project_root: Path) -> list[str]:
    errors: list[str] = []
    patch = project_root / PATCH_RELATIVE_PATH
    if not patch.is_file() or _sha256(patch) != PATCH_SHA256:
        errors.append("cloudbank-ms66-governed-hardening-patch-drift")
        return errors
    text = patch.read_text(encoding="utf-8")
    changed = re.findall(r"^diff --git a/(\S+) b/(\S+)$", text, re.MULTILINE)
    if len(changed) != 16 or any(
        left != right or not left.startswith(PINNED_SUBTREE + "/")
        or ".." in Path(left).parts or Path(left).is_absolute()
        for left, right in changed
    ):
        errors.append("cloudbank-ms66-governed-hardening-path-set-invalid")
    required_markers = (
        "MS66_CHECK_MESSAGES",
        "JOURNAL_COMMAND_KIND_UQ",
        "Idempotency-Key",
        "HttpStatus.UNPROCESSABLE_ENTITY",
        "findJournalForLRAidOrNull",
        "ACCOUNT_BASE_URL",
        "source_checkout_mutated",
    )
    combined = text + json.dumps(hardening_contract(), sort_keys=True)
    if any(marker not in combined for marker in required_markers):
        errors.append("cloudbank-ms66-governed-hardening-control-missing")
    if hardening_contract().get("exact_unchanged_upstream_application") is not False:
        errors.append("cloudbank-ms66-governed-hardening-source-overclaim")
    return sorted(set(errors))


def materialize_hardened_source(
    project_root: Path, source_root: Path, output_root: Path,
) -> tuple[Path, dict[str, Any]]:
    errors = validate_hardening(project_root) + validate_source_checkout(source_root)
    if errors:
        raise ValueError(",".join(sorted(set(errors))))
    resolved_source = source_root.resolve()
    resolved_output = output_root.resolve()
    if resolved_output == resolved_source or resolved_source in resolved_output.parents:
        raise ValueError("cloudbank-ms66-hardening-output-inside-source")
    output_existed = resolved_output.exists()
    if output_existed and (
        not resolved_output.is_dir() or any(resolved_output.iterdir())
    ):
        raise ValueError("cloudbank-ms66-hardening-fresh-output-required")
    resolved_output.mkdir(parents=True, exist_ok=True)
    workspace = resolved_output / PINNED_SUBTREE
    try:
        shutil.copytree(
            resolved_source / PINNED_SUBTREE,
            workspace,
            ignore=shutil.ignore_patterns("target", "*.pyc", "__pycache__"),
        )
        patch = project_root / PATCH_RELATIVE_PATH
        for check_only in (True, False):
            argv = ["git", "apply", "--whitespace=error-all"]
            if check_only:
                argv.append("--check")
            argv.append(str(patch.resolve()))
            result = subprocess.run(
                argv, cwd=resolved_output, capture_output=True, text=True, timeout=60, check=False,
            )
            if result.returncode:
                raise ValueError("cloudbank-ms66-governed-hardening-patch-apply-failed")
    except BaseException:
        if workspace.exists():
            shutil.rmtree(workspace)
        if not output_existed and resolved_output.exists() and not any(resolved_output.iterdir()):
            resolved_output.rmdir()
        raise
    receipt = seal({
        "schema_version": "1.0",
        "receipt_type": "lightyear-cloudbank-ms66-governed-hardening-materialization",
        "release": RELEASE,
        "source": source_identity(),
        "hardening_contract_sha256": HARDENING_CONTRACT_SHA256,
        "patch_sha256": PATCH_SHA256,
        "materialized_tree_sha256": _tree_sha256(workspace),
        "source_checkout_mutated": False,
        "materialized_application_identity": "pinned-source-plus-governed-hardening",
        "exact_unchanged_upstream_application": False,
    })
    write_json(resolved_output / MATERIALIZATION_RECEIPT, receipt)
    return workspace, receipt


def validate_materialization_receipt(receipt: Mapping[str, Any]) -> list[str]:
    expected_fields = {
        "schema_version", "receipt_type", "release", "source",
        "hardening_contract_sha256", "patch_sha256", "materialized_tree_sha256",
        "source_checkout_mutated", "materialized_application_identity",
        "exact_unchanged_upstream_application", "content_sha256",
    }
    errors: list[str] = []
    if set(receipt) != expected_fields:
        errors.append("cloudbank-ms66-hardening-materialization-fields-invalid")
    if receipt.get("receipt_type") != \
            "lightyear-cloudbank-ms66-governed-hardening-materialization" \
            or receipt.get("release") != RELEASE \
            or receipt.get("source") != source_identity():
        errors.append("cloudbank-ms66-hardening-materialization-identity-invalid")
    if receipt.get("content_sha256") != content_hash(dict(receipt)):
        errors.append("cloudbank-ms66-hardening-materialization-content-hash-invalid")
    if receipt.get("hardening_contract_sha256") != HARDENING_CONTRACT_SHA256 \
            or receipt.get("patch_sha256") != PATCH_SHA256 \
            or not HEX_64.fullmatch(str(receipt.get("materialized_tree_sha256", ""))):
        errors.append("cloudbank-ms66-hardening-materialization-binding-invalid")
    if receipt.get("source_checkout_mutated") is not False \
            or receipt.get("materialized_application_identity") != \
            "pinned-source-plus-governed-hardening" \
            or receipt.get("exact_unchanged_upstream_application") is not False:
        errors.append("cloudbank-ms66-hardening-materialization-boundary-invalid")
    return sorted(set(errors))


def build_source_image_lock(
    images: Mapping[str, str], materialization: Mapping[str, Any], *,
    controller_commit: str, cloud_build_id: str, java_base_image: str,
    oracle_runtime_image: str, microtx_runtime_image: str,
    key: str, signer: str,
) -> dict[str, Any]:
    if set(images) != set(SERVICES) or len(set(images.values())) != len(SERVICES) or any(
        not IMMUTABLE_IMAGE.fullmatch(str(images.get(service, ""))) for service in SERVICES
    ):
        raise ValueError("cloudbank-ms66-eight-immutable-source-images-required")
    if validate_materialization_receipt(materialization):
        raise ValueError("cloudbank-ms66-hardening-materialization-invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", controller_commit) \
            or not BUILD_ID.fullmatch(cloud_build_id) \
            or any(not IMMUTABLE_IMAGE.fullmatch(image) for image in (
                java_base_image, oracle_runtime_image, microtx_runtime_image,
            )) or not key or not signer.strip():
        raise ValueError("cloudbank-ms66-source-image-build-provenance-invalid")
    return sign({
        "schema_version": "1.0",
        "lock_type": SOURCE_IMAGE_LOCK_TYPE,
        "release": RELEASE,
        "source": source_identity(),
        "materialized_application_identity": "pinned-source-plus-governed-hardening",
        "exact_unchanged_upstream_application": False,
        "hardening_contract_sha256": HARDENING_CONTRACT_SHA256,
        "hardening_patch_sha256": PATCH_SHA256,
        "hardening_materialization_sha256": materialization["content_sha256"],
        "materialized_tree_sha256": materialization["materialized_tree_sha256"],
        "controller_commit": controller_commit,
        "cloud_build_id": cloud_build_id,
        "java_base_image": java_base_image,
        "native_runtime_images": {
            "oracle": oracle_runtime_image,
            "microtx": microtx_runtime_image,
        },
        "images": [
            {"service": service, "reference": images[service]}
            for service in SERVICES
        ],
        "source_checkout_mutated": False,
        "synthetic_data_only": True,
        "production_environment": False,
    }, key, signer)


def validate_source_image_lock(lock: Mapping[str, Any], key: str) -> list[str]:
    errors: list[str] = []
    expected_fields = {
        "schema_version", "lock_type", "release", "source",
        "materialized_application_identity", "exact_unchanged_upstream_application",
        "hardening_contract_sha256", "hardening_patch_sha256",
        "hardening_materialization_sha256",
        "materialized_tree_sha256", "controller_commit", "cloud_build_id",
        "java_base_image", "native_runtime_images", "images", "source_checkout_mutated",
        "synthetic_data_only", "production_environment", "content_sha256", "signature",
    }
    if set(lock) != expected_fields:
        errors.append("cloudbank-ms66-source-image-lock-fields-invalid")
    if lock.get("lock_type") != SOURCE_IMAGE_LOCK_TYPE or lock.get("release") != RELEASE \
            or lock.get("source") != source_identity():
        errors.append("cloudbank-ms66-source-image-lock-identity-invalid")
    if lock.get("content_sha256") != content_hash(dict(lock)) \
            or not key or not verify_signature(dict(lock), key):
        errors.append("cloudbank-ms66-source-image-lock-signature-invalid")
    signature = lock.get("signature")
    if not isinstance(signature, Mapping) or set(signature) != {"algorithm", "signer", "value"} \
            or not str(signature.get("signer", "")).strip():
        errors.append("cloudbank-ms66-source-image-lock-provenance-invalid")
    rows = lock.get("images") if isinstance(lock.get("images"), list) else []
    if [row.get("service") for row in rows if isinstance(row, Mapping)] != list(SERVICES) \
            or len(rows) != len(SERVICES) or any(
                set(row) != {"service", "reference"}
                or not IMMUTABLE_IMAGE.fullmatch(str(row.get("reference", "")))
                for row in rows if isinstance(row, Mapping)
            ):
        errors.append("cloudbank-ms66-source-image-lock-images-invalid")
    if len({row.get("reference") for row in rows if isinstance(row, Mapping)}) != len(SERVICES):
        errors.append("cloudbank-ms66-source-image-lock-images-invalid")
    for name in (
        "hardening_contract_sha256", "hardening_patch_sha256",
        "hardening_materialization_sha256", "materialized_tree_sha256",
    ):
        if not HEX_64.fullmatch(str(lock.get(name, ""))):
            errors.append(f"cloudbank-ms66-source-image-lock-{name}-invalid")
    if lock.get("hardening_contract_sha256") != HARDENING_CONTRACT_SHA256 \
            or lock.get("hardening_patch_sha256") != PATCH_SHA256 \
            or lock.get("materialized_application_identity") != \
            "pinned-source-plus-governed-hardening" \
            or lock.get("exact_unchanged_upstream_application") is not False \
            or lock.get("source_checkout_mutated") is not False \
            or lock.get("synthetic_data_only") is not True \
            or lock.get("production_environment") is not False:
        errors.append("cloudbank-ms66-source-image-lock-boundary-invalid")
    if not IMMUTABLE_IMAGE.fullmatch(str(lock.get("java_base_image", ""))) \
            or not re.fullmatch(r"[0-9a-f]{40}", str(lock.get("controller_commit", ""))) \
            or not BUILD_ID.fullmatch(str(lock.get("cloud_build_id", ""))):
        errors.append("cloudbank-ms66-source-image-lock-provenance-invalid")
    raw_native = lock.get("native_runtime_images")
    native = raw_native if isinstance(raw_native, Mapping) else {}
    if set(native) != {"oracle", "microtx"} \
            or any(not IMMUTABLE_IMAGE.fullmatch(str(native.get(name, "")))
                   for name in ("oracle", "microtx")):
        errors.append("cloudbank-ms66-source-image-lock-native-runtime-invalid")
    return sorted(set(errors))
