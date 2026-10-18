import base64
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from lightyear_factory.authorship import CandidateHistory, FACTORY_NAME, FACTORY_EMAIL, REF
from lightyear_factory.contracts import ContractError
from lightyear_factory.ledger import RunLedger
from lightyear_factory.orchestrator import ArtifactStore
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
