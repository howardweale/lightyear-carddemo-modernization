"""Validate an exact F2 exception from trusted base objects, never PR records.

This does not change the raw Java fence report or authorize a merge or run.
Human approval is recorded provenance, not machine authentication of the human.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

CHECKER = 'tools/check_java_quality_fence.py'
VALIDATOR = 'tools/check_f2_fence_exceptions.py'
MANIFEST = 'docs/factory/f2-exact-byte-exceptions-2026-10-24.json'
GATE = 'tools/ci_gate.py'
BUDGETED = 'src/lightyear_factory/budgeted_providers.py'
PROVIDERS = 'src/lightyear_factory/providers.py'
POSTTRAN = 'docs/factory/posttran-phase2-plan-2026-10-16.json'
REPOSITORY = 'howardweale/lightyear-carddemo-modernization'
APPROVED_SHA = '12d195d37b6d7ed9e7ca8f290e61f8aead641c5ded2d3351db600def5816d928'
PROVENANCE_EVIDENCE_LINK = ' [operator-chat record](f2-operator-chat-provenance-receipt-2026-10-24.json#sha256=b0a9e8187be72b9c78a6f13d750247f2355e626f41f49fd50017396f4e86fe7e)'
ORCHESTRATOR = 'src/lightyear_factory/orchestrator.py'
ORCHESTRATOR_SHA = 'e727445fb0de0e845abf5b9a0c451ac1269aa9a0b706e9fc3b2dc8da071af8d8'
ORCHESTRATOR_EVIDENCE_LINK = ' [operator-chat record](f2-orchestrator-provenance-receipt-2026-10-24.json#sha256=f5751763ffddcf4c12370866f31817012b7d63a55e9fb2f78e20dea8ff1b9523)'
WORKFLOW_BINDING = 'docs/factory/f2-p5-workflow-binding-2026-10-24.json'
P5_WORKFLOW = '.github/workflows/p5-factory-drills.yml'
P5_WORKFLOW_SHA = '302c13c53b9ad2f5136920f522c1b0c70c16fa8c563382fd6709aedf99dbd35f'
WORKFLOW_EVIDENCE_LINK = ' [operator-chat record](f2-workflow-provenance-receipt-2026-10-24.json#sha256=f5202f3faaff9699d66cc51c92926e0ef8aa13ff6e0242116b10069acacc388d)'
VERIFY_BINDING = 'docs/factory/f2-p5-verify-timeout-binding-2026-10-25.json'
VERIFY_WORKFLOW = '.github/workflows/verify.yml'
VERIFY_BEFORE_SHA = '1736424d5716880a0eb5dc941fcafc085d58faa04e4838c4eb7a8834ad1dbd1b'
VERIFY_AFTER_SHA = 'a83be67630a54de10840743bcc24a7f1bd9c786c7447108eb448ae4818e91cf3'
CONTROLS = {CHECKER, VALIDATOR, MANIFEST, GATE, WORKFLOW_BINDING}

EXECUTION_GATES = 'src/lightyear_factory/gates.py'
DURABLE_EVIDENCE_LINK = ' [operator-chat record](p5-durable-publication-operator-receipt-2026-10-26.json#sha256=511036c6271004549bc285e97384609078eaba506d61a73fa02c5fcdafd60734)'
DURABLE_BINDING = 'docs/factory/p5-flex-count-controller-exact-binding-2026-10-27.json'
DURABLE_RUNTIME = {'src/lightyear_execution/admission.py': {'before': {'mode': '100644', 'sha256': '5c4d96d664699b05cc814a7236feca8fa0927c37139a09c36306ad2f4b9c63f0'}, 'after': {'mode': '100644', 'sha256': 'a8cdc7539ca5eb73a82d9f8c0b8610f05c20ca25eae55303ec09d6debc97b8ec'}}, 'src/lightyear_execution/contracts.py': {'before': {'mode': '100644', 'sha256': '0bce6d7009d8d755c6f4c767238a1e7a1f990e01f6cfdf8628ea6edaa02cf88c'}, 'after': {'mode': '100644', 'sha256': '2c4d601a273ba1cda6339c44e2c6c84281a917058ea3e9570a2b233a14112e53'}}, 'src/lightyear_execution/human_drill_dispatch.py': {'before': None, 'after': {'mode': '100644', 'sha256': '2f76e65de0c1e0cb0aea5b7d002f445d595534f1a721b2de8abf2732e1b2fd52'}}, 'src/lightyear_execution/identity.py': {'before': {'mode': '100644', 'sha256': 'b2c9290037dfe0305ce0f0d26a13d621ef1fb40eb5e3c17b774cda43b1267a66'}, 'after': {'mode': '100644', 'sha256': '562e5b55b0083c8c1657b89bf71ff79336c467d1ee77c1d04cef4186682a9c98'}}, 'src/lightyear_execution/integration.py': {'before': {'mode': '100644', 'sha256': '1f3e05f10a505e84d273695e6ded111d9b46a9cceb72d03c282864d2d0a5a17e'}, 'after': {'mode': '100644', 'sha256': '82d83c3bce8d494a0bbf115edd3fca795e5ccd78f5588de6959b9114b8f486fb'}}, 'src/lightyear_execution/public_drill_outputs.py': {'before': None, 'after': {'mode': '100644', 'sha256': 'ecf9fa56a9f875e5abba30be0a2f5453f3351658a3c8b5d62c1da15ece395009'}}, 'src/lightyear_execution/public_drill_runtime.py': {'before': None, 'after': {'mode': '100644', 'sha256': '18c25805d72daec6c6cb9c32ae9c9ccc32e4305d7175d87bf55e52a5b8cf4005'}}, 'src/lightyear_execution/tower_drill_admission.py': {'before': None, 'after': {'mode': '100644', 'sha256': '1957c91ce428a5b89ada83b49bfa7c8e530e120af2957b616153f80497f48511'}}, 'src/lightyear_execution/tower_drill_context.py': {'before': None, 'after': {'mode': '100644', 'sha256': '6f2fa13bb661a82554c922beae5cb0c810dfb6f99ad02530cd52c7c314712a47'}}, 'src/lightyear_execution/tower_drill_reservation.py': {'before': None, 'after': {'mode': '100644', 'sha256': '153b1dba050ed57cdb2f499c91a5222da871ee16c4e5848ed93e066f9ee3d18e'}}, 'src/lightyear_execution/tower_drill_roles.py': {'before': None, 'after': {'mode': '100644', 'sha256': '55c78242ae12f67df91f9afd5f570e06c63713b0d439cbfeab1fb7fbfa40384f'}}, 'src/lightyear_factory/additional_providers.py': {'before': {'mode': '100644', 'sha256': 'cfcfc12f3300240dff2435abe22b9af726293bb8ba91ab40893166f935ec212c'}, 'after': {'mode': '100644', 'sha256': 'b76c37c6359cd1af0710033bb87dd4050f0d4ab36f6aa31cd75004b69216b1fc'}}, 'src/lightyear_factory/budgeted_providers.py': {'before': {'mode': '100644', 'sha256': '7207e840edf4292026a909b7f4e992dfe682f9add36b0fff4d552b224015fb7b'}, 'after': {'mode': '100644', 'sha256': '885b383a0daae7636c26a8218836e3f9202a1894723abbb55c75a1160de38289'}}, 'src/lightyear_factory/cli.py': {'before': {'mode': '100644', 'sha256': '2c20d8f13d34604e804700c63b231cef1f4a30c0eae5da7d506c66d3c1ee74d5'}, 'after': {'mode': '100644', 'sha256': 'e7dcaa6fd91e33b0dd5fbe03874f97642e1e4fd58ca82a43908dee255a7c2609'}}, 'src/lightyear_factory/controller_count_accounting.py': {'before': None, 'after': {'mode': '100644', 'sha256': 'e9c4fa996e467431764f4982974d557ebc5e77ff1b4127a5628d5dc6bf83c84d'}}, 'src/lightyear_factory/count_charge_account.py': {'before': None, 'after': {'mode': '100644', 'sha256': '49b2d418163f1b4f9d1050fb1f0dade08f903c9edb4a211ddc9a4362736b0a40'}}, 'src/lightyear_factory/count_request_bound.py': {'before': None, 'after': {'mode': '100644', 'sha256': '1c594ab95566c5be8e63daada4d56a64acdb25ded58b9a7e91009d41b40a917b'}}, 'src/lightyear_factory/flex_billing.py': {'before': None, 'after': {'mode': '100644', 'sha256': 'f0d00e0d9e72451ecc3e210cb5e406fe84cd7272eba0c3383731c7d27a39daec'}}, 'src/lightyear_factory/gates.py': {'before': {'mode': '100644', 'sha256': 'cd069b3321379235cd65ac357b1cd6d2f0afb6907ff2a66eff1e6b7db4c5ae51'}, 'after': {'mode': '100644', 'sha256': '5257a3da78e325ec46a6e70a5c6b24fdbb0287758279084acb3cd3fc4388c262'}}, 'src/lightyear_factory/model_config.py': {'before': {'mode': '100644', 'sha256': '5662ae03b55b0a9c99160ae21d33009ef1f566c4d4440ebad018ea22fcc90766'}, 'after': {'mode': '100644', 'sha256': 'cc38c1990fd8ffb9f840c0ca091a3889c0822f25e0796d4656631cb41fb6bbfe'}}, 'src/lightyear_factory/model_versions.py': {'before': {'mode': '100644', 'sha256': 'ceab75e32be2a8e686a8260044ba72d8bf44a5abafb550fab24d187f6e359d97'}, 'after': {'mode': '100644', 'sha256': 'ac31255a9e872b09c97e7f15932f1e8bc3d398496225bfc31fa8767bbcdc61a2'}}, 'src/lightyear_factory/orchestrator.py': {'before': {'mode': '100644', 'sha256': 'beee29177a35c5a45f283fe888f5c417bebe7b62d9dd51fd1a9bd961bfd66add'}, 'after': {'mode': '100644', 'sha256': 'f9aa90e3e58a4242ebecd4eb8d020f7ec057528c348a3c6133627e178b5f59ea'}}, 'src/lightyear_factory/providers.py': {'before': {'mode': '100644', 'sha256': 'f44ee1ce22fe78eb712ee16be560c8d6ef2c4ab498d9937b98dc6f1fd7b4e52d'}, 'after': {'mode': '100644', 'sha256': 'abf9d76275c99a9057c64264bb94dffbb8f852f6218891a21d5f79b15da59612'}}, 'src/lightyear_factory/transport_journal.py': {'before': None, 'after': {'mode': '100644', 'sha256': '1cdace7bed7427557557ff639b8014aad81ae68adb8ecff55efd23f4b81bdcc6'}}}
REPORT_KEYS = {'schema', 'base', 'head', 'fence_sha256', 'fenced_paths',
               'fenced_prefixes', 'source_records', 'blocked_paths',
               'merge_permitted', 'automatic_expiry'}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate-json-key')
        result[key] = value
    return result


def document(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def fields(value, names, code):
    require(isinstance(value, dict) and set(value) == set(names), code)


def digest(value, length=64):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{%d}' % length, value),
            'invalid-object-digest')
    return value


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def resolve(repo, value):
    digest(value, 40)
    result = git(repo, 'rev-parse', '--verify', value + '^{commit}').decode().strip()
    require(result == value, 'commit-identity')
    return result


def blob(repo, commit, path):
    row = git(repo, 'ls-tree', '-z', commit, '--', path).decode().split('\0')
    require(len(row) == 2 and row[1] == '', 'missing-or-ambiguous-blob')
    metadata, actual_path = row[0].split('\t')
    mode, kind, oid = metadata.split()
    require(actual_path == path and kind == 'blob' and mode == '100644', 'blob-mode')
    raw = git(repo, 'cat-file', 'blob', oid)
    return dict(mode=mode, sha256=sha(raw)), raw


def load_checker(repo, base):
    _, source = blob(repo, base, CHECKER)
    namespace = {'__name__': 'trusted_base_fence'}
    exec(compile(source, CHECKER, 'exec'), namespace)
    return namespace, source


def validate_raw_report(raw, expected, returncode):
    report = document(raw)
    fields(report, REPORT_KEYS, 'incomplete-fence-report')
    require(report == expected, 'unexpected-fence-report')
    require(report['schema'] == 'java-quality-fence/1', 'unknown-fence-schema')
    require(report['automatic_expiry'] is False, 'automatic-expiry-refused')
    require(report['merge_permitted'] is (not bool(report['blocked_paths'])),
            'inconsistent-fence-result')
    require(returncode == (1 if report['blocked_paths'] else 0), 'checker-error')
    return report


def validate_manifest(value):
    fields(value, {'schema', 'repository', 'base_anchor', 'activation', 'entries',
                   'identity_limitation', 'authority'}, 'manifest-fields')
    require(value['schema'] == 'f2-exact-byte-exceptions/1', 'manifest-schema')
    require(value['repository'] == REPOSITORY, 'manifest-repository')
    digest(value['base_anchor'], 40)
    require(value['activation'] == 'trusted-base-only-after-exact-head-merge-approval',
            'manifest-activation')
    require(value['identity_limitation'] ==
            'Operator-chat attribution is not independently authenticated; the agent shares Howard\'s GitHub identity. Open after-run item.',
            'identity-limitation-required')
    require(value['authority'] == {'merge': False, 'run': False, 'signing': False,
                                   'spend': False, 'gap_acceptance': False}, 'manifest-authority')
    require(isinstance(value['entries'], list) and 1 <= len(value['entries']) <= 2,
            'approved-entry-count')
    require(all(isinstance(e, dict) for e in value['entries']), 'entry-fields')
    paths = [e.get('path') for e in value['entries']]
    require(paths[0] == BUDGETED and len(set(paths)) == len(paths)
            and all(p in (BUDGETED, ORCHESTRATOR) for p in paths), 'ineligible-entry')
    for entry in value['entries']:
        validate_entry(entry)
    return value['entries'][0]


def validate_entry(entry):
    fields(entry, {'repository', 'pr', 'path', 'mode', 'base_preimage_sha256',
                   'final_sha256', 'approved_change_commit', 'provenance'}, 'entry-fields')
    require(entry['repository'] == REPOSITORY and type(entry['pr']) is int and entry['pr'] == 455,
            'entry-target')
    require(entry['path'] in (BUDGETED, ORCHESTRATOR) and entry['mode'] == '100644', 'ineligible-entry')
    approved_sha = APPROVED_SHA if entry['path'] == BUDGETED else ORCHESTRATOR_SHA
    evidence_link = PROVENANCE_EVIDENCE_LINK if entry['path'] == BUDGETED else ORCHESTRATOR_EVIDENCE_LINK
    digest(entry['base_preimage_sha256']); digest(entry['approved_change_commit'], 40)
    require(entry['final_sha256'] == approved_sha, 'unapproved-postimage')
    provenance = entry['provenance']
    fields(provenance, {'source', 'approved_by', 'recorded_at_pt', 'exact_sha256',
                        'statement', 'github_identity_is_human_proof'}, 'provenance-fields')
    require(provenance['source'] == 'operator-chat' and provenance['approved_by'] == 'Howard Weale',
            'approval-provenance')
    require(isinstance(provenance['recorded_at_pt'], str) and
            re.fullmatch(r'2026-10-24T\d{2}:\d{2}:\d{2}-07:00', provenance['recorded_at_pt']),
            'approval-time')
    require(provenance['exact_sha256'] == approved_sha and
            provenance['github_identity_is_human_proof'] is False, 'approval-hash-or-identity')
    require(provenance['statement'] == 'approved by Howard in the operator chat, ' +
            provenance['recorded_at_pt'] + ', exact hash ' + approved_sha +
            evidence_link, 'approval-statement')
    return entry



def validate_durable_binding(value):
    """Pending review is inert; approved bytes still require trusted-base loading."""
    fields(value, {'schema', 'repository', 'pr', 'status', 'base_anchor',
                   'entries', 'approved_change_commit', 'approval', 'authority'},
           'durable-binding-fields')
    require(value['schema'] == 'p5-durable-reservation-exact-binding/1'
            and value['repository'] == REPOSITORY
            and type(value['pr']) is int and value['pr'] == 455,
            'durable-binding-target')
    require(value['base_anchor'] == '3bc468666be34faf69796a6cfece9fe59f9f8939',
            'durable-binding-anchor')
    require(value['authority'] == dict(merge=False, run=False, signing=False,
            spend=False, gap_acceptance=False), 'durable-binding-authority')
    require(isinstance(value['entries'], list)
            and len(value['entries']) == len(DURABLE_RUNTIME), 'durable-entry-count')
    paths = []
    for entry in value['entries']:
        fields(entry, {'path', 'before', 'after'}, 'durable-entry-fields')
        path = entry['path']
        require(isinstance(path, str) and path in DURABLE_RUNTIME
                and path not in paths, 'durable-entry-path')
        paths.append(path)
        require({'before': entry['before'], 'after': entry['after']} == DURABLE_RUNTIME[path],
                'durable-entry-bytes')
    require(paths == sorted(DURABLE_RUNTIME), 'durable-entry-order')
    if value['status'] == 'pending-exact-hash-approval':
        require(value['approval'] is None and value['approved_change_commit'] is None,
                'durable-pending-provenance')
        return None
    require(value['status'] == 'approved-exact-hashes', 'durable-binding-status')
    digest(value['approved_change_commit'], 40)
    approval = value['approval']
    fields(approval, {'source', 'approved_by', 'recorded_at_pt', 'exact_sha256',
                     'statement', 'github_identity_is_human_proof'}, 'durable-approval-fields')
    require(approval['source'] == 'operator-chat'
            and approval['approved_by'] == 'Howard Weale'
            and approval['github_identity_is_human_proof'] is False,
            'durable-approval-identity')
    require(isinstance(approval['recorded_at_pt'], str)
            and re.fullmatch(r'2026-10-\d{2}T\d{2}:\d{2}:\d{2}-07:00',
                             approval['recorded_at_pt']), 'durable-approval-time')
    expected = {path: row['after']['sha256'] for path, row in DURABLE_RUNTIME.items()}
    require(approval['exact_sha256'] == expected, 'durable-approval-hashes')
    exact = sha(json.dumps(expected, sort_keys=True, separators=(',', ':')).encode())
    require(approval['statement'] == 'approved by Howard in the operator chat, '
            + approval['recorded_at_pt'] + ', exact runtime hash set ' + exact
            + DURABLE_EVIDENCE_LINK,
            'durable-approval-statement')
    return value


def load_durable_binding(repo, base, head):
    if not git(repo, 'ls-tree', '-z', base, '--', DURABLE_BINDING):
        require(not git(repo, 'ls-tree', '-z', head, '--', DURABLE_BINDING),
                'candidate-durable-binding-refused')
        return None
    before, raw = blob(repo, base, DURABLE_BINDING)
    require((before, raw) == blob(repo, head, DURABLE_BINDING),
            'candidate-durable-binding-refused')
    return validate_durable_binding(document(raw))


def inspect_durable_companions(repo, base, head, binding, excluded, prefixes):
    """All seven files are one exact set; no wildcard provider exception."""
    approved = resolve(repo, binding['approved_change_commit'])
    result = []
    for entry in binding['entries']:
        path = entry['path']
        require(path not in excluded and not any(path.startswith(p) for p in prefixes),
                'judge-or-posttran-exception-refused')
        if entry['before'] is None:
            require(not git(repo, 'ls-tree', '-z', base, '--', path),
                    'durable-preimage-not-absent')
        else:
            require(blob(repo, base, path)[0] == entry['before'], 'durable-preimage')
        require(blob(repo, head, path)[0] == entry['after'], 'durable-postimage')
        require(blob(repo, approved, path)[0] == entry['after'], 'durable-approved-content')
        result.append(dict(path=path, before=entry['before'], after=entry['after']))
    return result

def validate_workflow_binding(value):
    fields(value, {'schema', 'repository', 'pr', 'path', 'mode', 'base_preimage',
                   'final_sha256', 'provenance'}, 'workflow-binding-fields')
    require(value['schema'] == 'f2-exact-workflow-binding/1', 'workflow-binding-schema')
    require(value['repository'] == REPOSITORY and type(value['pr']) is int and
            value['pr'] == 455, 'workflow-binding-target')
    require(value['path'] == P5_WORKFLOW and value['mode'] == '100644' and
            value['base_preimage'] == 'absent', 'workflow-binding-scope')
    require(value['final_sha256'] == P5_WORKFLOW_SHA, 'workflow-binding-postimage')
    provenance = value['provenance']
    fields(provenance, {'source', 'approved_by', 'recorded_at_pt', 'exact_sha256',
                        'statement', 'github_identity_is_human_proof'}, 'workflow-provenance-fields')
    require(provenance['source'] == 'operator-chat' and
            provenance['approved_by'] == 'Howard Weale' and
            provenance['recorded_at_pt'] == '2026-10-24 ~17:55 PT' and
            provenance['exact_sha256'] == P5_WORKFLOW_SHA and
            provenance['github_identity_is_human_proof'] is False, 'workflow-provenance')
    require(provenance['statement'] == 'approved by Howard in the operator chat, ' +
            provenance['recorded_at_pt'] + ', exact hash ' + P5_WORKFLOW_SHA +
            WORKFLOW_EVIDENCE_LINK, 'workflow-approval-statement')
    return value


def inspect_p5_workflow_change(repo, base, head, anchor, changed):
    workflows = [p for p in changed if p.startswith('.github/workflows/')]
    if not workflows:
        return []
    require(workflows == [P5_WORKFLOW], 'candidate-control-change')
    _, raw = blob(repo, base, WORKFLOW_BINDING)
    binding = validate_workflow_binding(document(raw))
    # Absent means no tree entry of any kind, both at the anchor and live base.
    require(not git(repo, 'ls-tree', '-z', base, '--', P5_WORKFLOW) and
            not git(repo, 'ls-tree', '-z', anchor, '--', P5_WORKFLOW),
            'workflow-preimage-not-absent')
    after, _ = blob(repo, head, P5_WORKFLOW)
    require(after == {'mode': binding['mode'], 'sha256': binding['final_sha256']},
            'workflow-postimage-refused')
    return [dict(path=P5_WORKFLOW, before='absent', after=after,
                 binding_sha256=sha(raw), provenance=binding['provenance'])]


def validate_verify_binding(value):
    fields(value, {'schema', 'repository', 'pr', 'path', 'mode', 'base_preimage',
                   'final_sha256', 'provenance'}, 'verify-binding-fields')
    require(value['schema'] == 'f2-exact-workflow-binding/1', 'verify-binding-schema')
    require(value['repository'] == REPOSITORY and type(value['pr']) is int and
            value['pr'] == 455, 'verify-binding-target')
    require(value['path'] == VERIFY_WORKFLOW and value['mode'] == '100644' and
            value['base_preimage'] == VERIFY_BEFORE_SHA, 'verify-binding-scope')
    require(value['final_sha256'] == VERIFY_AFTER_SHA, 'verify-binding-postimage')
    require(value['provenance'] == dict(source='operator-chat',
            requested_by='Howard Weale', requested_on='2026-10-25',
            exact_sha256=VERIFY_AFTER_SHA,
            statement='Planned: Windows verification timeout only, 60 to 90 minutes; exact bytes require separate review before publication and merge.',
            github_identity_is_human_proof=False), 'verify-binding-provenance')
    return value


def inspect_workflow_change(repo, base, head, anchor, changed):
    workflows = [p for p in changed if p.startswith('.github/workflows/')]
    require(all(p in (P5_WORKFLOW, VERIFY_WORKFLOW) for p in workflows),
            'candidate-control-change')
    accepted = inspect_p5_workflow_change(repo, base, head, anchor,
                                         [p for p in workflows if p == P5_WORKFLOW])
    if VERIFY_WORKFLOW not in workflows:
        return accepted
    _, raw = blob(repo, base, VERIFY_BINDING)
    binding = validate_verify_binding(document(raw))
    require(blob(repo, base, VERIFY_BINDING) == blob(repo, head, VERIFY_BINDING),
            'candidate-control-change')
    before, before_raw = blob(repo, base, VERIFY_WORKFLOW)
    after, after_raw = blob(repo, head, VERIFY_WORKFLOW)
    require(before == {'mode': '100644', 'sha256': binding['base_preimage']},
            'verify-workflow-preimage')
    require(after == {'mode': '100644', 'sha256': binding['final_sha256']},
            'verify-workflow-postimage')
    # Independently enforce the single authorized line even for synthetic tests.
    old_line = b"timeout-minutes: ${{ matrix.os == 'windows-2025' && 60 || 35 }}"
    new_line = b"timeout-minutes: ${{ matrix.os == 'windows-2025' && 90 || 35 }}"
    require(before_raw.count(old_line) == 1 and
            after_raw == before_raw.replace(old_line, new_line),
            'verify-timeout-only')
    accepted.append(dict(path=VERIFY_WORKFLOW, before=before, after=after,
                         binding_sha256=sha(raw), provenance=binding['provenance']))
    return accepted


def ineligible_paths(repo, base, checker):
    original = document(git(repo, 'show', base + ':' + checker['ORIGINAL']))
    amendment = document(git(repo, 'show', base + ':' + checker['AMENDMENT']))
    judge = {checker['ORIGINAL'], checker['AMENDMENT']}
    judge.update(x['path'] for x in original['files'])
    judge.update(x['path'] for x in amendment['files'])
    judge.add(amendment['existing_authorized_change']['path'])
    prefixes = {p.split('/src/test/')[0] + '/src/test/' for p in judge
                if '/service/src/test/' in p}
    plan = document(git(repo, 'show', base + ':' + POSTTRAN))
    excluded = judge | set(plan['bound_files']) | set(plan['candidate_files']) | {POSTTRAN}
    prefixes.update(('docs/factory/posttran-', 'spec/mainframe/posttran-independent/'))
    return excluded, prefixes


def api(route):
    return document(subprocess.check_output(['gh', 'api', 'repos/' + REPOSITORY + '/' + route]))


def context(repo, base, head, event, environment, query=api):
    """Check live PR provenance; a main push must be the actual approved merge."""
    require(environment.get('GITHUB_REPOSITORY') == REPOSITORY and
            event.get('repository', {}).get('full_name') == REPOSITORY, 'wrong-repository')
    kind = environment.get('GITHUB_EVENT_NAME')
    live = query('pulls/455')
    require(live['number'] == 455 and live['base']['ref'] == 'main' and
            live['base']['repo']['full_name'] == REPOSITORY and
            live['head']['repo']['full_name'] == REPOSITORY, 'wrong-pr-or-repository')
    parents = git(repo, 'show', '-s', '--format=%P', head).decode().split()
    if kind == 'pull_request':
        pr = event['pull_request']
        require(pr['number'] == 455 and live['state'] == 'open' and not live['merged'], 'wrong-pr')
        require(pr['base']['sha'] == live['base']['sha'] == base and
                pr['head']['sha'] == live['head']['sha'], 'stale-pr-context')
        require(pr['head']['repo']['full_name'] == REPOSITORY, 'fork-refused')
        candidate = live['head']['sha']
        if head != candidate:
            require(parents == [base, candidate], 'unbound-checkout')
            tree = git(repo, 'merge-tree', '--write-tree', base, candidate).decode().strip()
            require(tree == git(repo, 'rev-parse', head + '^{tree}').decode().strip(),
                    'unexpected-merge-tree')
    elif kind == 'push':
        require(event.get('ref') == 'refs/heads/main' and event.get('before') == base and
                event.get('after') == head and live['merged'] is True and
                live['merge_commit_sha'] == head and parents == [base, live['head']['sha']],
                'unbound-main-merge')
        candidate = live['head']['sha']
    else:
        raise ValueError('exception-requires-pr-or-exact-main-merge')
    return dict(repository=REPOSITORY, pr=455, candidate=candidate)


def inspect(repo, base, head, event=None, environment=None, query=api):
    base = resolve(repo, base); head = resolve(repo, head)
    checker, source = load_checker(repo, base)
    # Keep the unchanged checker's actual report and exit outcome, and independently
    # reconstruct its complete result using the same trusted-base implementation.
    expected = checker['inspect'](repo, base, head)
    process = subprocess.run([sys.executable, '-B', '-c', source.decode('utf-8'),
                              '--repo', str(repo), '--base', base, '--head', head],
                             capture_output=True, check=False)
    report = validate_raw_report(process.stdout, expected, process.returncode)
    result = dict(schema='f2-fence-exception-result/1', raw_fence_report=report,
                  raw_checker_exit=process.returncode, accepted_exceptions=[],
                  fence_requirement_met=not report['blocked_paths'], merge_authorized=False,
                  run_authorized=False)
    changed = [p for p in git(repo, 'diff', '--no-renames', '--name-only', '-z', base, head)
               .decode().split('\0') if p]
    excluded, prefixes = ineligible_paths(repo, base, checker)
    # The Java checker does not enumerate POSTTRAN. Independently refuse every
    # changed protected path, even when the raw Java report has no violations.
    require(not any(p in excluded or any(p.startswith(prefix) for prefix in prefixes)
                    for p in changed), 'judge-or-posttran-change-refused')
    durable = load_durable_binding(repo, base, head)
    durable_used = durable is not None and bool(set(changed) & set(DURABLE_RUNTIME))
    # A pending manifest never changes the historical exact-byte path.
    if not report['blocked_paths']:
        require(not durable_used, 'durable-binding-requires-engineering-exception')
        return result
    _, raw = blob(repo, base, MANIFEST)
    manifest = document(raw); validate_manifest(manifest)
    entries = {e['path']: e for e in manifest['entries']}
    durable_companions = []
    if durable_used:
        require(durable['base_anchor'] == manifest['base_anchor'], 'durable-anchor-mismatch')
        durable_companions = inspect_durable_companions(repo, base, head, durable, excluded, prefixes)
        for path in (BUDGETED, ORCHESTRATOR, EXECUTION_GATES):
            row = DURABLE_RUNTIME[path]
            entries[path] = dict(path=path, mode='100644',
                base_preimage_sha256=row['before']['sha256'],
                final_sha256=row['after']['sha256'],
                approved_change_commit=durable['approved_change_commit'],
                provenance=durable['approval'])
    anchor = resolve(repo, manifest['base_anchor'])
    require(subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', anchor, base],
                           capture_output=True).returncode == 0, 'unrelated-base-anchor')
    require(not (set(changed) & (CONTROLS | {VERIFY_BINDING})), 'candidate-control-change')
    # All of these objects must exist in base, including the validator itself.
    for path in CONTROLS:
        require(blob(repo, base, path) == blob(repo, head, path), 'candidate-control-change')
    if not durable_used:
        require(blob(repo, base, PROVIDERS) == blob(repo, head, PROVIDERS), 'providers-change-refused')
    workflow_bindings = inspect_workflow_change(repo, base, head, anchor, changed)
    require(len(set(report['blocked_paths'])) == len(report['blocked_paths']) and
            all(p in entries for p in report['blocked_paths']), 'unlisted-fence-violation')
    accepted = []
    for path in report['blocked_paths']:
        entry = entries[path]
        require(path not in excluded and not any(path.startswith(p) for p in prefixes),
                'judge-or-posttran-exception-refused')
        f2 = document(git(repo, 'show', base + ':' + checker['F2']))
        require(path in {b['path'] for b in f2['engineering_source_bindings'].values()},
                'not-f2-engineering-source')
        before, _ = blob(repo, base, path); anchored, _ = blob(repo, anchor, path)
        after, _ = blob(repo, head, path)
        require(before == anchored == {'mode': entry['mode'], 'sha256': entry['base_preimage_sha256']},
                'wrong-preimage')
        require(after == {'mode': entry['mode'], 'sha256': entry['final_sha256']}, 'wrong-postimage')
        approved, _ = blob(repo, resolve(repo, entry['approved_change_commit']), path)
        require(approved == after, 'approved-commit-content')
        accepted.append(dict(path=path, before=before, after=after, provenance=entry['provenance']))
    bound = context(repo, base, head, event or {}, environment or {}, query)
    # Re-check live provenance after object reads; stale observations never pass.
    require(context(repo, base, head, event or {}, environment or {}, query) == bound,
            'context-changed')
    result.update(accepted_exceptions=accepted, accepted_workflow_bindings=workflow_bindings,
                  fence_requirement_met=True, manifest_sha256=sha(raw), context=bound)
    if durable_used:
        result['accepted_durable_companions'] = durable_companions
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    args = parser.parse_args()
    event = document(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes()) if os.environ.get('GITHUB_EVENT_PATH') else {}
    report = inspect(args.repo, args.base, args.head, event, os.environ)
    print(json.dumps(report, sort_keys=True))
    require(report['fence_requirement_met'], 'fence-requirement-not-met')


if __name__ == '__main__':
    main()
