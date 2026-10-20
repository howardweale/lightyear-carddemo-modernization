import base64
import copy
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from lightyear_factory.authorship import CandidateHistory, FACTORY_NAME, FACTORY_EMAIL, REF, bind_candidate_changes, CICommitSigner
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import ArtifactStore, FactoryOrchestrator
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.additional_providers import AnthropicMessagesProvider
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.workspace import IsolatedWorkspace


class FactoryAuthorshipTests(unittest.TestCase):
    def setup_history(self, directory):
        root = Path(directory)
        source = root / 'source'; source.mkdir()
        (source / 'public.txt').write_bytes(b'approved toy input')
        workspace = IsolatedWorkspace(source, root / 'workspace', ('candidate',),
                                      {'public.txt': sha256(b'approved toy input').hexdigest()})
        workspace.create()
        ledger = RunLedger(root / 'events.jsonl')
        history = CandidateHistory(workspace, root / 'controller/history.git', 'fixture-run', ledger)
        history.initialize()
        (workspace.root / 'candidate').mkdir()
        (workspace.root / 'candidate/toy.txt').write_text('deliberately wrong fixture')
        return root, workspace, ledger, history, ArtifactStore(root / 'artifacts', 'fixture-run')

    def human_commit(self, history, message='human adjustment', identity=('Fixture Human', 'human@example.invalid')):
        history._git('add', '-A', '--', 'candidate')
        tree = history._git('write-tree').decode().strip()
        parent = history._git('rev-parse', REF).decode().strip()
        commit = history._git('commit-tree', '--no-gpg-sign', tree, '-p', parent,
                              data=(message + '\n').encode(), identity=identity).decode().strip()
        history._git('update-ref', REF, commit, parent)
        return commit

    def test_factory_identity_trailers_history_exclusion_and_retained_diffs(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            self.assertEqual(b'true', history._git('config', '--get', 'core.bare').strip())
            # Windows may expand the temporary root from its 8.3 alias.
            self.assertTrue((root / 'controller/history.git').samefile(history.history))
            self.assertTrue((history.history / 'HEAD').is_file())
            self.assertFalse((workspace.root / '.git').exists())
            first = history.commit(1)
            (workspace.root / 'candidate/toy.txt').write_text('known good throwaway fixture')
            final = history.commit(1)
            result = history.audit(final, artifacts)
            self.assertEqual(0, result['human_interventions'])
            self.assertEqual([first, final], [r['commit'] for r in result['commits']])
            self.assertTrue(all(r['factory'] for r in result['commits']))
            self.assertEqual({'candidate/toy.txt'}, set(history._git('ls-tree', '-r', '--name-only', final).decode().splitlines()))
            self.assertFalse((workspace.root / '.git').exists())
            self.assertEqual({'public.txt', 'candidate/toy.txt'}, set(workspace.verify_read_boundary()))
            for record in result['commits']:
                path = root / record['diff_artifact']['path']
                diff = json.loads(path.read_text())['content']['diffs'][0]
                self.assertEqual(diff['sha256'], sha256(base64.b64decode(diff['diff_base64'])).hexdigest())
            self.assertTrue(ledger.verify())

    def test_reverted_human_edit_still_counts_once(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            history.commit(1)
            target = workspace.root / 'candidate/toy.txt'
            target.write_text('human intervention')
            human = self.human_commit(history)
            target.write_text('deliberately wrong fixture')
            final = history.commit(2)
            result = history.audit(final, artifacts)
            self.assertEqual(1, result['human_interventions'])
            self.assertEqual([human], [r['commit'] for r in result['commits'] if r['human_intervention']])

    def test_wrong_run_missing_trailer_and_nonfactory_author_are_interventions(self):
        cases = [((FACTORY_NAME, FACTORY_EMAIL), 'wrong run\n\nFactory-Run: another-run\nFactory-Attempt: 1'),
                 ((FACTORY_NAME, FACTORY_EMAIL), 'missing trailer'),
                 (('Fixture Human', 'human@example.invalid'), 'forged trailer\n\nFactory-Run: fixture-run\nFactory-Attempt: 1')]
        for identity, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as d:
                root, workspace, ledger, history, artifacts = self.setup_history(d)
                final = self.human_commit(history, message, identity)
                self.assertEqual(1, history.audit(final, artifacts)['human_interventions'])

    def test_history_location_and_attempt_limits_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            with self.assertRaisesRegex(ContractError, 'visible-to-agent'):
                CandidateHistory(workspace, workspace.root / 'history.git', 'fixture-run', ledger)
            with self.assertRaisesRegex(ContractError, 'already-exists'):
                history.initialize()
            for attempt in (0, 4, True):
                with self.assertRaisesRegex(ContractError, 'attempt'):
                    history.commit(attempt)
            with self.assertRaisesRegex(ContractError, 'range'):
                history.audit('HEAD', artifacts)

    def test_merged_side_branch_human_edit_is_not_hidden_by_path_simplification(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            first = history.commit(1)
            target = workspace.root / 'candidate/toy.txt'
            target.write_text('side branch human bytes')
            human = self.human_commit(history)
            # A factory merge deliberately uses the original tree; the human
            # side commit remains in ancestry and must still be counted.
            tree = history._git('rev-parse', first + '^{tree}').decode().strip()
            final = history._git('commit-tree', '--no-gpg-sign', tree, '-p', first, '-p', human,
                                 data=b'fixture merge\n\nFactory-Run: fixture-run\nFactory-Attempt: 2\n').decode().strip()
            history._git('update-ref', REF, final, human)
            result = history.audit(final, artifacts)
            self.assertEqual(1, result['human_interventions'])
            self.assertIn(human, [r['commit'] for r in result['commits']])
            with self.assertRaisesRegex(ContractError, 'stale-end'):
                history.audit(first, artifacts)

    def test_per_file_response_provenance_requires_completed_same_run_builder_events(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = RunLedger(Path(d)/'events.jsonl')
            begun = dict(run_id='fixture-run', attempt=1, role='builder', provider='fixture',
                         configured_model_version='fixture-snapshot', request={'artifact_sha256': '1'*64})
            start = ledger.append('RUNNING', 'model-transport-started', begun)
            payload = dict(begun, start_event_sha256=start['event_sha256'], status='response', response_complete=True,
                           response=dict(artifact_type='model-response', run_id='fixture-run', role='builder',
                                         visibility='controller-encrypted', plaintext_sha256='2'*64,
                                         artifact_sha256='3'*64, ciphertext_sha256='4'*64))
            finish = ledger.append('RUNNING', 'model-transport-finished', payload)
            files = {'candidate/toy.txt': sha256(b'actual fixture bytes').hexdigest()}
            mapping = {'candidate/toy.txt': [finish['event_sha256']]}
            bound = bind_candidate_changes(ledger, 'fixture-run', 1, files, mapping)
            self.assertEqual(ledger.head_sha256, bound['ledger_head_sha256'])
            self.assertEqual('2'*64, bound['files'][0]['model_responses'][0]['response_sha256'])
            self.assertEqual(files['candidate/toy.txt'], bound['files'][0]['sha256'])
            for field, bad_value in [('run_id', 'other-run'), ('role', 'analyst'), ('attempt', 2),
                                     ('status', 'http-error'), ('response_complete', False)]:
                bad = copy.deepcopy(payload); bad[field] = bad_value
                bad_event = ledger.append('RUNNING', 'model-transport-finished', bad)
                with self.subTest(field=field), self.assertRaisesRegex(ContractError, 'unverified-response'):
                    bind_candidate_changes(ledger, 'fixture-run', 1, files, {'candidate/toy.txt':[bad_event['event_sha256']]})
            for bad_mapping in ({}, {'candidate/toy.txt': []}, {'candidate/toy.txt': ['0'*64]},
                                {'candidate/toy.txt': [finish['event_sha256']]*2}):
                with self.assertRaises(ContractError):
                    bind_candidate_changes(ledger, 'fixture-run', 1, files, bad_mapping)
            stale = RunLedger(ledger.path)
            ledger.append('BUILDING', 'another-controller-event', {})
            with self.assertRaisesRegex(ContractError, 'stale-ledger'):
                bind_candidate_changes(stale, 'fixture-run', 1, files, mapping)

    def test_signer_requires_external_trusted_main_ci_and_explicit_signature_verification(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); workspace = root/'workspace'; workspace.mkdir()
            key = root/'ci-key'; trust = root/'allowed-signers'
            # Placeholder fixture files only; this test mocks Git and never signs.
            key.write_text('not a real private key')
            trust.write_text(FACTORY_EMAIL + ' ssh-ed25519 AAAATESTFIXTURE')
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ContractError, 'trusted-main-ci-required'):
                    CICommitSigner(key, trust, workspace)
            env = dict(GITHUB_ACTIONS='true', GITHUB_REF='refs/heads/main', GITHUB_EVENT_NAME='push',
                       GITHUB_SHA='a'*40, RUNNER_TEMP=str(root))
            with patch.dict(os.environ, env, clear=True):
                signer = CICommitSigner(key, trust, workspace)
                history = SimpleNamespace(workspace=SimpleNamespace(root=workspace.resolve()),
                                          _git=Mock(side_effect=[('b'*40+'\n').encode(), b'']))
                self.assertEqual('b'*40, signer.sign(history, 'c'*40, 'd'*40, b'bound fixture message'))
                self.assertIn('-S', history._git.call_args_list[0].args)
                self.assertIn('verify-commit', history._git.call_args_list[1].args)
                self.assertNotIn('not a real private key', repr(history._git.call_args_list))
                with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request_target'}):
                    with self.assertRaisesRegex(ContractError, 'trusted-main-ci-required'):
                        signer.verify(history, 'b'*40)
                inside = workspace/'key'; inside.write_text('fixture')
                with self.assertRaisesRegex(ContractError, 'external-key-required'):
                    CICommitSigner(inside, trust, workspace)
                trust.write_text(FACTORY_EMAIL + ' ssh-ed25519 AAAATESTFIXTURE\nother ssh-ed25519 AAAA')
                with self.assertRaisesRegex(ContractError, 'single-factory-trust-required'):
                    CICommitSigner(key, trust, workspace)


    def response_event(self, ledger, attempt=1):
        begun = dict(run_id='fixture-run', attempt=attempt, role='builder', provider='fixture',
                     configured_model_version='fixture-snapshot', request={'artifact_sha256': '1'*64})
        start = ledger.append('BUILDING', 'model-transport-started', begun)
        return ledger.append('BUILDING', 'model-transport-finished', dict(
            begun, start_event_sha256=start['event_sha256'], status='response', response_complete=True,
            response=dict(artifact_type='model-response', run_id='fixture-run', role='builder',
                          visibility='controller-encrypted', plaintext_sha256='2'*64,
                          artifact_sha256='3'*64, ciphertext_sha256='4'*64)))['event_sha256']

    @staticmethod
    def fixture_sign(signer, history, tree, parent, message):
        # Real Git trees/commits, but mocked signature boundary. No crypto proof is claimed.
        return history._git('commit-tree', '--no-gpg-sign', tree, '-p', parent,
                            data=message).decode().strip()

    def test_signed_history_requires_response_binding_and_audits_historical_ledger_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            history.signer = CICommitSigner.__new__(CICommitSigner)
            original = history._git('rev-parse', REF)
            with self.assertRaisesRegex(ContractError, 'path-coverage'):
                history.commit(1)
            self.assertEqual(original, history._git('rev-parse', REF))
            with patch.object(CICommitSigner, 'sign', self.fixture_sign), patch.object(CICommitSigner, 'verify', return_value=True) as verify:
                event = self.response_event(ledger)
                first = history.commit(1, response_events={'candidate/toy.txt': [event]})
                (workspace.root/'candidate/toy.txt').write_bytes(b'repaired fixture')
                event2 = self.response_event(ledger, 2)
                final = history.commit(2, response_events={'candidate/toy.txt': [event2]})
                result = history.audit(final, artifacts)
                self.assertTrue(result['qualifies_for_factory_receipt'])
                self.assertEqual([first, final], [r['commit'] for r in result['commits']])
                self.assertEqual(2, verify.call_count)
                # Future transport events must not enter an earlier signed provenance prefix.
                first_record = next(e for e in ledger.events if e['kind']=='candidate_committed')
                prefix = first_record['payload']['provenance']['ledger_head_sha256']
                with self.assertRaisesRegex(ContractError, 'unverified-response'):
                    bind_candidate_changes(ledger, 'fixture-run', 2, {'candidate/toy.txt':'a'*64},
                                           {'candidate/toy.txt':[event2]}, ledger_head=prefix)

    def test_signed_history_never_credits_reverted_human_or_empty_unsigned_commits(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            history.signer = CICommitSigner.__new__(CICommitSigner)
            with patch.object(CICommitSigner, 'sign', self.fixture_sign), patch.object(CICommitSigner, 'verify', return_value=True):
                history.commit(1, response_events={'candidate/toy.txt':[self.response_event(ledger)]})
                target = workspace.root/'candidate/toy.txt'
                target.write_bytes(b'human edit')
                human = self.human_commit(history)
                empty = self.human_commit(history, 'empty unsigned commit')
                target.write_bytes(b'deliberately wrong fixture')
                final = history.commit(2, response_events={'candidate/toy.txt':[self.response_event(ledger, 2)]})
                result = history.audit(final, artifacts)
                self.assertFalse(result['qualifies_for_factory_receipt'])
                self.assertEqual({human, empty}, {r['commit'] for r in result['commits'] if r['human_intervention']})

    def test_signature_refusal_and_final_package_mutations_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            history.signer = CICommitSigner.__new__(CICommitSigner)
            with patch.object(CICommitSigner, 'sign', self.fixture_sign):
                final = history.commit(1, response_events={'candidate/toy.txt':[self.response_event(ledger)]})
            with patch.object(CICommitSigner, 'verify', side_effect=ContractError('candidate-signature-unverified')):
                self.assertFalse(history.audit(final, artifacts)['qualifies_for_factory_receipt'])
            target = workspace.root/'candidate/toy.txt'; old = target.read_bytes()
            with patch.object(CICommitSigner, 'verify', return_value=True):
                for mutation in ('bytes', 'extra', 'deleted'):
                    if mutation == 'bytes': target.write_bytes(b'changed after commit')
                    elif mutation == 'extra': (workspace.root/'candidate/extra.txt').write_bytes(b'extra')
                    else: target.unlink()
                    with self.subTest(mutation=mutation), self.assertRaisesRegex(ContractError, 'package-tree-mismatch'):
                        history.audit(final, artifacts)
                    target.write_bytes(old)
                    extra = workspace.root/'candidate/extra.txt'
                    if extra.exists(): extra.unlink()
                if os.name != 'nt':
                    old_mode = target.stat().st_mode
                    target.chmod(old_mode | 0o111)
                    with self.assertRaisesRegex(ContractError, 'package-mode-mismatch'):
                        history.audit(final, artifacts)
                    target.chmod(old_mode)

    def test_unsigned_legacy_history_cannot_qualify_for_factory_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            final = history.commit(1)
            result = history.audit(final, artifacts)
            self.assertFalse(result['cryptographically_verified'])
            self.assertFalse(result['qualifies_for_factory_receipt'])


    def test_strict_baseline_and_exact_broker_changes_refuse_surrounding_human_edits(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, old_ledger, old_history, artifacts = self.setup_history(d)
            ledger = RunLedger(root/'strict-events.jsonl')
            signer = CICommitSigner.__new__(CICommitSigner)
            history = CandidateHistory(workspace, root/'strict/history.git', 'fixture-run', ledger, signer=signer)
            history.initialize()
            parent = history.verify_before_build()
            target = workspace.root/'candidate/toy.txt'; before = target.read_bytes()
            target.write_bytes(b'human edit before builder')
            with self.assertRaisesRegex(ContractError, 'package-tree-mismatch'):
                history.verify_before_build()
            target.write_bytes(before)
            after = b'broker fixture replacement'
            change_set = dict(broker='lightyear-constrained-patch-broker', changes=[dict(
                path='candidate/toy.txt', before_sha256=sha256(before).hexdigest(),
                after_sha256=sha256(after).hexdigest())])
            change_set['content_sha256']=canonical_hash(change_set)
            event = self.response_event(ledger)
            target.write_bytes(after)
            with patch.object(CICommitSigner, 'sign', self.fixture_sign), patch.object(CICommitSigner, 'verify', return_value=True):
                for extra_bytes in (b'changed after broker', before):
                    target.write_bytes(extra_bytes)
                    with self.assertRaisesRegex(ContractError, 'broker-after'):
                        history.commit_applied_changes(1, parent=parent, change_set=change_set, response_events=[event])
                target.write_bytes(after)
                extra = workspace.root/'candidate/extra.txt';extra.write_bytes(b'outside broker')
                with self.assertRaisesRegex(ContractError, 'broker-after'):
                    history.commit_applied_changes(1, parent=parent, change_set=change_set, response_events=[event])
                extra.unlink()
                bad = copy.deepcopy(change_set);bad['changes'][0]['before_sha256']='0'*64
                bad['content_sha256']=canonical_hash(bad, {'content_sha256'})
                with self.assertRaisesRegex(ContractError, 'broker-before'):
                    history.commit_applied_changes(1, parent=parent, change_set=bad, response_events=[event])
                final = history.commit_applied_changes(1, parent=parent, change_set=change_set, response_events=[event])
                self.assertTrue(history.audit(final, artifacts)['qualifies_for_factory_receipt'])
                with self.assertRaisesRegex(ContractError, 'stale-parent'):
                    history.commit_applied_changes(1, parent=parent, change_set=change_set, response_events=[event])


    def test_controller_binds_one_run_to_existing_accounting_recorder_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, old_history, artifacts = self.setup_history(d)
            provider = AnthropicMessagesProvider('fixture-model', api_key='offline-fixture',
                       input_usd_per_million=1, output_usd_per_million=1, opener=lambda *a, **kw: None)
            agents = ModelAgentSet(provider)
            controller = FactoryOrchestrator(root/'source', root/'runs', agents,
                         workspace_read_manifest=workspace.read_manifest,
                         candidate_signing_paths=(root/'unused-key', root/'unused-trust'),
                         transport_encryption=(b'x'*32, 'fixture-key-id'))
            order = SimpleNamespace(max_attempts=3, content_sha256='a'*64)
            run_dir = root/'bound-run';run_dir.mkdir()
            # Scan boundary is a component fixture; no factory acceptance claim.
            agents.isolation_scan = lambda name, raw: None
            # Admission/signature boundaries mocked; no keys loaded or encryption/model calls.
            with patch.object(CICommitSigner, '__init__', return_value=None), patch.object(
                    controller, '_verify_runtime_admission', return_value={'fixture':True}):
                history, recorder = controller._bind_candidate_run(order, workspace, run_dir, artifacts, ledger)
                self.assertIsInstance(agents.bounded_provider, AccountedModelProvider)
                self.assertIs(agents.bounded_provider.provider, provider)
                self.assertIs(provider.transport_recorder, recorder)
                self.assertIs(recorder.isolation_scan, agents.isolation_scan)
                self.assertIs(recorder.ledger, ledger)
                self.assertIs(recorder.store, artifacts)
                self.assertIs(history.ledger, ledger)
                self.assertEqual('fixture-run', history.run_id)
                self.assertEqual(0, len(agents.bounded_provider.calls))
                self.assertIsNone(provider.last_transport_record)
                with self.assertRaisesRegex(ContractError, 'controller-binding-required'):
                    controller._bind_candidate_run(order, workspace, run_dir, artifacts, ledger)
                with self.assertRaisesRegex(ContractError, 'already-bound'):
                    provider.bind_transport_recorder(recorder)

    def test_controller_response_join_rejects_prior_failed_foreign_or_ambiguous_calls(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=RunLedger(Path(d)/'events.jsonl')
            provider=SimpleNamespace(last_transport_record=None)
            controller=FactoryOrchestrator(Path(d), Path(d)/'runs', SimpleNamespace(provider=provider))
            event=self.response_event(ledger)
            provider.last_transport_record={'end_event_sha256':event}
            self.assertEqual([event], controller._candidate_response_ids(ledger, 0, 'fixture-run', 1))
            for start, run, attempt in [(len(ledger.events), 'fixture-run', 1), (0, 'other-run', 1), (0, 'fixture-run', 2)]:
                with self.assertRaisesRegex(ContractError, 'builder-response-required'):
                    controller._candidate_response_ids(ledger, start, run, attempt)
            provider.last_transport_record={'end_event_sha256':'0'*64}
            with self.assertRaisesRegex(ContractError, 'builder-response-required'):
                controller._candidate_response_ids(ledger, 0, 'fixture-run', 1)
            provider.last_transport_record={'end_event_sha256':self.response_event(ledger)}
            with self.assertRaisesRegex(ContractError, 'builder-response-required'):
                controller._candidate_response_ids(ledger, 0, 'fixture-run', 1)

    def test_exported_package_binds_exact_signed_tree_and_refuses_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            history.signer = CICommitSigner.__new__(CICommitSigner)
            with patch.object(CICommitSigner, 'sign', self.fixture_sign):
                final = history.commit(1, response_events={'candidate/toy.txt':[self.response_event(ledger)]})
            with patch.object(CICommitSigner, 'verify', return_value=True):
                audit = history.audit(final, artifacts)
            scanner = lambda name,raw: None  # Component fixture, not isolation acceptance.
            destination = root/'package'
            package = history.export_verified_package(final, destination, audit, scanner)
            self.assertEqual(audit['final_package_tree_sha256'],package['tree_sha256'])
            self.assertEqual((workspace.root/'candidate/toy.txt').read_bytes(),
                             (destination/'candidate/toy.txt').read_bytes())
            original = (destination/'candidate/toy.txt').read_bytes()
            for mutation in ('bytes','extra','deleted'):
                target=destination/'candidate/toy.txt';extra=destination/'extra'
                if mutation=='bytes':target.write_bytes(b'changed')
                elif mutation=='extra':extra.write_bytes(b'extra')
                else:target.unlink()
                with self.subTest(mutation=mutation), self.assertRaisesRegex(ContractError,'^candidate-package-refused$'):
                    history.verify_exported_package(final,destination,scanner)
                target.write_bytes(original)
                if extra.exists():extra.unlink()
            if os.name!='nt':
                target=destination/'candidate/toy.txt';mode=target.stat().st_mode;target.chmod(mode|0o111)
                with self.assertRaisesRegex(ContractError,'^candidate-package-refused$'):
                    history.verify_exported_package(final,destination,scanner)
                target.chmod(mode)
            with self.assertRaisesRegex(ContractError,'candidate-package-audit-binding'):
                history.export_verified_package(final,root/'reused',audit,scanner)

    def test_package_export_scans_before_file_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            history.signer = CICommitSigner.__new__(CICommitSigner)
            with patch.object(CICommitSigner, 'sign', self.fixture_sign):
                final = history.commit(1, response_events={'candidate/toy.txt':[self.response_event(ledger)]})
            with patch.object(CICommitSigner, 'verify', return_value=True):
                audit = history.audit(final, artifacts)
            def refuse(name,raw):
                if name=='package-export-file':raise ContractError('private fixture detail')
            destination=root/'package'
            with self.assertRaisesRegex(ContractError,'^candidate-package-refused$'):
                history.export_verified_package(final,destination,audit,refuse)
            self.assertFalse((destination/'candidate/toy.txt').exists())
            self.assertFalse(any(e['kind']=='candidate_package_verified' for e in ledger.events))

    def test_package_finalization_rechecks_manifest_bytes_ref_and_signatures(self):
        # CI component fixture: mocked signatures are not real acceptance proof.
        with tempfile.TemporaryDirectory() as d:
            root, workspace, ledger, history, artifacts = self.setup_history(d)
            history.signer = CICommitSigner.__new__(CICommitSigner)
            with patch.object(CICommitSigner, 'sign', self.fixture_sign):
                final = history.commit(1, response_events={'candidate/toy.txt':[self.response_event(ledger)]})
            with patch.object(CICommitSigner, 'verify', return_value=True):
                audit = history.audit(final, artifacts)
            scanner = lambda name,raw: None
            destination = root/'package'
            package = history.export_verified_package(final, destination, audit, scanner)
            with patch.object(CICommitSigner, 'verify', return_value=True) as verify:
                result = history.revalidate_exported_package(final,destination,package,scanner,artifacts)
                self.assertGreater(verify.call_count,0)
                self.assertEqual(package['content_sha256'],result['package_manifest_sha256'])
            forged = dict(package,bytes=package['bytes']+1)
            forged['content_sha256'] = canonical_hash(forged, {'content_sha256'})
            with self.assertRaisesRegex(ContractError,'^candidate-package-finalization-refused$'):
                history.revalidate_exported_package(final,destination,forged,scanner,artifacts)
            target = destination/'candidate/toy.txt'; original = target.read_bytes()
            target.write_bytes(b'changed after export')
            with self.assertRaisesRegex(ContractError,'^candidate-package-finalization-refused$'):
                history.revalidate_exported_package(final,destination,package,scanner,artifacts)
            target.write_bytes(original)
            with patch.object(CICommitSigner, 'verify', side_effect=ContractError('signature refused')):
                with self.assertRaisesRegex(ContractError,'^candidate-package-finalization-refused$'):
                    history.revalidate_exported_package(final,destination,package,scanner,artifacts)
            history._git('update-ref', 'refs/heads/candidate', history.start_commit)
            with self.assertRaisesRegex(ContractError,'^candidate-package-finalization-refused$'):
                history.revalidate_exported_package(final,destination,package,scanner,artifacts)
            self.assertEqual(1,sum(e['kind']=='candidate_package_finalized' for e in ledger.events))
