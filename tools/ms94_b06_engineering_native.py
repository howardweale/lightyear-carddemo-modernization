"""Oracle-only adapter; imports #293 observer unchanged. Never a pair adapter."""
import secrets
import time
from pathlib import Path
from lightyear_calibration.contracts import read_json, canonical, seal
from lightyear_calibration.journey_runtime import docker, inspect, LocalRunner
from lightyear_calibration.measured_native import cleanup_owned
from lightyear_execution.journey_network import InternalOnlyNetwork
from tools.ms94_b06_observed_runner import ObservedRunner
from tools.ms94_b06_engineering import LIMITS, LABEL, guard, require, sha, write_new, now


class OracleEngineeringRunner(ObservedRunner):
    def __init__(self, assets, run, plan, emit, approval):
        super().__init__(Path(assets), Path(run), plan, emit)
        self.approval = approval
        self.deadline = time.monotonic()+LIMITS['run_seconds']
        self.next_size_check = 0
        self.before_candidate = lambda lane: require(lane == 'oracle', 'oracle-only')

    def check_cancel(self):
        guard(self.approval)
        require(not (self.run/'cancel-request.json').exists(), 'cancelled')
        require(time.monotonic() < self.deadline, 'deadline')
        if time.monotonic() >= self.next_size_check:
            total = sum(p.stat().st_size for p in self.run.rglob('*') if p.is_file())
            require(total <= LIMITS['output_bytes'], 'output-cap')
            self.next_size_check = time.monotonic()+1

    def checkpoint(self, stage):
        self.check_cancel()
        from tools.ms94_b06_admission import bound_file
        for name, digest in self.plan['implementation_sha256'].items(): bound_file(self.root, name, digest)
        for name, digest in self.plan['inputs_sha256'].items(): bound_file(self.run/'inputs', name, digest)
        self.record_guard(stage)

    def record_guard(self, stage):
        from tools.ms94_calendar import guard as period_guard
        self.check_cancel(); period_guard(self.plan['calendar'])
        self.emit('stage', dict(stage=stage, real_utc=now().isoformat()))

    def worker(self, command, payload, timeout):
        require(payload.get('lane') == 'oracle', 'oracle-only')
        return super().worker(command, payload, min(timeout, max(1, self.deadline-time.monotonic())))

    def remember(self, kind, name):
        # Journal BEFORE create so interruption cannot leave an unnamed resource.
        require(name.startswith(self.owner+'-'), 'resource-owner')
        self.resources.append(dict(kind=kind, name=name))
        (self.run/'resources.json').write_bytes(canonical(dict(**LABEL, resources=self.resources)))

    def prepare(self, case='operations', attempt=1):
        require(case == 'operations' and attempt == 1, 'retained-reference-only')
        self.checkpoint('prepare-oracle')
        prefix = self.owner+'-operations-1'
        self.network = prefix+'-net'
        self.remember('network', self.network)
        docker(*InternalOnlyNetwork(self.owner).create_args(self.network))
        self.password = secrets.token_hex(24)
        self.names = dict(oracle=prefix+'-oracle')
        database = self.names['oracle']; self.remember('container', database)
        docker('create','--name',database,'--label',self.label,'--network',self.network,
               '--network-alias','oracle','--memory','6g','--cpus','2',
               '--security-opt','no-new-privileges',self.plan['declaration']['environment']['engines']['oracle']['image_digest'])
        docker('start',database)
        self.runner = prefix+'-runner'; self.remember('container', self.runner)
        docker('create','--name',self.runner,'--label',self.label,'--network',self.network,
               '--memory','8g','--cpus','4','--cap-drop','ALL','--security-opt','no-new-privileges',
               '--tmpfs','/secrets:rw,noexec,nosuid,size=268435456',
               '--mount',f'type=bind,src={self.root / "src"},dst=/verifier/src,readonly',
               '--mount',f'type=bind,src={self.run},dst=/output',self.plan['local']['runner_image'])
        docker('start', self.runner)
        InternalOnlyNetwork(self.owner).verify(inspect('network',self.network),
            [inspect('container',n) for n in (database,self.runner)])
        docker('exec',self.runner,'python','-c',
               'import socket; s=socket.socket(); s.settimeout(2); r=s.connect_ex(("1.1.1.1",443)); s.close(); assert r != 0')
        for name in (database,self.runner): self.assert_real_runtime(name)
        self.rotate_passwords()  # Iterates self.names: Oracle only.
        folder = self.run/'cases/operations/1'; folder.mkdir(parents=True,exist_ok=False)
        self.worker('prepare', dict(lane='oracle',output=self.inside(folder/'baseline/oracle'),
            expected_version=self.plan['declaration']['environment']['engines']['oracle']['expected_version']), timeout=1800)
        oracle_baseline(self.run, folder/'baseline/oracle')
        return folder


def oracle_baseline(run, base):
    from lightyear_calibration.native_reconciliation import state
    from lightyear_calibration.native_catalog import read_capture
    from lightyear_calibration.contracts import verify
    expected=read_json(run/'inputs/oracle-entry-multisets.json')
    for moment in ('before','after','entry'):
        snapshot=state(base/moment,'oracle')
        require({k:v['row_multiset'] for k,v in snapshot['tables'].items()}==expected,'oracle-entry-multisets')
    catalog=read_capture(base/'catalog.json')
    require(catalog['import_binding']==dict(ms84_checkpoint_sha256=read_json(run/'inputs/checkpoint.json')['content_sha256'],
        state_sha256=state(base/'after','oracle')['content_sha256']),'oracle-entry-lineage')
    probes=read_json(base/'probes.json'); verify(probes)
    require(probes['catalog_sha256']==catalog['content_sha256'] and probes['expected_cases']==probes['expectations_met']==30 and
            len(probes['cases'])==30 and all(c['expectation_met'] for c in probes['cases']) and probes['transaction_rolled_back'] is True,
            'oracle-entry-probes')


def absence(owner):
    # Always check all three resource kinds, even with partial setup.
    for kind in ('container','network','volume'):
        args = ['-a'] if kind == 'container' else []
        require(not docker(kind,'ls',*args,'-q','--filter','label=lightyear.journey='+owner).stdout.strip(), 'owned-resource-remains')
    return True


def no_overlap():
    # Only after approval. Refuse any active journey container, not just ours.
    require(not docker('ps','-q','--filter','label=lightyear.journey').stdout.strip(), 'active-native-overlap')


def execute(assets, run, approval, signer):
    run=Path(run); plan=read_json(run/'plan.json')
    def emit(kind, body):
        with (run/'progress.jsonl').open('ab') as stream:
            stream.write(canonical(dict(**LABEL,kind=kind,at_utc=now().isoformat(),payload=body))+b'\n')
    runner=OracleEngineeringRunner(assets,run,plan,emit,approval); runner.signer=signer
    started=time.monotonic(); outcome='incomplete'; error=None
    try:
        folder=runner.prepare()
        result=runner.worker('execute',dict(lane='oracle',output=runner.inside(folder/'execution/oracle'),
            harness_sha256=plan['harness_sha256'],test='LightyearOperationsTest',
            source_commit=plan['declaration']['application']['source_commit'],
            timeout_seconds=LIMITS['candidate_seconds']),timeout=LIMITS['candidate_seconds']+30)
        require(result['exit_code'] == 0, 'candidate-failed')
        outcome='observer-completed-uncredited'
    except Exception as exc:
        outcome='refused'; error=dict(exception_type=type(exc).__name__)
    finally:
        cleaned=cleanup_owned(runner)
        verified=bool(cleaned['complete']) and absence(run.name)
        write_new(run/'cleanup.json',signer.sign(dict(**LABEL,artifact_type='b06-engineering-cleanup/1',
            **cleaned,actual_absence_verified=verified)))
    return dict(outcome=outcome,error=error,cleanup_verified=verified,elapsed_seconds=round(time.monotonic()-started,3))
