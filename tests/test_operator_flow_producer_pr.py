"""CI-only untrusted relationships and actual Git reads; no service/admission claim."""
from copy import deepcopy
import json, subprocess, tempfile, unittest
from pathlib import Path
from tools.ci.operator_flow_producer_pr import (
    parse_approval, relationships, check_source, WORKFLOW, JOB, LABEL, REPOSITORY)
from tools.ci.operator_flow_ci_prerequisite import validate_prior_component, REQUIRED_STEPS


def configuration():
    return dict(executable='a'*40, expected_main='b'*40, validation_run_id=10,
        pr_number=455, fixture_only=True, scope='disposable-producer-only', trigger_label=LABEL)


class ProducerPRRecords(unittest.TestCase):
    def setUp(self):
        self.approval = configuration()
        self.pr = dict(number=455, state='open', head=dict(sha='a'*40,
            repo=dict(full_name=REPOSITORY)), base=dict(repo=dict(full_name=REPOSITORY)))
        self.event = dict(action='labeled', label=dict(name=LABEL), number=455,
            repository=dict(full_name=REPOSITORY), pull_request=deepcopy(self.pr))
        self.run = dict(id=20, event='pull_request', status='in_progress', run_attempt=1,
            head_sha='a'*40, head_repository=dict(full_name=REPOSITORY), workflow_id=7)
        self.job = dict(id=30, run_id=20, head_sha='a'*40, name=JOB, status='in_progress', run_attempt=1)

    def check(self):
        return relationships(self.event, self.run, self.job, self.pr, self.approval, 20)

    def test_exact_fixture_configuration(self):
        self.assertEqual(parse_approval(json.dumps(self.approval)), self.approval)

    def test_configuration_refuses_missing_extra_duplicate_and_nonfinite(self):
        for raw in ('', '{}', json.dumps(dict(self.approval, extra=True)),
                json.dumps(self.approval)[:-1]+',"fixture_only":true}', '{"value":NaN}'):
            with self.assertRaises(ValueError): parse_approval(raw)

    def test_configuration_refuses_scope_types_and_heads(self):
        for key, value in (('fixture_only', 1), ('scope', 'production'), ('trigger_label', 'other'),
                ('pr_number', True), ('validation_run_id', '10'), ('executable', 'A'*40),
                ('expected_main', ''), ('validation_run_id', 0)):
            candidate = dict(self.approval); candidate[key] = value
            with self.assertRaises(ValueError): parse_approval(json.dumps(candidate))

    def test_matching_records_return_no_authority(self):
        self.assertIsNone(self.check())

    def test_wrong_action_label_and_pr_refuse(self):
        for key, value in (('action', 'synchronize'), ('label', dict(name='other')),
                ('number', 456), ('number', True)):
            before = deepcopy(self.event); self.event[key] = value
            with self.assertRaises(ValueError): self.check()
            self.event = before

    def test_fork_event_and_live_head_movement_refuse(self):
        for pr in (self.event['pull_request'], self.pr):
            original = deepcopy(pr)
            for field in ('head', 'base'):
                pr[field]['repo']['full_name'] = 'other/repo'
                with self.assertRaises(ValueError): self.check()
                pr.clear(); pr.update(deepcopy(original))
            pr['head']['sha'] = 'c'*40
            with self.assertRaises(ValueError): self.check()
            pr.clear(); pr.update(original)

    def test_service_merge_revision_is_not_normalized_to_E(self):
        for row in (self.run, self.job):
            row['head_sha'] = 'c'*40
            with self.assertRaisesRegex(ValueError, 'producer-service-head'): self.check()
            row['head_sha'] = 'a'*40

    def test_wrong_run_attempt_repository_and_dispatch_refuse(self):
        for key, value in (('event', 'workflow_dispatch'), ('run_attempt', 2),
                ('run_attempt', True), ('id', 21), ('status', 'completed'),
                ('head_repository', dict(full_name='other/repo')), ('workflow_id', True)):
            before = deepcopy(self.run); self.run[key] = value
            with self.assertRaises(ValueError): self.check()
            self.run = before

    def test_wrong_job_identity_refuses(self):
        for key, value in (('name', 'operator-consumer'), ('run_id', 21), ('run_attempt', 2),
                ('id', True), ('status', 'completed')):
            before = deepcopy(self.job); self.job[key] = value
            with self.assertRaises(ValueError): self.check()
            self.job = before


class ProducerPriorCIRecords(unittest.TestCase):
    def setUp(self):
        self.producer = dict(id=20, head_sha='a'*40, event='pull_request', status='in_progress',
            run_attempt=1, head_repository=dict(full_name=REPOSITORY), created_at='2026-10-30T03:00:00Z')
        self.run = dict(id=10, head_sha='a'*40, event='pull_request', status='completed',
            conclusion='success', run_attempt=1, head_repository=dict(full_name=REPOSITORY),
            workflow_id=7, created_at='2026-10-30T01:00:00Z')
        self.workflow = dict(id=7, path='.github/workflows/operator-flow-component.yml')
        self.job = dict(id=30, run_id=10, head_sha='a'*40, name='operator-component',
            status='completed', conclusion='success', started_at='2026-10-30T01:01:00Z',
            completed_at='2026-10-30T02:00:00Z',
            steps=[dict(name=n, status='completed', conclusion='success') for n in REQUIRED_STEPS])

    def check(self):
        return validate_prior_component('a'*40, 20, 10, self.producer, self.run, self.workflow,
            dict(total_count=1, jobs=[self.job]), producer_event='pull_request')

    def test_pr_producer_requires_completed_prior_component(self):
        self.assertEqual(self.check()['validation_run_id'], 10)
        self.producer['event'] = 'workflow_dispatch'
        with self.assertRaises(ValueError): self.check()

    def test_pr_producer_created_before_component_finish_refuses(self):
        self.job['completed_at'] = '2026-10-30T03:00:01Z'
        with self.assertRaisesRegex(ValueError, 'prior-ci-must-precede-producer'): self.check()

    def test_new_producer_step_missing_or_skipped_refuses(self):
        step = next(x for x in self.job['steps'] if x['name'] ==
            'Exact PR producer fixture and identity refusal checks')
        step['conclusion'] = 'skipped'
        with self.assertRaisesRegex(ValueError, 'prior-ci-required-step'): self.check()
        self.job['steps'].remove(step)
        with self.assertRaisesRegex(ValueError, 'prior-ci-required-step'): self.check()


class ProducerActualGitSource(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git('init'); self.git('config', 'user.name', 'Disposable CI fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'core.autocrlf', 'false')
        self.path = self.root/WORKFLOW; self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'name: public fixture\n')
        self.git('add', '.'); self.git('commit', '-m', 'first')
        self.first = self.git('rev-parse', 'HEAD')
        (self.root/'public.txt').write_bytes(b'public fixture\n')
        self.git('add', '.'); self.git('commit', '-m', 'second')
        self.second = self.git('rev-parse', 'HEAD')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args],
            stderr=subprocess.DEVNULL).decode().strip()

    def test_distinct_actual_revision_with_identical_workflow(self):
        self.assertNotEqual(self.first, self.second)
        self.assertEqual(check_source(self.root, self.second, self.first),
            check_source(self.root, self.second, self.second))

    def test_changed_workflow_revision_refuses(self):
        self.path.write_bytes(b'name: changed public fixture\n')
        self.git('add', '.'); self.git('commit', '-m', 'changed workflow')
        third = self.git('rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'producer-actual-workflow-bytes'):
            check_source(self.root, third, self.first)

    def test_dirty_or_wrong_checkout_refuses(self):
        with self.assertRaisesRegex(ValueError, 'producer-clean-E'):
            check_source(self.root, self.first, self.first)
        (self.root/'untracked.txt').write_bytes(b'public fixture')
        with self.assertRaisesRegex(ValueError, 'producer-clean-E'):
            check_source(self.root, self.second, self.first)
