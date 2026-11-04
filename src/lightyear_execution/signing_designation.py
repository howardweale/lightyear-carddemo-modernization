"""Public-only designation preparation for the two-signers-on-A custody profile.

No device access, signing, admission, approval authentication or key discovery.
The integrating owner must authenticate the expected digest and revocation
snapshot independently. Human slot declarations are not hardware attestation.
"""
from dataclasses import dataclass
import base64
import hashlib
import re

from cryptography.hazmat.primitives import serialization

from lightyear_control_tower.decisions import canonical
from .external_signing import PRINCIPAL, SigningBinding, SigningRefused, _hex, _json, _pem

SCHEMA = "public-signing-designation/key-a-v1"
ROLES = (("controller-receipt", "9c"), ("candidate-commit", "9a"))
LIMIT = 16 * 1024


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _label(value):
    if (type(value) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._@+-]{0,99}", value)):
        raise SigningRefused("designation-public-label")
    return value


def _artifacts(pem):
    if type(pem) is not bytes:
        raise SigningRefused("designation-public-pem-required")
    key = _pem(pem, _sha(pem))
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ssh = key.public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
    blob = base64.b64decode(ssh.split(b" ")[1], validate=True)
    return raw, ssh, dict(
        pem_sha256=_sha(pem),
        raw_ed25519_sha256=_sha(raw),
        openssh_fingerprint="SHA256:" + base64.b64encode(
            hashlib.sha256(blob).digest()).decode().rstrip("="))


@dataclass(frozen=True)
class PreparedDesignation:
    """Immutable public bytes; this object is not an approval or admission."""

    record: bytes
    controller_public_key: bytes
    candidate_public_key: bytes
    candidate_allowed_signers: bytes

    @property
    def sha256(self):
        return _sha(self.record)


def prepare_designation(controller_public_key, candidate_public_key, *,
                        designation_id, source_commit, work_order_sha256,
                        host_label, custodian, revocation_contact):
    """Prepare an unsigned, source/work-order-scoped public designation.

    Occupancy, policies and canary preservation remain separate human evidence.
    No absent signing keys, preflight result or public signature is fabricated.
    """
    _label(designation_id)
    _hex(source_commit, 40)
    _hex(work_order_sha256, 64)
    for value in (host_label, custodian, revocation_contact):
        _label(value)
    controller_raw, controller_ssh, controller_ids = _artifacts(controller_public_key)
    candidate_raw, candidate_ssh, candidate_ids = _artifacts(candidate_public_key)
    if controller_raw == candidate_raw:
        raise SigningRefused("designation-distinct-role-keys-required")
    allowed = PRINCIPAL.encode() + b" " + candidate_ssh + b"\n"
    role_records = []
    for (role, slot), pem, ssh, identifiers in (
            (ROLES[0], controller_public_key, controller_ssh, controller_ids),
            (ROLES[1], candidate_public_key, candidate_ssh, candidate_ids)):
        role_records.append(dict(
            role=role, device_label="lightyear-A", slot=slot, algorithm="Ed25519",
            pin_policy="ONCE", touch_policy="ALWAYS",
            public_key_pem=pem.decode("ascii"), openssh_public_key=ssh.decode("ascii"),
            **identifiers))
    record = canonical(dict(
        schema=SCHEMA, designation_id=designation_id, source_commit=source_commit,
        work_order_sha256=work_order_sha256, host_label=host_label,
        custodian=custodian, revocation_contact=revocation_contact,
        roles=role_records, candidate_allowed_signers_sha256=_sha(allowed),
        declaration_basis="human-supplied-public-keys-and-proposed-slot-mapping",
        device_attestation=False, preflight_verified=False,
        possession_verified=False, native_qualified=False,
        key_b_role="encryption-only-off-site-backup",
        common_failure_domain="lightyear-A",
        revoke_together=["controller-receipt", "candidate-commit"],
        existing_tower_authority="human-authorization-unchanged"))
    return PreparedDesignation(record, controller_public_key, candidate_public_key, allowed)


def verify_designation(record, *, expected_sha256, expected_designation_id,
                       binding, revoked_raw_key_sha256):
    """Validate bytes against independently authenticated designation state.

    The caller supplies a current authenticated revocation snapshot as a
    frozenset of SHA256(raw Ed25519 public key) identifiers. Either role's
    revocation invalidates this shared-device pair. Historical cryptographic
    verification is separate and is not rejected/erased by this preparation API.
    """
    if type(binding) is not SigningBinding:
        raise SigningRefused("designation-binding-required")
    if (type(record) is not bytes or len(record) > LIMIT
            or _sha(record) != _hex(expected_sha256, 64)):
        raise SigningRefused("designation-digest-mismatch")
    _label(expected_designation_id)
    if type(revoked_raw_key_sha256) is not frozenset:
        raise SigningRefused("explicit-revocation-snapshot-required")
    for key_id in revoked_raw_key_sha256:
        _hex(key_id, 64)
    value = _json(record, LIMIT)
    try:
        if (value["designation_id"] != expected_designation_id
                or value["source_commit"] != binding.source_commit
                or value["work_order_sha256"] != binding.work_order_sha256):
            raise SigningRefused("designation-scope-mismatch")
        roles = value["roles"]
        if type(roles) is not list or len(roles) != 2:
            raise SigningRefused("designation-role-pair-required")
        prepared = prepare_designation(
            roles[0]["public_key_pem"].encode("ascii"),
            roles[1]["public_key_pem"].encode("ascii"),
            designation_id=value["designation_id"],
            source_commit=value["source_commit"],
            work_order_sha256=value["work_order_sha256"],
            host_label=value["host_label"], custodian=value["custodian"],
            revocation_contact=value["revocation_contact"])
    except (KeyError, TypeError, AttributeError, UnicodeError, IndexError) as exc:
        raise SigningRefused("designation-fields") from exc
    # Exact regeneration rejects unknown fields (including secret fields),
    # reordered/swapped roles, altered policies, slots, fingerprints or claims.
    if prepared.record != record:
        raise SigningRefused("designation-noncanonical-profile")
    if any(role["raw_ed25519_sha256"] in revoked_raw_key_sha256 for role in roles):
        raise SigningRefused("designation-shared-device-revoked")
    return prepared


def handoff_parameters(record, *, expected_sha256, expected_designation_id,
                       binding, revoked_raw_key_sha256):
    """Public key arguments for PublicSigningHandoff, after strict validation.

    The integrating owner still supplies the original window/attempt identity,
    verifies actual role designation and revocation freshness, and controls
    admission. No handoff is opened and no production signer is enabled here.
    """
    prepared = verify_designation(
        record, expected_sha256=expected_sha256,
        expected_designation_id=expected_designation_id, binding=binding,
        revoked_raw_key_sha256=revoked_raw_key_sha256)
    return dict(
        designation_sha256=prepared.sha256,
        controller_public_key=prepared.controller_public_key,
        controller_key_sha256=_sha(prepared.controller_public_key),
        candidate_allowed_signers=prepared.candidate_allowed_signers,
        candidate_key_sha256=_sha(prepared.candidate_allowed_signers))
