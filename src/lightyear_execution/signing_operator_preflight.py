"""Validate public operator observations; never access a device or authorize signing.

The integrating attended command must authenticate observations independently,
retain the expected digests outside the report, and consume its durable one-shot
journal before any private operation. A matching report is an assertion check,
not device attestation, signature possession, admission, or native qualification.
No hardware commands, inventory collection, key creation, or signatures occur.
"""
from dataclasses import dataclass
import hashlib

from cryptography.hazmat.primitives import serialization

from .external_signing import SigningRefused, _hex, _json, _pem, _ssh_public
from .signing_operator_payload import (
    OperatorPayload, prepare_operator_payload,
)

MAX_REPORT = 16384
ROLE_LAYOUT = {
    "controller-receipt": ("9c", "Slot 9C (SIGNATURE)"),
    "candidate-commit": ("9a", "Slot 9A (AUTHENTICATION)"),
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _fields(value, expected, reason):
    if type(value) is not dict or set(value) != set(expected):
        raise SigningRefused(reason)


def _same_digest(value, expected, reason):
    if _hex(value, 64) != _hex(expected, 64):
        raise SigningRefused(reason)


@dataclass(frozen=True)
class PublicPreflightMatch:
    """A report match only; callers cannot treat this as signing authority."""

    request_sha256: str
    context_sha256: str
    observation_sha256: str
    designation_sha256: str
    purpose: str
    device_label: str
    piv_slot: str
    canary_ciphertext_sha256: str


def check_operator_preflight(
        prepared, observation, *, expected_observation_sha256,
        expected_designation_sha256, controller_public_key,
        candidate_allowed_signers, expected_canary_plaintext_sha256,
        expected_canary_ciphertext_sha256, expected_preserved_inventory_sha256):
    """Check one canonical, public-only report against independent retained state.

    Both role keys come from the authenticated designation, never from report
    fields. The report is already bound to one retained request/context/purpose.
    The caller must verify report provenance and current owner/session freshness;
    this pure function cannot prove physical state or enforce persistent retries.

    The preserved-inventory digest covers the caller's normalized baseline of
    unchanged settings, age recipients, certificates and other slots. Normalizing
    actual ykman output is outside this module. New 9a/9c ED25519 piv-info entries
    are represented separately, with both certificates still absent (v3).
    """
    if type(prepared) is not OperatorPayload:
        raise SigningRefused("preflight-prepared-payload-required")
    checked = prepare_operator_payload(
        prepared.request, expected_request_sha256=prepared.request_sha256,
        expected_context_sha256=prepared.context_sha256,
        expected_purpose=prepared.purpose,
        designated_public_material=prepared.public_material,
        binding=prepared.binding, window=prepared.window)
    if checked != prepared:
        raise SigningRefused("preflight-prepared-payload-drift")
    if (type(observation) is not bytes or not 0 < len(observation) <= MAX_REPORT
            or _sha(observation) != _hex(expected_observation_sha256, 64)):
        raise SigningRefused("preflight-retained-observation-mismatch")
    report = _json(observation, MAX_REPORT)
    _fields(report, (
        "schema", "request_sha256", "context_sha256", "designation_sha256",
        "purpose", "device_label", "connected_devices", "key_b_state",
        "owner_state", "operation_state", "roles", "canary",
        "preserved_inventory_sha256",
    ), "preflight-report-fields")
    if report["schema"] != "public-signing-operator-preflight/1":
        raise SigningRefused("preflight-report-schema")
    for field, expected in (
            ("request_sha256", prepared.request_sha256),
            ("context_sha256", prepared.context_sha256),
            ("designation_sha256", expected_designation_sha256),
            ("preserved_inventory_sha256", expected_preserved_inventory_sha256)):
        _same_digest(report[field], expected, "preflight-" + field + "-mismatch")
    if report["purpose"] != prepared.purpose:
        raise SigningRefused("preflight-purpose-mismatch")
    if (report["device_label"] != "lightyear-A"
            or report["connected_devices"] != ["lightyear-A"]
            or report["key_b_state"] != "unplugged-no-configuration-writes"
            or report["owner_state"] != "attended-isolated"
            or report["operation_state"] != "unattempted"):
        raise SigningRefused("preflight-owner-device-or-attempt")

    # Compare raw public key bytes: distinct PEM/SSH encodings are NOT proof of
    # distinct role keys. Only public key parsing is performed.
    if type(controller_public_key) is not bytes or type(candidate_allowed_signers) is not bytes:
        raise SigningRefused("preflight-public-designation-required")
    controller = _pem(controller_public_key, _sha(controller_public_key))
    _, candidate = _ssh_public(candidate_allowed_signers, _sha(candidate_allowed_signers))
    raw_format = (serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if controller.public_bytes(*raw_format) == candidate.public_bytes(*raw_format):
        raise SigningRefused("preflight-distinct-role-keys-required")
    designated = {
        "controller-receipt": controller_public_key,
        "candidate-commit": candidate_allowed_signers,
    }
    if prepared.public_material != designated[prepared.purpose]:
        raise SigningRefused("preflight-request-designation-mismatch")
    roles = report["roles"]
    if type(roles) is not list or len(roles) != 2:
        raise SigningRefused("preflight-exact-two-roles-required")
    seen = set()
    for role in roles:
        _fields(role, (
            "purpose", "device_label", "slot", "piv_info_slot", "algorithm",
            "origin", "pin_policy", "touch_policy", "certificate",
            "public_material_sha256",
        ), "preflight-role-fields")
        purpose = role["purpose"]
        if type(purpose) is not str or purpose not in ROLE_LAYOUT or purpose in seen:
            raise SigningRefused("preflight-duplicate-or-unknown-role")
        seen.add(purpose)
        slot, symbolic_slot = ROLE_LAYOUT[purpose]
        if (role["device_label"] != "lightyear-A" or role["slot"] != slot
                or role["piv_info_slot"] != symbolic_slot
                or role["algorithm"] != "ED25519" or role["origin"] != "GENERATED"
                or role["pin_policy"] != "ONCE" or role["touch_policy"] != "ALWAYS"
                or role["certificate"] != "absent"):
            raise SigningRefused("preflight-role-policy")
        _same_digest(role["public_material_sha256"], _sha(designated[purpose]),
                     "preflight-role-public-key-mismatch")
    canary = report["canary"]
    _fields(canary, (
        "plaintext_sha256", "ciphertext_sha256",
        "created_with_all_keys_unplugged", "digest_committed_before_encryption",
        "digest_recorded_on_paper", "digest_sent_to_operator_record",
        "encrypted_to_both_existing_recipients",
        "plaintext_deleted_before_insertion", "b_decryption_sha256",
        "a_before_decryption_sha256", "a_after_decryption_sha256",
    ), "preflight-canary-fields")
    for field in (
            "created_with_all_keys_unplugged", "digest_committed_before_encryption",
            "digest_recorded_on_paper", "digest_sent_to_operator_record",
            "encrypted_to_both_existing_recipients", "plaintext_deleted_before_insertion"):
        if canary[field] is not True:
            raise SigningRefused("preflight-canary-prerequisite")
    _same_digest(canary["ciphertext_sha256"], expected_canary_ciphertext_sha256,
                 "preflight-canary-ciphertext-mismatch")
    for field in ("plaintext_sha256", "b_decryption_sha256",
                  "a_before_decryption_sha256", "a_after_decryption_sha256"):
        _same_digest(canary[field], expected_canary_plaintext_sha256,
                     "preflight-canary-committed-digest-mismatch")
    # The original window is checked both before parsing and immediately before
    # returning. No report timestamp can rebase or extend it.
    prepared.window.check(prepared.binding)
    return PublicPreflightMatch(
        prepared.request_sha256, prepared.context_sha256,
        expected_observation_sha256, expected_designation_sha256,
        prepared.purpose, "lightyear-A", ROLE_LAYOUT[prepared.purpose][0],
        expected_canary_ciphertext_sha256)
