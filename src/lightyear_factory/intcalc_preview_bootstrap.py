"""C2 attended controller. Proposal only; no authority is supplied by this module.

The fixed CLI has live and no-spend rehearsal entries. Live use still requires
reviewed code, green CI, machine evidence and independent attended approval.
A public hash is an integrity join, not an authenticated Howard approval.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import os
import argparse
import getpass
import hashlib
import hmac
import secrets
import warnings
import shutil
from pathlib import Path
import platform
import sys
import time

from lightyear_factory import intcalc_preview_admission as a
from lightyear_factory import intcalc_preview_composition as c
from lightyear_factory import intcalc_preview_transport as t
from lightyear_factory import intcalc_preview_build_gate as b
from lightyear_factory import intcalc_preview_ledger_volume as v

DERIVED = {'status': 'DERIVED_AFTER_HOWARD_APPROVAL'}
SCOPE = 'NOT-P5/public-CBACT04C-only'
STATE_ORDER = ('OFFLINE', 'AUTHENTICATED', 'EVIDENCE_VERIFIED', 'SECRET_RECEIVED',
               'NONCE_CONSUMED', 'TRANSPORT_READY', 'RUNNING', 'TERMINAL')


class BootstrapRefused(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise BootstrapRefused(code)


def clone(value):
    return c.strict_json(c.canonical(value))


def intent_for(packet):
    c.validate_packet(packet)
    result = clone(packet)
    result['binding_sha256'] = clone(DERIVED)
    for key in ('exact_run_approval', 'spend_authority'):
        result['prerequisites'][key] = clone(DERIVED)
    return result


def validate_intent(intent, mode='LIVE'):
    if mode == 'REHEARSAL':
        return validate_rehearsal_intent(intent)
    require(mode == 'LIVE', 'intent-mode')
    probe = clone(intent)
    require(probe.get('binding_sha256') == DERIVED, 'intent-binding-marker')
    probe['binding_sha256'] = '0' * 64
    for key in ('exact_run_approval', 'spend_authority'):
        require(probe['prerequisites'][key] == DERIVED, 'intent-authority-marker')
        probe['prerequisites'][key] = {'status': 'PRESENT', 'evidence_sha256': '0' * 64}
    c.validate_packet(probe)
    require(not c.prepare(probe)['missing'], 'intent-prerequisite')
    return c.digest(c.canonical(intent))


def approval_record(intent, record, expected_hash, now):
    """expected_hash is supplied by the attended human channel, not the packet."""
    intent_hash = validate_intent(intent, record.get('mode'))
    fields = {'schema', 'intent_sha256', 'scope', 'cap_microdollars', 'count_billing_known',
              'account_billing_evidence_sha256', 'issued_at', 'expires_at', 'qualified',
              'production_controller_receipt', 'local_config_sha256', 'qualification_sha256', 'mode'}
    require(type(record) is dict and set(record) == fields, 'approval-fields')
    require(c.is_hash(expected_hash) and c.digest(c.canonical(record)) == expected_hash, 'attended-approval-join')
    require(record['schema'] == 'full-intcalc-attended-approval/2' and record['intent_sha256'] == intent_hash
            and record['scope'] == SCOPE and type(record['cap_microdollars']) is int
            and record['mode'] in ('LIVE', 'REHEARSAL')
            and record['cap_microdollars'] == (c.CAP if record['mode'] == 'LIVE' else 0)
            and (record['count_billing_known'] is True if record['mode'] == 'LIVE' else record['count_billing_known'] is False)
            and c.is_hash(record['local_config_sha256']) and c.is_hash(record['qualification_sha256'])
            and (c.is_hash(record['account_billing_evidence_sha256']) if record['mode'] == 'LIVE'
                 else record['account_billing_evidence_sha256'] is None)
            and record['qualified'] is False and record['production_controller_receipt'] is False, 'approval-scope')
    issued, expires = a._timestamp(record['issued_at']), a._timestamp(record['expires_at'])
    require(now.tzinfo is not None and issued <= now < expires
            and 0 < (expires - issued).total_seconds() <= 1800, 'approval-freshness')
    return intent_hash


def bindings_for(intent, approval, *, issued_at, nonce, admission_expires_at):
    """Pure public derivation; does not issue an envelope or create a key."""
    validate_intent(intent)
    mapping = {'controller_source_manifest_sha256': 'controller_source_manifest_sha256',
               'C1_gate_manifest_sha256': 'gate_manifest_sha256', 'model_context_sha256': 'context_sha256',
               'model_allowlist_sha256': 'allowlist_sha256', 'case_manifest_sha256': 'case_manifest_sha256',
               'budget_policy_sha256': 'budget_policy_sha256', 'feedback_schema_sha256': 'feedback_schema_sha256',
               'named_feedback_limit_sha256': 'named_limit_sha256', 'byte_policy_sha256': 'byte_policy_sha256'}
    result = {left: intent[right] for left, right in mapping.items()}
    result.update(work_order_sha256=c.digest(c.canonical(intent)), operator_approval_sha256=c.digest(c.canonical(approval)),
                  runtime_image_digest='sha256:' + intent['runtime_manifest_sha256'],
                  build_toolchain_digest='sha256:' + intent['toolchain_manifest_sha256'],
                  model_snapshot_sha256=c.digest(t.MODEL.encode('utf-8')), preview_policy_sha256=a.POLICY_SHA256,
                  run_budget_seconds=8100, issued_at=issued_at, nonce=nonce, admission_expires_at=admission_expires_at)
    return a._bindings(result)


def final_packet(intent, record, bindings):
    expected = bindings_for(intent, record, issued_at=bindings['issued_at'], nonce=bindings['nonce'],
                            admission_expires_at=bindings['admission_expires_at'])
    require(bindings == expected, 'binding-map')
    result = clone(intent)
    result['binding_sha256'] = c.digest(a._canonical(bindings))
    for key in ('exact_run_approval', 'spend_authority'):
        result['prerequisites'][key] = {'status': 'PRESENT', 'evidence_sha256': c.digest(c.canonical(record))}
    c.validate_packet(result)
    require(intent_for(result) == intent, 'intent-reconstruction')
    return result


def verify_evidence(packet, evidence):
    """All non-authority receipts must be the exact bytes in the authenticated intent.

    This verifies integrity only. Receipt semantics/qualification are a separate
    mandatory fixed-module prerequisite; PRESENT is never used as authentication.
    """
    names = set(c.PREREQUISITES) - {'exact_run_approval', 'spend_authority'}
    require(type(evidence) is dict and set(evidence) == names, 'evidence-set')
    for name, raw in evidence.items():
        require(type(raw) is bytes and len(raw) <= 4 * 1024 * 1024
                and c.digest(raw) == packet['prerequisites'][name]['evidence_sha256'], 'evidence-hash')
        c.strict_json(raw)


def artifact_valid(value, schema):
    require(type(schema) is dict and type(schema.get('properties')) is dict, 'artifact-schema')
    keys = set(schema['properties'])
    require(keys in ({'text'}, {'source'}) and schema.get('required') == list(keys)
            and schema.get('additionalProperties') is False and type(value) is dict and set(value) == keys,
            'artifact-shape')
    key = next(iter(keys))
    text = value[key]
    require(type(text) is str and 0 < len(text.encode('utf-8')) <= (65536 if key == 'source' else 8192)
            and not any(ord(ch) < 32 and ch not in '\t\r\n' for ch in text), 'artifact-content')
    return True


BASE_CONFIG_FIELDS = frozenset(('use_parent', 'run_parent', 'build_parent', 'docker_binary',
    'endpoint', 'docker_config', 'disk_receipt_path', 'verifier_binding', 'verifier_binding_sha256',
    'gate_source_sha256', 'source_root', 'source_manifest_path', 'public_fixture_path',
    'public_fixture_sha256', 'outside_sync_and_candidate_roots'))
LIVE_CONFIG_FIELDS = BASE_CONFIG_FIELDS | {'public_context_path', 'public_allowlist_path'}
REHEARSAL_REQUIRED = frozenset(('exact_implementations_green', 'operator_rehearsal_procedure',
    'public_fixture_review', 'attended_image_pull', 'daemon_inspection', 'verifier_freeze_review'))
REHEARSAL_HASHES = frozenset(('controller_source_manifest_sha256', 'gate_manifest_sha256',
    'case_manifest_sha256', 'runtime_manifest_sha256', 'runtime_config_sha256',
    'toolchain_manifest_sha256', 'javac_sha256', 'jar_sha256', 'public_fixture_sha256'))
SOURCE_FILES = ('src/carddemo_oracle/__init__.py', 'src/carddemo_oracle/compare.py', 'src/carddemo_oracle/records.py', 'src/lightyear_common/__init__.py', 'src/lightyear_common/io.py', 'src/lightyear_common/trust.py', 'src/lightyear_factory/__init__.py', 'src/lightyear_factory/intcalc_preview_admission.py', 'src/lightyear_factory/intcalc_preview_bootstrap.py', 'src/lightyear_factory/intcalc_preview_build_gate.py', 'src/lightyear_factory/intcalc_preview_build_gate_worker.py', 'src/lightyear_factory/intcalc_preview_composition.py', 'src/lightyear_factory/intcalc_preview_ledger_volume.py', 'src/lightyear_factory/intcalc_preview_transport.py', 'src/lightyear_mainframe/__init__.py', 'src/lightyear_mainframe/intcalc_candidate_gate.py', 'src/lightyear_mainframe/public_dataset_diff.py', 'src/lightyear_mainframe/records.py', 'src/lightyear_mainframe/source.py', 'src/lightyear_mainframe/zos_bindings.py', 'tests/fixtures/intcalc-c1/Main.java')
PUBLIC_REFUSAL_CODES = ('absolute-child-reap-deadline', 'absolute-child-reap-unconfirmed', 'absolute-command-deadline', 'absolute-result-late', 'absolute-runtime-binding', 'absolute-runtime-incomplete', 'absolute-validation-deadline', 'actual-volume-lease-required', 'admission-binding', 'admission-deadline', 'admission-ledger-required', 'admission-validity-mismatch', 'admission-volume-stale-or-used', 'admit-once', 'apfs-required', 'approval-already-consumed', 'approval-fields', 'approval-freshness', 'approval-scope', 'approved-binding-hash-required', 'archive-invalid', 'archive-inventory', 'archive-member', 'archive-partial', 'archive-size', 'artifact-c0', 'artifact-content', 'artifact-contract', 'artifact-drift', 'artifact-schema', 'artifact-schema-binding', 'artifact-shape', 'artifact-utf8', 'artifact-validator-required', 'attempt-record', 'attempt-stopped-after-fault', 'attended-approval-join', 'attended-terminal-required', 'authenticated-placement-required', 'authority-not-authenticated', 'binding-fields', 'binding-hashes', 'binding-map', 'binding-schema-or-source', 'bound-file-hash', 'bound-java-entrypoint', 'bounded-binary-input-required', 'bounded-regular-file-required', 'budget-fixed-input-cap', 'budget-policy-mismatch', 'build-artifact-join', 'build-directory-exists', 'build-failed-no-retry', 'build-or-cleanup-fault', 'build-order', 'build-platform-toolchain-join', 'build-status-type', 'builder-not-paused', 'c2-fixed-docker-only', 'candidate-output-not-frozen', 'cap-shortage', 'capture-not-closed', 'case-codec-date', 'case-dd-inventory', 'case-kind', 'case-timestamp', 'child-group-reap-unconfirmed', 'child-reap-deadline', 'child-reap-unconfirmed', 'cleanup-deadline', 'clock-or-process', 'clock-regressed', 'closed-source-inventory', 'collector-mount-boundary', 'command-deadline', 'command-late', 'command-output-cap', 'compile-feedback-bytes', 'compile-feedback-fields', 'compile-result-joins', 'compiler-diagnostic-capture', 'compiler-exit-marker', 'compiler-exit-proof', 'compiler-exit-readback', 'compiler-terminal-fault', 'complete-case-inventory-required', 'complete-gate-inventory', 'complete-verdict-inventory', 'composition-stopped-no-resume', 'configuration-inputs', 'configuration-placement', 'container-boundary', 'container-boundary-not-observed', 'container-cleanup-unconfirmed', 'context-allowlist-schema', 'context-archive-size', 'context-compression', 'context-duplicate-member', 'context-encrypted-member', 'context-exact-member-set', 'context-member-count', 'context-member-hash', 'context-member-metadata', 'context-member-name', 'context-member-size', 'context-nonregular-member', 'context-total-size', 'count-object', 'count-phase-deadline', 'credential-already-consumed', 'credential-format', 'credential-id', 'credential-memory-only', 'credential-size', 'daemon-native-arm64', 'daemon-platform', 'disk-image-platform', 'disk-observation-cleanup', 'disk-observation-create', 'disk-observation-exit', 'disk-receipt-already-exists', 'distinct-ledger-parents-required', 'docker-config-already-exists', 'docker-config-not-empty', 'docker-daemon-platform-mismatch-emulation-refused', 'docker-daemon-platform-unknown', 'docker-disk-approval-window', 'docker-disk-headroom', 'docker-disk-output', 'docker-disk-raw-join', 'docker-disk-receipt', 'docker-disk-receipt-join', 'docker-executable', 'docker-operation', 'duplicate-field', 'duplicate-field-path', 'duplicate-json-key', 'duplicate-record-key', 'e2-projection-bound', 'empty-case', 'endpoint-not-allowed', 'envelope-fields', 'envelope-size', 'evidence-hash', 'evidence-set', 'exact-command-binding', 'exact-pins', 'exact-public-input-required', 'exclusive-create-not-enforced', 'executed-bootstrap-location', 'explicit-byte-policy', 'explicit-supported-ebcdic-codec-required', 'explicit-supported-runtime-platform-required', 'feedback-binding', 'feedback-counts', 'feedback-fields', 'feedback-limit-mismatch', 'feedback-mismatch', 'field-layout-drift', 'file-changed', 'file-kind', 'file-size', 'filesystem-fields', 'filesystem-identity', 'fixed-budget', 'fixed-cap', 'fixed-ports', 'fixed-public-fixture', 'fixed-record-binding-required', 'fixed-record-framing', 'fixed-run-deadline', 'float-json-forbidden', 'float-or-nonfinite-json', 'frozen-case-crosscheck-required', 'frozen-oracle-binding', 'fstatfs-failed', 'full-sync-unavailable', 'fullfsync-failed', 'fullfsync-unavailable', 'gate-artifact-join', 'gate-binding-join', 'gate-cleanup', 'gate-failed-no-retry', 'gate-or-cleanup-fault', 'gate-order', 'gate-result-joins', 'gate-source', 'gate-source-join', 'generation-hold-exceeded', 'generation-phase-deadline', 'hand-oracle-finding', 'host-disk-headroom', 'http-status-failure', 'image-digest-platform-store', 'image-inspect-shape', 'image-store-binding', 'immutable-runtime-image-required', 'incomplete-or-failed-response', 'incomplete-reasoning', 'infrastructure-capture-overflow', 'inline-proof-rule-binding', 'input-size', 'input-usage-exceeds-bound', 'intent-authority-marker', 'intent-binding-marker', 'intent-mode', 'intent-prerequisite', 'intent-reconstruction', 'interactive-tty-required', 'invalid-binding-digest', 'invalid-detail-limit', 'invalid-envelope-json', 'invalid-json', 'invalid-nonce', 'invalid-public-context-archive', 'invalid-response-json', 'invalid-runtime-digest', 'invalid-timestamp', 'invalid-use-identity', 'io-refused', 'jdk-image-platform-digest', 'job-and-snapshot-maps-required', 'json-size', 'late-result', 'lease-process-or-closed', 'ledger-consumed-or-uncertain', 'ledger-exclusive-or-durability-fault', 'ledger-owner-mode', 'ledger-parent-owner-mode', 'ledger-placement', 'ledger-process-changed', 'ledger-record-name', 'ledger-short-write', 'ledger-volume-join', 'linked-ledger-parent', 'linked-path', 'live-authority', 'loaded-project-module-location', 'local-config-fields', 'local-docker-only', 'local-endpoint', 'local-evidence-join', 'local-image-missing', 'local-volume-required', 'machine-binding', 'missing-prerequisite', 'mode-binding', 'monotonic-clock-invalid', 'named-byte-policy-attempt', 'named-byte-policy-binding', 'named-byte-policy-expired', 'named-byte-policy-scope-required', 'native-arm64-required', 'native-controller-required', 'native-macos-arm64-required', 'non-artifact-output', 'non-candidate-fault', 'non-integer-number', 'nonfinite-json', 'normalization-governance', 'not-p5-required', 'one-complete-artifact-required', 'operator-binding-mismatch', 'original-deadline', 'original-deadline-expired', 'original-deadline-reached-during-admission', 'original-deadline-required', 'output-item', 'output-missing', 'outside-admission-window', 'owner-mode', 'packet-fields', 'packet-hashes', 'packet-schema', 'parent-components', 'parent-io-failed', 'parent-path-rebound', 'partial-fixed-record', 'phase-clock', 'phase-deadline', 'phase-expired', 'phase-response-or-deadline', 'phase-type', 'pinned-parent-drift', 'placement-filesystem', 'placement-parent-identity', 'policy-mismatch', 'posix-required', 'pre-count-proof-missing', 'pre-count-proof-violated', 'pre-count-refused-no-reservation', 'preflight-refused', 'preparation-inputs', 'preparation-mode', 'prerequisite-evidence', 'prerequisite-fields', 'prerequisite-inventory', 'preview-admission-required', 'preview-cannot-qualify', 'preview-identity-mismatch', 'preview-only', 'preview-scope-mismatch', 'probe-capability-required', 'probe-file-kind', 'probe-id', 'probe-io-failed', 'probe-late-no-admission', 'probe-readback', 'probe-short-write', 'process-changed', 'projection-fields', 'projection-hash-size', 'projection-types', 'public-bundle-hash', 'public-carddemo-job-required', 'public-carddemo-source-drift', 'public-context-join', 'public-fixture-build', 'public-fixture-counts', 'public-fixture-join', 'public-input-hash', 'qualification-fields', 'qualified-evidence-required', 'qualified-live-bootstrap-not-supplied', 'qualified-receipt-join', 'reasoning-usage-missing', 'record-bytes', 'record-count-limit', 'regular-public-input', 'rehearsal-authority', 'rehearsal-evidence', 'rehearsal-intent-fields', 'rehearsal-prerequisites', 'rehearsal-scope', 'relative-public-path-required', 'request-fixed-role', 'request-role-order', 'resolved-parent-required', 'resolved-path-required', 'resource-absence-unconfirmed', 'resource-count', 'resource-name', 'resource-record', 'resource-record-name', 'resource-removal-join', 'resource-remove', 'response-size', 'result-attempt-count', 'result-binding', 'result-budget-policy', 'result-cost', 'result-failed-role-terminal', 'result-fault', 'result-fields', 'result-limits', 'result-observations', 'result-outcome-join', 'result-role-order', 'result-role-prefix', 'result-roles', 'result-status', 'reviewed-public-context', 'reviewed-request-proof', 'reviewed-request-required', 'role-consumed-or-stopped', 'role-instructions-drift', 'role-or-cap', 'run-budget-mismatch', 'run-deadline-or-process', 'run-directory-exists', 'run-id', 'session-consumed', 'short-write', 'signature-format', 'signature-invalid', 'slot-failed-consumed-no-retry', 'snapshot-inventory-mismatch', 'snapshot-or-flex-mismatch', 'source-content-drift', 'source-contract', 'source-drift', 'source-inventory', 'source-join', 'source-manifest-join', 'spend-and-billing-authority-required', 'spend-cap', 'statfs-abi', 'step-dd-key-required', 'store-specific-image-id', 'strict-case-binding', 'successful-build-contract', 'synchronized-parent', 'timestamp-offset-required', 'toolchain-hashes', 'transport-budget-policy', 'transport-evidence', 'transport-once', 'unexpected-output', 'unknown-role', 'unsafe-gate-result', 'unsafe-verdict', 'unsupported-dataset-mode', 'unsupported-use-store-platform', 'usage-missing', 'usage-total-mismatch', 'use-store-owner-mode', 'use-store-short-write', 'use-store-unavailable-or-uncertain', 'verifier-binding', 'verifier-binding-join', 'volume-changed', 'volume-flags', 'wall-clock-invalid', 'wire-absolute-timeout', 'wire-cleanup-unconfirmed', 'wire-response', 'wire-send-uncertain', 'worker-arguments', 'worker-failed', 'worker-late', 'worker-operation', 'worker-request-hash', 'worker-result')
PROOF_RULE = {'schema': 'full-intcalc-inline-request-proof/1',
    'projection': 'merged canonical UTF-8 serializer', 'rule': 'len(canonical(projection)) + 4096',
    'before_count_send': True, 'role_caps': c.ROLE_INPUT_CAPS,
    'named_limit': c.NAMED_BUDGET_LIMIT, 'budget_policy_sha256': c.BUDGET_POLICY_SHA256}
PROOF_RULE_SHA256 = c.digest(c.canonical(PROOF_RULE))


def native():
    require(os.name == 'posix' and sys.platform == 'darwin' and platform.machine() == 'arm64',
            'native-controller-required')


def read_json(path):
    return c.strict_json(b.read_file(path, 4 * 1024 * 1024))


def validate_rehearsal_intent(intent):
    fields = REHEARSAL_HASHES | {'schema', 'prerequisites', 'runtime_platform', 'byte_policy_sha256'}
    require(type(intent) is dict and set(intent) == fields
            and intent['schema'] == 'full-intcalc-rehearsal-intent/1'
            and all(c.is_hash(intent[k]) for k in REHEARSAL_HASHES), 'rehearsal-intent-fields')
    require(intent['runtime_platform'] == 'linux/arm64' and intent['byte_policy_sha256'] == 'STRICT',
            'rehearsal-scope')
    rows = intent['prerequisites']
    require(type(rows) is dict and set(rows) == REHEARSAL_REQUIRED, 'rehearsal-prerequisites')
    for row in rows.values():
        require(type(row) is dict and set(row) == {'status', 'evidence_sha256'}
                and row['status'] == 'PRESENT' and c.is_hash(row['evidence_sha256']), 'rehearsal-evidence')
    return c.digest(c.canonical(intent))


def rehearsal_packet(intent, approval_hash):
    validate_rehearsal_intent(intent)
    # Structural adapter envelope only. All live prerequisites remain MISSING;
    # unused model fields are constants, never assertions of spend/admission.
    packet = {k: '0' * 64 for k in c.HASH_FIELDS}
    packet.update({k: intent[k] for k in REHEARSAL_HASHES if k in c.HASH_FIELDS})
    packet.update(schema='full-intcalc-composition-packet/1', binding_sha256=approval_hash,
        controller_platform='darwin/arm64', runtime_platform='linux/arm64', emulation=False,
        byte_policy_sha256='STRICT', run_budget_seconds=8100, cap_microdollars=c.CAP,
        context_sha256=c.CONTEXT_HASH, allowlist_sha256=c.ALLOWLIST_HASH,
        feedback_schema_sha256=c.FEEDBACK_HASH, named_limit_sha256=c.LIMIT_HASH,
        budget_policy_sha256=c.BUDGET_POLICY_SHA256,
        prerequisites={k: {'status': 'MISSING', 'evidence_sha256': None} for k in c.PREREQUISITES})
    b.pins(packet)
    return packet


def source_check(config, intent):
    root = b.safe_path(config['source_root'], directory=True)
    raw = b.read_file(config['source_manifest_path'], 128 * 1024)
    require(c.digest(raw) == intent['controller_source_manifest_sha256'], 'source-manifest-join')
    record = c.strict_json(raw)
    require(type(record) is dict and set(record) == {'schema', 'files'}
            and record['schema'] == 'full-intcalc-controller-source/1'
            and type(record['files']) is dict and set(record['files']) == set(SOURCE_FILES)
            and bool(SOURCE_FILES), 'closed-source-inventory')
    require(Path(__file__).resolve() == root / 'src/lightyear_factory/intcalc_preview_bootstrap.py',
            'executed-bootstrap-location')
    for name, module in tuple(sys.modules.items()):
        if name.startswith(('lightyear_', 'carddemo_oracle')) and getattr(module, '__file__', None):
            require(Path(module.__file__).resolve().is_relative_to(root / 'src'), 'loaded-project-module-location')
    for name, digest in record['files'].items():
        require(c.is_hash(digest) and c.digest(b.read_file(root / name, 2 * 1024 * 1024)) == digest,
                'source-content-drift')


def docker_prefix(config):
    binary = b.safe_path(config['docker_binary'])
    empty = b.safe_path(config['docker_config'], directory=True, owner=True)
    require(not any(empty.iterdir()), 'docker-config-not-empty')
    require(os.access(binary, os.X_OK) and type(config['endpoint']) is str
            and config['endpoint'].startswith('unix:///')
            and not any(ch.isspace() for ch in config['endpoint']), 'local-docker-only')
    return [str(binary), '--config', str(empty), '--host', config['endpoint']]


def qualify_record(intent, config, record, approval):
    mode = approval['mode']
    fields = LIVE_CONFIG_FIELDS if mode == 'LIVE' else BASE_CONFIG_FIELDS
    require(type(config) is dict and set(config) == fields
            and config['outside_sync_and_candidate_roots'] is True, 'local-config-fields')
    require(c.digest(c.canonical(config)) == approval['local_config_sha256']
            and c.digest(c.canonical(record)) == approval['qualification_sha256'], 'local-evidence-join')
    fields = {'schema', 'intent_sha256', 'checks', 'receipts', 'disk_receipt_sha256',
              'endpoint_sha256', 'controller_source_manifest_sha256',
              'gate_source_sha256', 'public_fixture_sha256', 'image_store', 'image_ids'}
    require(type(record) is dict and set(record) == fields
            and record['schema'] == 'full-intcalc-machine-qualification/2'
            and record['intent_sha256'] == validate_intent(intent, mode), 'qualification-fields')
    required = (set(c.PREREQUISITES) - {'spend_authority', 'exact_run_approval'}
                if mode == 'LIVE' else REHEARSAL_REQUIRED)
    require(set(record['checks']) == required and all(x is True for x in record['checks'].values())
            and set(record['receipts']) == required, 'qualified-evidence-required')
    for name in required:
        require(record['receipts'][name] == intent['prerequisites'][name]['evidence_sha256'], 'qualified-receipt-join')
    require(record['controller_source_manifest_sha256'] == intent['controller_source_manifest_sha256']
            and record['gate_source_sha256'] == config['gate_source_sha256']
            and record['public_fixture_sha256'] == config['public_fixture_sha256']
            and record['endpoint_sha256'] == c.digest(config['endpoint'].encode()), 'machine-binding')
    if mode == 'LIVE':
        require(intent['request_bound_proof_sha256'] == PROOF_RULE_SHA256, 'inline-proof-rule-binding')
    else:
        require(intent['public_fixture_sha256'] == config['public_fixture_sha256'], 'public-fixture-join')
    require(record['image_store'] in ('classic', 'containerd')
            and set(record['image_ids']) == {'jre', 'jdk'}, 'image-store-binding')
    expected = {'jre': b.JRE, 'jdk': b.JDK} if record['image_store'] == 'containerd' else {
        'jre': b.JRE_CONFIG, 'jdk': 'b6b0d394b3d52d8db009047a714e54141e97e7e267c2fddc256c7a23708e0bd7'}
    require(record['image_ids'] == {k: 'sha256:' + val for k, val in expected.items()}, 'store-specific-image-id')


def host_disk_check(config):
    observations = {}
    for key in ('use_parent', 'run_parent', 'build_parent'):
        _, fd, identity = v.open_parent(config[key])
        try:
            observed = v.filesystem(fd)
            v.validate_filesystem(observed)  # controller statfs, >=20GiB now
            observations[key] = (identity, tuple(observed['fsid']))
        finally:
            os.close(fd)
    require(observations['use_parent'][0] != observations['run_parent'][0]
            and observations['use_parent'][1] == observations['run_parent'][1], 'ledger-placement')
    return observations


def disk_check(config, qualification, approval):
    host_disk_check(config)
    raw = b.read_file(config['disk_receipt_path'], 65536)
    require(c.digest(raw) == qualification['disk_receipt_sha256'], 'docker-disk-receipt-join')
    receipt = c.strict_json(raw)
    fields = {'schema', 'observed_at', 'endpoint_sha256', 'image_manifest_sha256', 'method',
              'df_stdout', 'df_stdout_sha256', 'available_bytes', 'cleanup_confirmed'}
    require(type(receipt) is dict and set(receipt) == fields
            and receipt['schema'] == 'full-intcalc-docker-headroom/1'
            and receipt['endpoint_sha256'] == c.digest(config['endpoint'].encode())
            and receipt['image_manifest_sha256'] == b.JRE
            and receipt['method'] == 'pinned-readonly-container-df-P-k-root'
            and receipt['cleanup_confirmed'] is True, 'docker-disk-receipt')
    stdout = receipt['df_stdout'].encode('ascii', errors='strict')
    require(c.digest(stdout) == receipt['df_stdout_sha256'], 'docker-disk-raw-join')
    available = parse_df(stdout)
    require(type(receipt['available_bytes']) is int and available == receipt['available_bytes']
            and available >= v.MIN_FREE, 'docker-disk-headroom')
    observed = a._timestamp(receipt['observed_at'])
    issued, expires = a._timestamp(approval['issued_at']), a._timestamp(approval['expires_at'])
    require(observed <= issued <= datetime.now(timezone.utc) < expires
            and expires <= observed + timedelta(seconds=1800), 'docker-disk-approval-window')


def parse_df(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 8192, 'docker-disk-output')
    lines = raw.decode('ascii', errors='strict').splitlines()
    require(len(lines) == 2, 'docker-disk-output')
    fields = lines[1].split()
    require(len(fields) == 6 and fields[-1] == '/' and all(x.isdecimal() for x in fields[1:4])
            and fields[4].endswith('%'), 'docker-disk-output')
    size, used, available = map(int, fields[1:4])
    require(0 <= used <= size and 0 <= available <= size and size < 2**53, 'docker-disk-output')
    return available * 1024


def local_images(config, qualification):
    prefix = docker_prefix(config)
    end = time.monotonic() + 30
    from lightyear_mainframe.intcalc_candidate_gate import daemon_runtime_platform
    info = b.capture([*prefix, 'info', '--format', '{"os":{{json .OSType}},"architecture":{{json .Architecture}}}'], end, end + 2)
    require(info['rc'] == 0 and daemon_runtime_platform(info['stdout']) == 'linux/arm64', 'daemon-native-arm64')
    for key, digest in (('jre', b.JRE), ('jdk', b.JDK)):
        image = 'docker.io/library/eclipse-temurin@sha256:' + digest
        result = b.capture([*prefix, 'image', 'inspect', image], end, end + 2)
        require(result['rc'] == 0, 'local-image-missing')
        rows = c.strict_json(result['stdout'])
        require(type(rows) is list and len(rows) == 1, 'image-inspect-shape')
        row = rows[0]
        require(row['Os'] == 'linux' and row['Architecture'] == 'arm64'
                and row['Id'] == qualification['image_ids'][key]
                and any(x in row['RepoDigests'] for x in (image, 'eclipse-temurin@sha256:' + digest)),
                'image-digest-platform-store')


def read_only_checks(intent, approval, expected_hash, config, qualification):
    """Same non-mutating checks for preflight, run and rehearsal."""
    native()
    approval_record(intent, approval, expected_hash, datetime.now(timezone.utc))
    qualify_record(intent, config, qualification, approval)
    if approval['mode'] == 'REHEARSAL':
        rehearsal_packet(intent, expected_hash)
    else:
        structural = clone(intent)
        structural['binding_sha256'] = '0' * 64
        for key in ('spend_authority', 'exact_run_approval'):
            structural['prerequisites'][key] = {'status': 'MISSING', 'evidence_sha256': None}
        b.pins(structural)
    source_check(config, intent)
    local_images(config, qualification)
    disk_check(config, qualification, approval)
    import fcntl
    require(hasattr(fcntl, 'F_FULLFSYNC'), 'fullfsync-unavailable')
    binding_raw = b.read_file(config['verifier_binding'], 128 * 1024)
    require(c.digest(binding_raw) == config['verifier_binding_sha256'], 'verifier-binding-join')
    binding = c.strict_json(binding_raw)  # metadata only; never opens frozen cases here
    require(binding['case_manifest']['sha256'] == intent['case_manifest_sha256']
            and binding['runtime_platform'] == 'linux/arm64' and 'byte_policy' not in binding,
            'verifier-binding-join')
    gate_path = Path(config['source_root']) / 'src/lightyear_mainframe/intcalc_candidate_gate.py'
    require(c.digest(b.read_file(gate_path, 128 * 1024)) == config['gate_source_sha256'], 'gate-source-join')
    source = b.read_file(config['public_fixture_path'], 65536)
    require(c.digest(source) == config['public_fixture_sha256']
            and source == b.read_file(Path(config['source_root']) / 'tests/fixtures/intcalc-c1/Main.java', 65536),
            'fixed-public-fixture')
    if approval['mode'] == 'LIVE':
        archive = b.read_file(config['public_context_path'], c.MAX_CONTEXT_ARCHIVE)
        allowlist = b.read_file(config['public_allowlist_path'], 128 * 1024)
        require(c.digest(archive) == c.CONTEXT_HASH and c.digest(allowlist) == c.ALLOWLIST_HASH, 'public-context-join')
        c.context_members(archive, allowlist)
        used_name = hashlib.sha256(('c2-' + expected_hash).encode()).hexdigest() + '.used'
        require(not (Path(config['use_parent']) / used_name).exists(), 'approval-already-consumed')
        require(not (Path(config['run_parent']) / expected_hash).exists(), 'run-directory-exists')
    require(not (Path(config['build_parent']) / ('build-gate-' + expected_hash)).exists(), 'build-directory-exists')
    # No write probe, key prompt, nonce, use-store consumption or file creation.
    # O_EXCL/write/full-sync readback stays the actual launch-time probe.
    return 'preflight-ready-write-probe-pending'


def refusal_code(error):
    if isinstance(error, (BootstrapRefused, c.CompositionRefused, b.AdapterRefused,
                          a.PreviewAdmissionError, v.VolumeRefused, t.TransportRefused)):
        code = getattr(error, 'code', None) or (error.args[0] if error.args else '')
        if code in PUBLIC_REFUSAL_CODES:
            return code
    if isinstance(error, OSError):
        return 'io-refused'
    return 'preflight-refused'


def hidden_api_key():
    require(sys.stdin.isatty(), 'interactive-tty-required')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        value = getpass.getpass('OpenAI API key (hidden; this process only): ')
    require(type(value) is str and 1 <= len(value) <= 512
            and value.isascii() and not any(ch.isspace() or ord(ch) < 33 for ch in value), 'credential-format')
    return value


def ephemeral_envelope(bindings, credential_id, key):
    unsigned = dict(schema=a.SCHEMA, issuer_namespace=a.ISSUER, credential_id=credential_id,
        scope=SCOPE, qualified=False, production_controller_receipt=False, bindings=bindings)
    return {**unsigned, 'signature': {'algorithm': 'HMAC-SHA256', 'value':
        hmac.new(key, a.DOMAIN + a._canonical(unsigned), hashlib.sha256).hexdigest()}}


def volume_preflight(config, approval_hash, probe_id):
    ids, fsids = [], []
    for key in ('use_parent', 'run_parent'):
        _, fd, identity = v.open_parent(config[key])
        try:
            ids.append(identity)
            fsids.append(tuple(v.filesystem(fd)['fsid']))
        finally:
            os.close(fd)
    require(fsids[0] == fsids[1], 'ledger-volume-join')
    placement = v.AttendedPlacement(approval_hash, ids[0], ids[1], fsids[0], True)
    return v.qualify(config['use_parent'], config['run_parent'], probe_id=probe_id, placement=placement)


class Ports:
    def __init__(self, packet, intent, approval, approval_hash, config, qualification, bindings):
        self.packet, self.intent, self.approval = clone(packet), clone(intent), clone(approval)
        self.approval_hash, self.config, self.qualification = approval_hash, clone(config), clone(qualification)
        self.bindings = clone(bindings)
        self.lease = self.ledger = self.adapter = self.admission = self.transport_instance = None
        self.key = None
        self.authenticated = self.consumed = self.closed = False
        self.role_index = 0
        self.pre_admission_code = None

    def authenticate(self, packet):
        try:
            return self._authenticate(packet)
        except BaseException as error:
            self.pre_admission_code = refusal_code(error)
            raise

    def _authenticate(self, packet):
        require(not self.authenticated and packet == self.packet and self.approval['mode'] == 'LIVE', 'live-authority')
        read_only_checks(self.intent, self.approval, self.approval_hash, self.config, self.qualification)
        self.authenticated = True
        return True

    def admit(self, packet):
        try:
            return self._admit(packet)
        except BaseException as error:
            if self.admission is None:
                self.pre_admission_code = refusal_code(error)
            raise

    def _admit(self, packet):
        require(self.authenticated and not self.consumed and packet == self.packet, 'admit-once')
        self.consumed = True
        self.key = hidden_api_key()
        # Recheck freshness after the operator prompt. Never extend the window.
        approval_record(self.intent, self.approval, self.approval_hash, datetime.now(timezone.utc))
        disk_check(self.config, self.qualification, self.approval)
        self.lease = volume_preflight(self.config, self.approval_hash, c.digest(self.bindings['nonce'].encode()))
        approval_record(self.intent, self.approval, self.approval_hash, datetime.now(timezone.utc))
        disk_check(self.config, self.qualification, self.approval)
        # The approval identity, not a fresh random nonce, keys the exclusive use
        # store. Relaunching with a new in-memory key cannot reuse this approval.
        credential_id = 'c2-' + self.approval_hash
        secret = secrets.token_bytes(32)
        try:
            envelope = ephemeral_envelope(self.bindings, credential_id, secret)
            self.admission = a.admit_preview(a._canonical(envelope), approved_bindings=self.bindings,
                credential_id=credential_id, verification_key=secret, use_store=v.CheckedUseStore(self.lease),
                wall_now=lambda: datetime.now(timezone.utc), monotonic_now=time.monotonic)
        finally:
            secret = None  # reference disposal only, not guaranteed zeroization
        self.ledger = v.CheckedRunLedger(self.lease, self.approval_hash)
        self.ledger.record_once('ledger-volume.json', self.lease.receipt())
        self.adapter = b.BuildGateAdapter(self.packet, parent=self.config['build_parent'],
            session_id=self.approval_hash, docker_binary=self.config['docker_binary'],
            endpoint=self.config['endpoint'], verifier_binding=self.config['verifier_binding'],
            verifier_binding_sha256=self.config['verifier_binding_sha256'],
            gate_source_sha256=self.config['gate_source_sha256'])
        return self.admission

    def transport(self, admission):
        require(admission is self.admission and self.transport_instance is None, 'transport-once')
        self.transport_instance = t.PreviewTransport(admission=admission,
            spend=t.ReviewedSpend(self.approval_hash, self.approval['account_billing_evidence_sha256'], True, c.CAP),
            ledger=self.ledger, api_key=self.key, validate_artifact=artifact_valid)
        self.key = None
        return self.transport_instance

    def prove_request(self, role, projection):
        require(self.role_index < len(c.ROLES) and role == c.ROLES[self.role_index], 'request-role-order')
        source_check(self.config, self.intent)
        require(self.packet['request_bound_proof_sha256'] == PROOF_RULE_SHA256
                and projection['model'] == c.MODEL and projection['instructions'] == c.ROLE_INSTRUCTIONS[role],
                'request-fixed-role')
        raw = c.canonical(projection)
        upper = len(raw) + 4096
        require(upper <= c.ROLE_INPUT_CAPS[role], 'budget-fixed-input-cap')
        self.role_index += 1
        return t.ReviewedRequest(projection, c.digest(raw), upper,
            self.packet['request_bound_proof_sha256'], self.packet['public_context_approval_sha256'])

    def build(self, attempt, source, window):
        self.lease.check()
        return self.adapter.build(attempt, source, window)

    def gate(self, attempt, built, window):
        self.lease.check()
        return self.adapter.gate(attempt, built, window)

    def record_once(self, name, value):
        require(self.ledger is not None, 'admission-ledger-required')
        self.ledger.record_once(name, value)

    def close(self):
        if not self.closed:
            self.closed = True
            self.key = None
            if self.transport_instance is not None:
                self.transport_instance._key = None
            try:
                if self.ledger is not None:
                    self.ledger.close()
            finally:
                if self.lease is not None:
                    self.lease.close()


def run_session(packet, public_context, public_allowlist, ports):
    native()
    require(type(ports) is Ports, 'fixed-ports')
    try:
        result = c.Composition(packet, public_context, public_allowlist, ports).run()
        if ports.admission is None and ports.pre_admission_code:
            raise BootstrapRefused(ports.pre_admission_code)
        c.verify_result(result)
        return result
    except Exception:
        if ports.admission is None and ports.pre_admission_code:
            raise BootstrapRefused(ports.pre_admission_code) from None
        raise
    finally:
        ports.close()


def rehearse(intent, approval, approval_hash, config, qualification):
    """Real Mac build/gate, fixed public fixture, no transport/admission/key path."""
    native()
    require(approval['mode'] == 'REHEARSAL', 'rehearsal-authority')
    read_only_checks(intent, approval, approval_hash, config, qualification)
    packet = rehearsal_packet(intent, approval_hash)
    source = b.read_file(config['public_fixture_path'], 65536)
    require(c.digest(source) == config['public_fixture_sha256'], 'public-fixture-join')
    # Source must also be the reviewed repository fixture, not any supplied hash.
    expected = b.read_file(Path(config['source_root']) / 'tests/fixtures/intcalc-c1/Main.java', 65536)
    require(source == expected, 'fixed-public-fixture')
    adapter = b.BuildGateAdapter(packet, parent=config['build_parent'], session_id=approval_hash,
        docker_binary=config['docker_binary'], endpoint=config['endpoint'],
        verifier_binding=config['verifier_binding'], verifier_binding_sha256=config['verifier_binding_sha256'],
        gate_source_sha256=config['gate_source_sha256'])
    lease = volume_preflight(config, approval_hash, c.digest(('rehearsal:' + approval_hash).encode()))
    try:
        approval_record(intent, approval, approval_hash, datetime.now(timezone.utc))
        disk_check(config, qualification, approval)
        original = time.monotonic() + 1200
        built = adapter.build(1, source.decode('utf-8'), c.PhaseWindow(min(time.monotonic() + 600, original), original))
        require(not built.compile_failed, 'public-fixture-build')
        lease.check()
        result = adapter.gate(1, built, c.PhaseWindow(min(time.monotonic() + 600, original), original))
        lease.check()
        b.exclusive(adapter.root / 'rehearsal-ledger-volume.json', c.canonical(lease.receipt()))
    finally:
        lease.close()
    counts = c.feedback(result.verdicts)['verdict_counts']
    require(counts == {k: {'DIFFERENT': 6, 'MATCH': 1, 'REFUSAL_NOT_OBSERVED': 3}.get(k, 0)
                      for k in c.VERDICTS}, 'public-fixture-counts')
    public = dict(verdict_counts=counts, hashes=dict(source=c.digest(source), build=built.receipt_sha256,
        gate=result.receipt_sha256), cleanup=dict(build=built.cleanup_confirmed, gate=result.cleanup_confirmed))
    b.exclusive(adapter.root / 'rehearsal-public.json', c.canonical(public))
    return public


def configure(inputs, output):
    """Materialize reviewed local paths; no key, admission, image pull or probe."""
    native()
    mode, config = inputs['mode'], clone(inputs['config'])
    fields = LIVE_CONFIG_FIELDS if mode == 'LIVE' else BASE_CONFIG_FIELDS
    require(mode in ('LIVE', 'REHEARSAL') and set(config) == fields, 'configuration-inputs')
    require(config['outside_sync_and_candidate_roots'] is True, 'configuration-placement')
    # The operator-reviewed local input chooses paths, never headroom numbers.
    parent = b.safe_path(Path(config['docker_config']).parent, directory=True, owner=True)
    require(not Path(config['docker_config']).exists(), 'docker-config-already-exists')
    (parent / Path(config['docker_config']).name).mkdir(mode=0o700)
    docker_prefix(config)
    b.exclusive(Path(output), c.canonical(config))


def observe_disk(config):
    """Separate attended observation; NOT the read-only preflight command.

    The CLI cannot read guest statfs directly. A pinned trusted container reads
    its root backing filesystem, with no mounts or network. Its result is then
    bound to the entire approval window, never refreshed or operator-entered.
    """
    native()
    host_disk_check(config)
    prefix = docker_prefix(config)
    destination = Path(config['disk_receipt_path'])
    b.safe_path(destination.parent, directory=True, owner=True)
    require(not destination.exists(), 'disk-receipt-already-exists')
    token = secrets.token_hex(16)  # public resource identity, not a credential
    registry_root = b.safe_path(config['build_parent'], directory=True, owner=True) / ('disk-observation-' + token)
    registry_root.mkdir(mode=0o700)
    registry = b.Registry(registry_root)
    name = 'c2-build-' + token
    image = 'docker.io/library/eclipse-temurin@sha256:' + b.JRE
    hard = time.monotonic() + 60
    work = hard - 30
    inspected = b.capture([*prefix, 'image', 'inspect', image], work, hard)
    require(inspected['rc'] == 0, 'local-image-missing')
    rows = c.strict_json(inspected['stdout'])
    require(type(rows) is list and len(rows) == 1 and rows[0]['Os'] == 'linux'
            and rows[0]['Architecture'] == 'arm64', 'disk-image-platform')
    from lightyear_mainframe.intcalc_candidate_gate import daemon_runtime_platform
    info = b.capture([*prefix, 'info', '--format', '{"os":{{json .OSType}},"architecture":{{json .Architecture}}}'], work, hard)
    require(info['rc'] == 0 and daemon_runtime_platform(info['stdout']) == 'linux/arm64', 'daemon-native-arm64')
    registry.register('container', name)
    try:
        created = b.capture([*prefix, 'create', '--pull=never', '--name', name,
            '--platform=linux/arm64', '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--pids-limit=32', '--memory=128m', '--cpus=1',
            '--entrypoint=/usr/bin/df', image, '-P', '-k', '/'], work, hard)
        require(created['rc'] == 0, 'disk-observation-create')
        result = b.capture([*prefix, 'start', '--attach', name], work, hard, cap=8192)
        require(result['rc'] == 0 and result['stderr'] == b'', 'disk-observation-exit')
        available = parse_df(result['stdout'])
        observed_at = datetime.now(timezone.utc).isoformat()
    finally:
        removed = b.cleanup(prefix, registry, hard)
    require(len(removed) == 1 and removed[0]['absence_confirmed'], 'disk-observation-cleanup')
    require(available >= v.MIN_FREE, 'docker-disk-headroom')
    receipt = dict(schema='full-intcalc-docker-headroom/1', observed_at=observed_at,
        endpoint_sha256=c.digest(config['endpoint'].encode()), image_manifest_sha256=b.JRE,
        method='pinned-readonly-container-df-P-k-root', df_stdout=result['stdout'].decode('ascii'),
        df_stdout_sha256=c.digest(result['stdout']), available_bytes=available, cleanup_confirmed=True)
    b.exclusive(destination, c.canonical(receipt))


def prepare_files(inputs, config, output):
    """Produces review candidates, NOT approval; Howard must authorize exact hash."""
    native()
    require(set(inputs) == {'mode', 'intent', 'image_store', 'account_billing_evidence_sha256'}, 'preparation-inputs')
    mode, intent = inputs['mode'], clone(inputs['intent'])
    require(mode in ('LIVE', 'REHEARSAL'), 'preparation-mode')
    intent_hash = validate_intent(intent, mode)
    fields = LIVE_CONFIG_FIELDS if mode == 'LIVE' else BASE_CONFIG_FIELDS
    require(set(config) == fields, 'local-config-fields')
    source_check(config, intent)
    disk_raw = b.read_file(config['disk_receipt_path'], 65536)
    disk = c.strict_json(disk_raw)
    observed = a._timestamp(disk['observed_at'])
    issued = datetime.now(timezone.utc)
    expires = observed + timedelta(seconds=1800)
    require(observed <= issued < expires, 'docker-disk-approval-window')
    required = set(c.PREREQUISITES) - {'spend_authority', 'exact_run_approval'} if mode == 'LIVE' else REHEARSAL_REQUIRED
    store = inputs['image_store']
    require(store in ('classic', 'containerd'), 'image-store-binding')
    ids = {'jre': b.JRE, 'jdk': b.JDK} if store == 'containerd' else {
        'jre': b.JRE_CONFIG, 'jdk': 'b6b0d394b3d52d8db009047a714e54141e97e7e267c2fddc256c7a23708e0bd7'}
    qualification = dict(schema='full-intcalc-machine-qualification/2', intent_sha256=intent_hash,
        checks={k: True for k in required}, receipts={k: intent['prerequisites'][k]['evidence_sha256'] for k in required},
        disk_receipt_sha256=c.digest(disk_raw), endpoint_sha256=c.digest(config['endpoint'].encode()),
        controller_source_manifest_sha256=intent['controller_source_manifest_sha256'],
        gate_source_sha256=config['gate_source_sha256'], public_fixture_sha256=config['public_fixture_sha256'],
        image_store=store, image_ids={k: 'sha256:' + val for k, val in ids.items()})
    approval = dict(schema='full-intcalc-attended-approval/2', intent_sha256=intent_hash, scope=SCOPE,
        cap_microdollars=c.CAP if mode == 'LIVE' else 0, count_billing_known=mode == 'LIVE',
        account_billing_evidence_sha256=inputs['account_billing_evidence_sha256'],
        issued_at=issued.isoformat(), expires_at=expires.isoformat(), qualified=False,
        production_controller_receipt=False, local_config_sha256=c.digest(c.canonical(config)),
        qualification_sha256=c.digest(c.canonical(qualification)), mode=mode)
    digest = c.digest(c.canonical(approval))
    read_only_checks(intent, approval, digest, config, qualification)
    parent = b.safe_path(Path(output).parent, directory=True, owner=True)
    root = parent / Path(output).name
    root.mkdir(mode=0o700)  # exclusive; no overwrite or rebinding of old evidence
    for name, value in (('intent', intent), ('config', config), ('qualification', qualification), ('approval', approval)):
        b.exclusive(root / (name + '.json'), c.canonical(value))
    b.exclusive(root / 'REVIEW-REQUIRED.txt', b'Generated candidates only. Independent review and Howard exact approval are required.\n')


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'arguments-refused\n')


def main(argv=None):
    parser = SafeParser(description='Proposal-only attended controller; separate exact authority required.')
    sub = parser.add_subparsers(dest='command', required=True, parser_class=SafeParser)
    for mode in ('preflight', 'rehearse', 'run'):
        p = sub.add_parser(mode)
        for name in ('intent', 'approval', 'config', 'qualification', 'approval-sha256'):
            p.add_argument('--' + name, required=True)
    p = sub.add_parser('configure')
    p.add_argument('--inputs', required=True)
    p.add_argument('--output', required=True)
    p = sub.add_parser('observe-disk')
    p.add_argument('--config', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--inputs', required=True)
    p.add_argument('--config', required=True)
    p.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        native()
        if args.command == 'configure':
            configure(read_json(args.inputs), args.output)
            print('configuration-created-review-required')
            return 0
        if args.command == 'observe-disk':
            observe_disk(read_json(args.config))
            print('disk-observation-created-review-required')
            return 0
        if args.command == 'prepare':
            prepare_files(read_json(args.inputs), read_json(args.config), args.output)
            print('candidates-created-independent-approval-required')
            return 0
        intent, approval, config, qualification = (read_json(getattr(args, k))
            for k in ('intent', 'approval', 'config', 'qualification'))
        expected = args.approval_sha256  # public digest independently supplied by Claude/Howard
        if args.command != 'preflight':
            require(approval['mode'] == ('LIVE' if args.command == 'run' else 'REHEARSAL'), 'mode-binding')
        code = read_only_checks(intent, approval, expected, config, qualification)
        if args.command == 'preflight':
            print(code)
            return 0
        require(sys.stdin.isatty(), 'attended-terminal-required')
        if args.command == 'rehearse':
            result = rehearse(intent, approval, expected, config, qualification)
        else:
            issued = datetime.now(timezone.utc)
            # Admission's reviewed schema requires exactly 1800 seconds. The
            # separate, earlier approval expiry is rechecked before consumption;
            # this envelope timestamp never extends Howard's approval window.
            bindings = bindings_for(intent, approval, issued_at=issued.isoformat(), nonce=secrets.token_hex(32),
                admission_expires_at=(issued + timedelta(seconds=1800)).isoformat())
            packet = final_packet(intent, approval, bindings)
            ports = Ports(packet, intent, approval, expected, config, qualification, bindings)
            result = run_session(packet, b.read_file(config['public_context_path'], c.MAX_CONTEXT_ARCHIVE),
                b.read_file(config['public_allowlist_path'], 128 * 1024), ports)
        print(c.canonical(result).decode('utf-8'))
        return 0
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        print(refusal_code(error))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
