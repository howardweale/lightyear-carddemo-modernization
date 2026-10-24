"""Disposable CI authority and real committed F2 admission. Never operator input."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid

from lightyear_control_tower.console import ConsoleService, provision
from lightyear_control_tower.decisions import canonical, verify_envelope
from lightyear_control_tower.factory_policy import FactoryDecisions, write_request
from lightyear_execution.admission import sign_work_order, verify_work_order
from lightyear_execution.contracts import ExecutionPolicy
from lightyear_factory.contracts import WorkOrder, canonical_hash
from lightyear_factory.model_admission import FactoryModelAdmission


class Fixture:
    """Real signatures, Git evidence and admission; no verifier patching."""

    def __init__(self, parent, repository, *, controller_probe=False):
        if os.environ.get('GITHUB_ACTIONS') != 'true':
            raise ValueError('p5-ci-only')
        self.parent = Path(parent)
        self.root = self.parent / 'executable'
        self.root.mkdir()
        self.tower = self.parent / 'disposable-tower'
        self.tower.mkdir()
        authority = self.parent / 'disposable-authority' / 'authority.json'
        credential = provision(authority, 'factory', 'p5-ci', 'Disposable CI operator').read_text().strip()
        self.service = ConsoleService(self.tower, authority)
        self.service.grant_roles('p5-ci', ['operator', 'campaign-authorizer'],
                                 reason='Synthetic CI only', workloads=['factory:factory'])
        self.token = self.service.login(credential)['token']
        self.policy = ExecutionPolicy.load(repository / 'factory/execution/policy.json')
        order = json.loads((repository / 'factory/work-orders/intcalc-repair.example.json').read_bytes())
        order.update(id='p5:synthetic', title='P5 synthetic failure drills', goal='Measure refusal boundaries')
        order['scope'] = dict(allowed_paths=['worker.py'], graph_node_ids=['workload:p5-synthetic'])
        order['acceptance'] = dict(baseline_first=True, max_attempts=1,
            gates=[dict(id='synthetic', command=['python3', 'worker.py'], timeout_seconds=10,
                        expose_output_to_builder=False)])
        order['policy'].update(max_model_calls=2, max_elapsed_seconds=60, max_model_cost_usd=1.0)
        self.private_values_path = None
        if controller_probe:
            order['acceptance']['baseline_first'] = False
            order['scope']['graph_node_ids'] = []
            self.private_values_path = self.parent / 'synthetic-expected-values.json'
            raw = canonical(dict(schema='factory-private-expected-values/1',
                values=['synthetic-private-account-18732491-balance-694127.83-unpublished-fixture']))
            with self.private_values_path.open('xb') as stream:
                stream.write(raw)
        self.order = WorkOrder.from_dict(order)
        self.git('init', '--quiet')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'core.hooksPath', str(self.parent / 'no-hooks'))
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'user.name', 'Disposable P5 CI')
        self.git('config', 'user.email', 'p5-ci@example.invalid')
        (self.root / 'worker.py').write_bytes(b'print("synthetic")\n')
        self.input_paths = {name: 'docs/factory/p5/' + name + '.json'
                            for name in ('scope', 'freeze', 'workspace', 'execution_policy')}
        inputs = dict(scope={'synthetic': True}, freeze={'synthetic': True},
                      workspace={'worker.py': hashlib.sha256((self.root / 'worker.py').read_bytes()).hexdigest()},
                      execution_policy=self.policy.to_dict())
        for name, value in inputs.items():
            self.write(self.input_paths[name], value)
        self.git('add', '.')
        self.git('commit', '--quiet', '--no-gpg-sign', '-m', 'Synthetic executable and bound inputs')
        executable = self.git('rev-parse', 'HEAD').decode().strip()
        bound = {name: dict(path=path, sha256=hashlib.sha256((self.root / path).read_bytes()).hexdigest())
                 for name, path in self.input_paths.items()}
        caps = dict(max_attempts=1, max_repair_loops=1, max_elapsed_seconds=60,
                    max_model_calls=2, max_model_tokens=self.order.max_model_tokens, cost_cap_microusd=1000000)
        self.now = datetime.now(timezone.utc)
        self.end = self.now + timedelta(minutes=30)
        self.window = dict(start=(self.now - timedelta(minutes=5)).isoformat(), end=self.end.isoformat())
        plan = dict(schema='factory-build-plan/1', work_order_sha256=self.order.content_sha256,
                    executable_commit=executable, caps=caps, bound_inputs=bound,
                    roles={role: dict(provider='p5-stub', model='p5-stub-2026-10-23')
                           for role in ('planner', 'builder', 'analyst')})
        if controller_probe:
            raw = self.private_values_path.read_bytes()
            plan['private_expected_values'] = dict(sha256=hashlib.sha256(raw).hexdigest(),
                size_bytes=len(raw), count=1)
        plan['content_sha256'] = canonical_hash(plan)
        self.contract = dict(schema='factory-contract/1', kind='engineering-run-approval', program='factory',
            sources=[dict(row, commit=executable) for row in bound.values()],
            details=dict(executable_commit=executable, request_seal=plan['content_sha256'],
                         observer_sha256=hashlib.sha256(b'p5-disposable-observer').hexdigest(),
                         class_hashes={'synthetic': hashlib.sha256(b'p5-synthetic').hexdigest()},
                         window=self.window, caps=caps))
        for path in self.input_paths.values():
            target = self.tower / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((self.root / path).read_bytes())
        journal = self.service.export_session(self.token)
        request = write_request(self.tower, self.contract, journal=journal, public_key=self.service.public_key,
                                trusted_head=journal['journal_head_sha256'])
        item = self.service.review(self.token, request['id'])
        event = self.service.decide(self.token, dict(item_id=item['id'], bound=item['bound'], outcome='approve',
            reason='Disposable CI fixture; no real execution authority', previous_decision_sha256=None,
            request_id=str(uuid.uuid4())))
        self.proof = self.service.proof(self.token, event['content_sha256'])
        self.head = self.proof['journal']['journal_head_sha256']
        FactoryDecisions(self.service.public_key, self.head, evidence_root=self.root).verify(
            self.proof, 'engineering-run-approval', self.contract, {'approve'})
        self.paths = ('docs/factory/p5/plan.json', 'docs/factory/p5/proof.json', 'docs/factory/p5/contract.json')
        for path, value in zip(self.paths, (plan, self.proof, self.contract)):
            self.write(path, value)
        self.git('add', '.')
        self.git('commit', '--quiet', '--no-gpg-sign', '-m', 'Synthetic signed approval metadata only')
        self.admission = FactoryModelAdmission(self.root, *self.paths, public_key=self.service.public_key,
                                               trusted_head=lambda: self.head)
        self.runtime()
        self.key_id = self.policy.trusted_key_ids[0]
        self.key = secrets.token_bytes(32)
        self.envelope = sign_work_order(self.order, self.policy, 'p5-ci', self.key_id, self.key,
            self.now.isoformat(), (self.now + timedelta(minutes=10)).isoformat(), 'p5-synthetic-attempt')
        self.verify_order()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE)

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(canonical(value))

    def runtime(self, **kwargs):
        return self.admission.verify_runtime(self.order, source_root=self.root,
            input_paths=self.input_paths, policy=self.policy, **kwargs)

    def verify_order(self, store=None, envelope=None, now=None):
        return verify_work_order(envelope or self.envelope, self.policy, {self.key_id: self.key},
                                 (now or self.now).isoformat(), nonce_store=store)

    def signed_observation(self, body):
        receipt = self.service.sign(body)
        if not verify_envelope(receipt, self.service.public_key):
            raise ValueError('p5-receipt-signature')
        tampered = copy.deepcopy(receipt)
        tampered['schema'] = 'tampered'
        if verify_envelope(tampered, self.service.public_key):
            raise ValueError('p5-receipt-negative-control')
        return receipt

    def close(self):
        self.service.close()
