"""CI-only tests for the inactive durable-binding review proposal.

Synthetic approval dictionaries below exercise parsing only and grant no authority.
"""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools import check_f2_fence_exceptions as gate


class DurableBindingTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        self.pending = json.loads(Path(gate.DURABLE_BINDING).read_text(encoding='utf-8'))
        # Parsing fixtures stay pending even after a separately approved activation.
        self.pending.update(status='pending-exact-hash-approval', approval=None,
                            approved_change_commit=None)
        self.assertEqual(self.pending['status'], 'pending-exact-hash-approval')

    def synthetic_approved(self):
        value = copy.deepcopy(self.pending)
        hashes = {p: row['after']['sha256'] for p, row in gate.DURABLE_RUNTIME.items()}
        stamp = '2026-10-27T00:00:00-07:00'  # Synthetic parser fixture, not an operator event.
        exact = gate.sha(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode())
        value.update(status='approved-exact-hashes', approved_change_commit='a'*40,
            approval=dict(source='operator-chat', approved_by='Howard Weale',
                recorded_at_pt=stamp, exact_sha256=hashes,
                statement='approved by Howard in the operator chat, '+stamp+', exact runtime hash set '+exact+gate.DURABLE_EVIDENCE_LINK,
                github_identity_is_human_proof=False))
        return value

    def test_pending_binding_is_inert_and_cannot_carry_approval(self):
        self.assertIsNone(gate.validate_durable_binding(self.pending))
        for field, value in (('approval', {}), ('approved_change_commit', 'a'*40)):
            bad = copy.deepcopy(self.pending); bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                gate.validate_durable_binding(bad)

    def test_exact_entry_set_rejects_omission_duplicate_extra_mode_and_byte_changes(self):
        variants = []
        bad = copy.deepcopy(self.pending); bad['entries'].pop(); variants.append(bad)
        bad = copy.deepcopy(self.pending); bad['entries'][1] = bad['entries'][0]; variants.append(bad)
        bad = copy.deepcopy(self.pending); bad['entries'].append(bad['entries'][0]); variants.append(bad)
        for field, value in (('mode', '100755'), ('sha256', '0'*64)):
            bad = copy.deepcopy(self.pending); bad['entries'][0]['after'][field] = value; variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                gate.validate_durable_binding(bad)

    def test_approved_parser_requires_exact_hash_set_and_provenance(self):
        value = self.synthetic_approved()
        self.assertEqual(gate.validate_durable_binding(value), value)
        for field, replacement in (('exact_sha256', {}), ('github_identity_is_human_proof', True),
                                   ('statement', 'approved'), ('recorded_at_pt', 'unknown')):
            bad = copy.deepcopy(value); bad['approval'][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                gate.validate_durable_binding(bad)

    def test_candidate_cannot_supply_or_modify_trusted_binding(self):
        with patch.object(gate, 'git', side_effect=[b'', b'candidate binding']):
            with self.assertRaisesRegex(ValueError, 'candidate-durable-binding-refused'):
                gate.load_durable_binding('repo', 'base', 'head')
        with patch.object(gate, 'git', return_value=b'base binding'), patch.object(
                gate, 'blob', side_effect=[({'mode':'100644'}, b'base'), ({'mode':'100644'}, b'changed')]):
            with self.assertRaisesRegex(ValueError, 'candidate-durable-binding-refused'):
                gate.load_durable_binding('repo', 'base', 'head')

    def test_companion_set_checks_preimages_postimages_approved_commit_and_protected_paths(self):
        binding = self.synthetic_approved()
        def blob(repo, ref, path):
            row = gate.DURABLE_RUNTIME[path]
            return (row['before'] if ref == 'base' else row['after']), b'synthetic'
        with patch.object(gate, 'resolve', return_value='approved'), patch.object(gate, 'git', return_value=b''), patch.object(gate, 'blob', side_effect=blob):
            result = gate.inspect_durable_companions('repo', 'base', 'head', binding, set(), set())
            self.assertEqual({x['path'] for x in result}, set(gate.DURABLE_RUNTIME))
            protected = {binding['entries'][0]['path']}
            with self.assertRaisesRegex(ValueError, 'judge-or-posttran-exception-refused'):
                gate.inspect_durable_companions('repo', 'base', 'head', binding, protected, set())
        for bad_ref in ('base', 'head', 'approved'):
            def bad_blob(repo, ref, path):
                row, raw = blob(repo, ref, path)
                return (dict(row, sha256='0'*64) if ref == bad_ref and row is not None else row), raw
            with self.subTest(ref=bad_ref), patch.object(gate, 'resolve', return_value='approved'), patch.object(gate, 'git', return_value=b''), patch.object(gate, 'blob', side_effect=bad_blob), self.assertRaises(ValueError):
                gate.inspect_durable_companions('repo', 'base', 'head', binding, set(), set())
        with patch.object(gate, 'resolve', return_value='approved'), patch.object(gate, 'git', return_value=b'unexpected new-file preimage'), patch.object(gate, 'blob', side_effect=blob):
            with self.assertRaisesRegex(ValueError, 'durable-preimage-not-absent'):
                gate.inspect_durable_companions('repo', 'base', 'head', binding, set(), set())

    def inspect_fixture(self, *, active=False, changed=None, faults=(), pending=True):
        """Run the dispatcher in CI with synthetic I/O, never real approval or API.

        Parsing, dispatch, companion checks, legacy checks, and live-context
        validation remain real. Git/blob/raw-checker boundaries are synthetic;
        these tests do not establish real Git or deployed runtime integration.
        """
        from contextlib import ExitStack
        from types import SimpleNamespace
        root = Path(__file__).resolve().parents[1]
        legacy = json.loads((root / gate.MANIFEST).read_text(encoding='utf-8'))
        binding = self.synthetic_approved() if active else copy.deepcopy(self.pending)
        base, head = 'b'*40, 'c'*40
        anchor = legacy['base_anchor']
        if changed is None:
            changed = sorted(gate.DURABLE_RUNTIME) if active else [gate.BUDGETED, gate.ORCHESTRATOR]
        blocked = [p for p in changed if p in (gate.BUDGETED, gate.ORCHESTRATOR, gate.EXECUTION_GATES, 'extra-fenced.py')]
        report = dict(schema='java-quality-fence/1', base=base, head=head,
            fence_sha256='1'*64, fenced_paths=[], fenced_prefixes=[], source_records=[],
            blocked_paths=blocked, merge_permitted=not bool(blocked), automatic_expiry=False)
        source = b'# synthetic checker process boundary\n'
        checker = dict(ORIGINAL='original.json', AMENDMENT='amendment.json', F2='f2.json',
                       inspect=lambda *args: copy.deepcopy(report))
        entries = {e['path']: e for e in legacy['entries']}
        def encoded(value):
            return json.dumps(value, sort_keys=True).encode()
        def read_blob(repo, ref, path):
            if path == gate.DURABLE_BINDING:
                data = encoded(binding)
                if 'candidate-binding' in faults and ref == head:
                    data += b' '
                return dict(mode='100644', sha256=gate.sha(data)), data
            if path == gate.MANIFEST:
                data = encoded(legacy)
                return dict(mode='100644', sha256=gate.sha(data)), data
            if path in gate.DURABLE_RUNTIME:
                row = gate.DURABLE_RUNTIME[path]
                if active:
                    metadata = row['before'] if ref in (base, anchor) else row['after']
                    if 'companion-bytes' in faults and ref == head and path == gate.PROVIDERS:
                        metadata = dict(metadata, sha256='0'*64)
                    if 'approved-content' in faults and ref == binding['approved_change_commit']:
                        metadata = dict(metadata, sha256='0'*64)
                elif path in entries:
                    entry = entries[path]
                    metadata = dict(mode='100644', sha256=entry[
                        'base_preimage_sha256' if ref in (base, anchor) else 'final_sha256'])
                else:
                    metadata = row['before']
                if 'legacy-provider' in faults and path == gate.PROVIDERS and ref == head:
                    metadata = dict(metadata, sha256='0'*64)
                return metadata, b'synthetic blob boundary'
            data = b'unchanged control'
            return dict(mode='100644', sha256=gate.sha(data)), data
        def git(repo, *args):
            if args[0] == 'diff':
                return ('\0'.join(changed) + '\0').encode()
            if args[0] == 'rev-parse':
                return args[-1].split('^')[0].encode()
            if args[0] == 'ls-tree':
                path = args[-1]
                if path == gate.DURABLE_BINDING:
                    return b'present' if pending or active else b''
                if path.endswith('/transport_journal.py'):
                    return b'present' if 'new-preimage' in faults else b''
                raise AssertionError(args)
            if args[:3] == ('show', '-s', '--format=%P'):
                return base.encode()
            if args[0] == 'show':
                path = args[-1].split(':', 1)[1]
                if path == 'original.json': return encoded(dict(files=[]))
                if path == 'amendment.json':
                    return encoded(dict(files=[], existing_authorized_change=dict(path='judge/generator.py')))
                if path == gate.POSTTRAN:
                    protected = {gate.PROVIDERS:'0'*64} if 'posttran-overlap' in faults else {}
                    return encoded(dict(bound_files=protected, candidate_files={}))
                if path == 'f2.json':
                    paths = (gate.BUDGETED,) if 'missing-engineering' in faults else (gate.BUDGETED, gate.ORCHESTRATOR, gate.EXECUTION_GATES)
                    return encoded(dict(engineering_source_bindings={p:dict(path=p) for p in paths}))
            raise AssertionError(args)
        def process(args, **kwargs):
            if args[0] == 'git':
                return SimpleNamespace(returncode=1 if 'unrelated-anchor' in faults else 0)
            return SimpleNamespace(returncode=1 if blocked else 0, stdout=encoded(report))
        live = dict(number=455, state='open', merged=False,
            base=dict(sha=base, ref='main', repo=dict(full_name=gate.REPOSITORY)),
            head=dict(sha=head, repo=dict(full_name=gate.REPOSITORY)))
        event = dict(repository=dict(full_name=gate.REPOSITORY), pull_request=copy.deepcopy(live))
        env = dict(GITHUB_REPOSITORY=gate.REPOSITORY, GITHUB_EVENT_NAME='pull_request')
        queries = []
        def query(route):
            queries.append(route)
            value = copy.deepcopy(live)
            if 'live-head' in faults and len(queries) == 2: value['head']['sha'] = 'd'*40
            if 'fork' in faults: value['head']['repo']['full_name'] = 'fork/repository'
            return value
        with ExitStack() as stack:
            stack.enter_context(patch.object(gate, 'load_checker', return_value=(checker, source)))
            stack.enter_context(patch.object(gate, 'blob', side_effect=read_blob))
            stack.enter_context(patch.object(gate, 'git', side_effect=git))
            stack.enter_context(patch.object(gate.subprocess, 'run', side_effect=process))
            result = gate.inspect('synthetic-repo', base, head, event, env, query)
        return result, queries

    def test_dispatch_pending_and_absent_bindings_preserve_legacy_profile(self):
        reports = []
        for pending in (False, True):
            result, queries = self.inspect_fixture(pending=pending)
            self.assertTrue(result['fence_requirement_met'])
            self.assertFalse(result['raw_fence_report']['merge_permitted'])
            self.assertEqual(1, result['raw_checker_exit'])
            self.assertEqual({gate.BUDGETED, gate.ORCHESTRATOR},
                             {e['path'] for e in result['accepted_exceptions']})
            self.assertNotIn('accepted_durable_companions', result)
            self.assertEqual(['pulls/455', 'pulls/455'], queries)
            self.assertFalse(result['merge_authorized'])
            self.assertFalse(result['run_authorized'])
            reports.append(result)
        self.assertEqual(reports[0], reports[1])
        with self.assertRaisesRegex(ValueError, 'providers-change-refused'):
            self.inspect_fixture(faults=('legacy-provider',))

    def test_dispatch_unfenced_pending_is_inert_and_has_no_live_query(self):
        result, queries = self.inspect_fixture(changed=['public-note.txt'])
        self.assertTrue(result['fence_requirement_met'])
        self.assertEqual([], result['accepted_exceptions'])
        self.assertEqual([], queries)
        with self.assertRaisesRegex(ValueError, 'durable-binding-requires-engineering-exception'):
            self.inspect_fixture(active=True, changed=[gate.PROVIDERS])
        with self.assertRaisesRegex(ValueError, 'candidate-durable-binding-refused'):
            self.inspect_fixture(changed=['public-note.txt'], faults=('candidate-binding',))

    def test_dispatch_approved_fixture_requires_all_companions_and_keeps_raw_failure(self):
        result, queries = self.inspect_fixture(active=True)
        self.assertTrue(result['fence_requirement_met'])
        self.assertFalse(result['raw_fence_report']['merge_permitted'])
        self.assertEqual(1, result['raw_checker_exit'])
        self.assertEqual(set(gate.DURABLE_RUNTIME),
                         {e['path'] for e in result['accepted_durable_companions']})
        for entry in result['accepted_exceptions']:
            self.assertEqual(gate.DURABLE_RUNTIME[entry['path']]['after'], entry['after'])
        self.assertEqual(2, len(queries))
        self.assertFalse(result['merge_authorized'])
        self.assertFalse(result['run_authorized'])
        for fault in ('companion-bytes', 'approved-content', 'new-preimage', 'missing-engineering'):
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.inspect_fixture(active=True, faults=(fault,))

    def test_dispatch_protected_controls_extra_fence_and_workflows_remain_refused(self):
        for extra in (gate.VALIDATOR, gate.CHECKER, gate.MANIFEST, gate.GATE,
                      gate.WORKFLOW_BINDING, gate.VERIFY_BINDING, gate.POSTTRAN,
                      'docs/factory/posttran-extra.json', 'judge/generator.py',
                      'extra-fenced.py', '.github/workflows/unapproved.yml'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.inspect_fixture(active=True, changed=sorted(gate.DURABLE_RUNTIME)+[extra])
        with self.assertRaisesRegex(ValueError, 'judge-or-posttran-change-refused'):
            self.inspect_fixture(active=True, faults=('posttran-overlap',))

    def test_dispatch_approved_fixture_still_requires_anchor_and_fresh_same_repo_context(self):
        for fault in ('unrelated-anchor', 'live-head', 'fork', 'candidate-binding'):
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.inspect_fixture(active=True, faults=(fault,))


    def test_unified_gates_route_is_exact_and_keeps_raw_fence_failure(self):
        result, queries = self.inspect_fixture(active=True)
        accepted = {e['path']: e for e in result['accepted_exceptions']}
        self.assertIn(gate.EXECUTION_GATES, accepted)
        self.assertEqual(gate.DURABLE_RUNTIME[gate.EXECUTION_GATES]['after'],
                         accepted[gate.EXECUTION_GATES]['after'])
        self.assertEqual(7, len(result['accepted_durable_companions']))
        self.assertFalse(result['raw_fence_report']['merge_permitted'])
        self.assertEqual(1, result['raw_checker_exit'])
        self.assertEqual(['pulls/455', 'pulls/455'], queries)
        self.assertFalse(result['merge_authorized'])
        self.assertFalse(result['run_authorized'])
        with self.assertRaisesRegex(ValueError, 'not-f2-engineering-source'):
            self.inspect_fixture(active=True, faults=('missing-engineering',))
        with self.assertRaisesRegex(ValueError, 'unlisted-fence-violation'):
            self.inspect_fixture(active=True,
                changed=sorted(gate.DURABLE_RUNTIME)+['extra-fenced.py'])

    def test_unified_provenance_link_and_gates_hash_cannot_be_substituted(self):
        value = self.synthetic_approved()
        for replacement in ('', gate.DURABLE_EVIDENCE_LINK.replace('#sha256=', '#wrong=')):
            bad = copy.deepcopy(value)
            bad['approval']['statement'] = bad['approval']['statement'].replace(
                gate.DURABLE_EVIDENCE_LINK, replacement)
            with self.subTest(replacement=replacement), self.assertRaisesRegex(
                    ValueError, 'durable-approval-statement'):
                gate.validate_durable_binding(bad)
        bad = copy.deepcopy(value)
        bad['approval']['exact_sha256'][gate.EXECUTION_GATES] = '0'*64
        with self.assertRaisesRegex(ValueError, 'durable-approval-hashes'):
            gate.validate_durable_binding(bad)
