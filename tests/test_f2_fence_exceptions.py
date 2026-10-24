"""CI-only synthetic Git fixtures; no private material, Tower or model calls."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import check_f2_fence_exceptions as policy
from tools import check_java_quality_fence as fence


class ExactF2ExceptionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.new = b'synthetic deadline refusal\n'
        self.digest = policy.sha(self.new)
        patcher = patch.object(policy, 'APPROVED_SHA', self.digest)
        patcher.start(); self.addCleanup(patcher.stop)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Synthetic')
        self.git('config', 'user.email', 'synthetic@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'core.filemode', 'true')
        source_root = Path(__file__).resolve().parents[1]
        for path in (policy.CHECKER, policy.VALIDATOR):
            self.put(path, (source_root / path).read_bytes())
        self.put(policy.GATE, b'# synthetic gate\n')
        self.put(policy.PROVIDERS, b'unchanged provider\n')
        self.put(policy.BUDGETED, b'old deadline behaviour\n')
        self.put('judge/frozen.py', b'judge\n')
        self.put('factory/service/src/test/java/OldTest.java', b'original test\n')
        original = self.doc(fence.ORIGINAL, {'files': [
            {'path': 'judge/frozen.py', 'sha256': '1' * 64},
            {'path': 'factory/service/src/test/java/OldTest.java', 'sha256': '2' * 64}]})
        self.doc(fence.AMENDMENT, {'original_manifest_sha256': original['sha256'],
            'files': [{'path': 'judge/pom.xml', 'sha256': '3' * 64}],
            'existing_authorized_change': {'path': 'judge/generator.py', 'sha256': '4' * 64}})
        scope = self.doc('scope.json', {'candidate_directory': 'candidate',
            'interfaces': {'source_path': 'interface.cbl'}})
        workspace = self.doc('workspace.json', {'worker/input.txt': '5' * 64})
        self.doc(fence.F2, {'schema': 'copau-f2-preparation/1',
            'engineering_source_bindings': {'provider': {'path': policy.BUDGETED},
                                           'controller': {'path': 'orchestrator.py'}},
            'bindings': {'scope': scope, 'workspace': workspace},
            'work_order': {'scope': {'allowed_paths': ['candidate']}}})
        self.doc('docs/factory/copau-f8-support-bindings-synthetic.json',
                 {'selection': {'source_bindings': [{'path': 'support.py', 'sha256': '6' * 64}]}})
        self.doc(policy.POSTTRAN, {'bound_files': {'posttran.py': '7' * 64},
                                  'candidate_files': {'candidate-posttran.py': '8' * 64}})
        anchor = self.commit('anchor')
        before = policy.sha((self.root / policy.BUDGETED).read_bytes())
        self.put(policy.BUDGETED, self.new)
        approved = self.commit('approved synthetic delta')
        self.git('checkout', '--detach', '-q', anchor)
        when = '2026-10-24T15:23:34-07:00'
        self.manifest = dict(schema='f2-exact-byte-exceptions/1', repository=policy.REPOSITORY,
            base_anchor=anchor, activation='trusted-base-only-after-exact-head-merge-approval',
            identity_limitation="Operator-chat attribution is not independently authenticated; the agent shares Howard's GitHub identity. Open after-run item.",
            authority=dict(merge=False, run=False, signing=False, spend=False, gap_acceptance=False),
            entries=[dict(repository=policy.REPOSITORY, pr=455, path=policy.BUDGETED,
                mode='100644', base_preimage_sha256=before, final_sha256=self.digest,
                approved_change_commit=approved, provenance=dict(source='operator-chat',
                    approved_by='Howard Weale', recorded_at_pt=when, exact_sha256=self.digest,
                    statement='approved by Howard in the operator chat, ' + when + ', exact hash ' + self.digest,
                    github_identity_is_human_proof=False))])
        self.doc(policy.MANIFEST, self.manifest)
        self.base = self.commit('trusted policy')
        self.put(policy.BUDGETED, self.new)
        self.head = self.commit('candidate')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args],
                                       stderr=subprocess.PIPE).decode().strip()

    def put(self, path, raw):
        p = self.root / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw)

    def doc(self, path, value):
        raw = json.dumps(value, sort_keys=True).encode()
        self.put(path, raw)
        return {'path': path, 'sha256': hashlib.sha256(raw).hexdigest()}

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '--no-gpg-sign', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def live(self):
        return dict(number=455, state='open', merged=False, merge_commit_sha=None,
                    base=dict(sha=self.base, ref='main', repo={'full_name': policy.REPOSITORY}),
                    head=dict(sha=self.head, repo={'full_name': policy.REPOSITORY}))

    def run_check(self, event=None, env=None, live=None, checkout=None):
        event = event if event is not None else {'repository': {'full_name': policy.REPOSITORY},
                                                'pull_request': self.live()}
        env = env if env is not None else dict(GITHUB_REPOSITORY=policy.REPOSITORY,
                                               GITHUB_EVENT_NAME='pull_request')
        return policy.inspect(self.root, self.base, checkout or self.head, event, env,
                              lambda route: live if live is not None else self.live())

    def update_policy(self, transform):
        self.git('checkout', '--detach', '-q', self.base)
        value = copy.deepcopy(self.manifest); transform(value)
        self.doc(policy.MANIFEST, value); self.base = self.commit('different base policy')
        self.put(policy.BUDGETED, self.new); self.head = self.commit('candidate again')

    def test_exact_approval_keeps_raw_failure_but_validates_only_fence_requirement(self):
        report = self.run_check()
        self.assertTrue(report['fence_requirement_met'])
        self.assertFalse(report['raw_fence_report']['merge_permitted'])
        self.assertEqual(1, report['raw_checker_exit'])
        self.assertEqual([policy.BUDGETED], report['raw_fence_report']['blocked_paths'])
        self.assertFalse(report['merge_authorized']); self.assertFalse(report['run_authorized'])
        self.assertEqual(self.digest, report['accepted_exceptions'][0]['after']['sha256'])

    def test_wrong_preimage_and_postimage_refuse(self):
        self.put(policy.BUDGETED, b'unapproved bytes\n'); self.head = self.commit('wrong bytes')
        with self.assertRaisesRegex(ValueError, 'wrong-postimage'):
            self.run_check()
        self.update_policy(lambda m: m['entries'][0].update(base_preimage_sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'wrong-preimage'):
            self.run_check()

    def test_wrong_repository_pr_fork_and_obsolete_live_head_refuse(self):
        for change in ('repository', 'pr', 'fork', 'head', 'base', 'event'):
            event = {'repository': {'full_name': policy.REPOSITORY}, 'pull_request': self.live()}
            env = dict(GITHUB_REPOSITORY=policy.REPOSITORY, GITHUB_EVENT_NAME='pull_request')
            live = self.live()
            if change == 'repository': env['GITHUB_REPOSITORY'] = 'other/repository'
            if change == 'pr': event['pull_request']['number'] = 456
            if change == 'fork': live['head']['repo']['full_name'] = 'fork/repository'
            if change == 'head': live['head']['sha'] = '0' * 40
            if change == 'base': live['base']['sha'] = '0' * 40
            if change == 'event': env['GITHUB_EVENT_NAME'] = 'workflow_dispatch'
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_check(event=event, env=env, live=live)

    def test_mode_rename_extra_fenced_path_and_candidate_manifest_refuse(self):
        original = self.head
        for change in ('mode', 'rename', 'extra', 'manifest', 'checker', 'validator', 'gate', 'workflow', 'providers'):
            self.git('checkout', '--detach', '-q', original)
            if change == 'mode':
                self.git('update-index', '--chmod=+x', policy.BUDGETED)
                self.git('commit', '--no-gpg-sign', '-qm', 'mode')
                self.head = self.git('rev-parse', 'HEAD')
            else:
                if change == 'rename': self.git('mv', policy.BUDGETED, 'renamed.py')
                elif change == 'extra': self.put('orchestrator.py', b'new fenced delta\n')
                else:
                    path = {'manifest': policy.MANIFEST, 'checker': policy.CHECKER,
                            'validator': policy.VALIDATOR, 'gate': policy.GATE,
                            'workflow': '.github/workflows/fake.yml', 'providers': policy.PROVIDERS}[change]
                    self.put(path, b'candidate substitution\n')
                self.head = self.commit(change)
            with self.subTest(change=change), self.assertRaises(ValueError): self.run_check()

    def test_every_judge_inventory_path_and_new_test_refuse(self):
        original = self.head
        checker, _ = policy.load_checker(self.root, self.base)
        excluded, _ = policy.ineligible_paths(self.root, self.base, checker)
        for path in sorted(excluded | {'factory/service/src/test/java/NewTest.java'}):
            self.git('checkout', '--detach', '-q', original)
            self.put(path, b'changed protected object\n'); self.head = self.commit('judge refusal')
            with self.subTest(path=path), self.assertRaises(ValueError): self.run_check()

    def test_manifest_provenance_and_exact_fields_refuse_mutations(self):
        changes = [lambda m: m['entries'][0].pop('provenance'),
                   lambda m: m['entries'][0]['provenance'].update(source='github-comment'),
                   lambda m: m['entries'][0]['provenance'].update(approved_by='Agent'),
                   lambda m: m['entries'][0]['provenance'].update(exact_sha256='0' * 64),
                   lambda m: m['entries'][0]['provenance'].update(github_identity_is_human_proof=True),
                   lambda m: m['entries'][0].update(repository='other/repository'),
                   lambda m: m['entries'][0].update(pr=456),
                   lambda m: m['entries'][0].update(path='src/**'),
                   lambda m: m['entries'][0].update(path='orchestrator.py'),
                   lambda m: m['entries'][0].update(mode='100755'),
                   lambda m: m.update(expires='tomorrow'),
                   lambda m: m['entries'].append(copy.deepcopy(m['entries'][0]))]
        for index, change in enumerate(changes):
            value = copy.deepcopy(self.manifest); change(value)
            with self.subTest(index=index), self.assertRaises(ValueError): policy.validate_manifest(value)

    def test_incomplete_inconsistent_and_error_reports_refuse(self):
        good = fence.inspect(self.root, self.base, self.head)
        for key in good:
            bad = dict(good); del bad[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                policy.validate_raw_report(json.dumps(bad), good, 1)
        for bad, status in ((dict(good, blocked_paths=[]), 1),
                            (dict(good, merge_permitted=True), 1), (good, 0), (good, 2)):
            with self.assertRaises(ValueError): policy.validate_raw_report(json.dumps(bad), good, status)
        with self.assertRaises(ValueError): policy.document('{"a":1,"a":2}')

    def test_judge_or_posttran_overlap_never_becomes_eligible(self):
        original_base = self.base
        for key in ('judge', 'posttran'):
            self.git('checkout', '--detach', '-q', original_base)
            if key == 'judge':
                raw = json.loads((self.root / fence.AMENDMENT).read_bytes())
                raw['files'].append({'path': policy.BUDGETED, 'sha256': '9' * 64})
                self.doc(fence.AMENDMENT, raw)
            else:
                self.doc(policy.POSTTRAN, {'bound_files': {policy.BUDGETED: '9' * 64}, 'candidate_files': {}})
            self.base = self.commit('overlapping protection')
            self.put(policy.BUDGETED, self.new); self.head = self.commit('candidate')
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'judge-or-posttran'):
                self.run_check()

    def test_synthetic_merge_and_exact_merged_main_push(self):
        tree = self.git('rev-parse', self.head + '^{tree}')
        merge = self.git('-c', 'commit.gpgsign=false', 'commit-tree', tree,
                         '-p', self.base, '-p', self.head, '-m', 'synthetic merge')
        self.assertTrue(self.run_check(checkout=merge)['fence_requirement_met'])
        live = self.live(); live.update(state='closed', merged=True, merge_commit_sha=merge)
        event = dict(repository={'full_name': policy.REPOSITORY}, ref='refs/heads/main',
                     before=self.base, after=merge)
        env = dict(GITHUB_REPOSITORY=policy.REPOSITORY, GITHUB_EVENT_NAME='push')
        self.assertTrue(self.run_check(event=event, env=env, live=live, checkout=merge)['fence_requirement_met'])
        live['merge_commit_sha'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'unbound-main-merge'):
            self.run_check(event=event, env=env, live=live, checkout=merge)

    def test_missing_base_manifest_cannot_be_supplied_by_candidate(self):
        anchor = self.manifest['base_anchor']
        with self.assertRaisesRegex(ValueError, 'missing-or-ambiguous-blob'):
            policy.inspect(self.root, anchor, self.head)

    def test_live_context_change_between_reads_refuses(self):
        event = {'repository': {'full_name': policy.REPOSITORY}, 'pull_request': self.live()}
        env = dict(GITHUB_REPOSITORY=policy.REPOSITORY, GITHUB_EVENT_NAME='pull_request')
        replies = [self.live(), self.live()]
        replies[1]['head']['sha'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'stale-pr-context'):
            policy.inspect(self.root, self.base, self.head, event, env, lambda route: replies.pop(0))

    def test_unfenced_change_needs_no_exception_or_live_api(self):
        self.git('checkout', '--detach', '-q', self.base)
        self.put('unfenced.txt', b'public documentation\n'); self.head = self.commit('unfenced')
        report = policy.inspect(self.root, self.base, self.head,
                                query=lambda route: self.fail('unexpected API call'))
        self.assertTrue(report['raw_fence_report']['merge_permitted'])
        self.assertEqual([], report['accepted_exceptions'])


class FencePolicyIntegrationTests(unittest.TestCase):
    def test_lint_loads_policy_from_base_and_keeps_original_checker(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'tools/ci_gate.py').read_text(encoding='utf-8')
        self.assertIn("policy_path = 'tools/check_f2_fence_exceptions.py'", source)
        self.assertIn("['git', 'show', base + ':' + policy_path]", source)
        self.assertNotIn('import check_f2_fence_exceptions', source)
        workflow = (root / '.github/workflows/required-ci.yml').read_text(encoding='utf-8')
        self.assertIn('python -B -m unittest test_f2_fence_exceptions -v', workflow)
        self.assertIn('GH_TOKEN: ${{ github.token }}', workflow)

    def test_public_manifest_has_only_the_approved_budgeted_provider(self):
        root = Path(__file__).resolve().parents[1]
        value = policy.document((root / policy.MANIFEST).read_bytes())
        entry = policy.validate_manifest(value)
        self.assertEqual(policy.APPROVED_SHA, entry['final_sha256'])
        self.assertEqual('operator-chat', entry['provenance']['source'])
        checker_sha = 'e520d6a7290a949839c38ae2407c20e67c3bc8fe9ea4a75fc9489737ba063339'
        self.assertEqual(checker_sha, policy.sha((root / policy.CHECKER).read_bytes()))
