"""B06-only observed execution; inherited J1 predicates/equipment remain untouched."""
import json
from pathlib import Path
import subprocess
import time

from lightyear_calibration.contracts import canonical, require, seal
from lightyear_calibration.journey_order import file_hash, save
from lightyear_calibration.journey_runtime import docker, inspect, JourneyAbort
from tools.ms94_b06_native import NativeRunner
from tools.ms94_b06_candidate_result import CandidateTimeout
from tools.ms94_b06_posting_broker import PostingBroker


class ObservedRunner(NativeRunner):
    def worker(self, command, payload, timeout):
        if command != 'execute':
            return super().worker(command, payload, timeout)
        lane = payload['lane']
        require(lane in ('oracle', 'postgresql') and payload['test'] == 'LightyearOperationsTest', 'Unknown observed target')
        relative = Path(payload['output'].removeprefix('/output/'))
        out = (self.run / relative).resolve()
        require(out.is_relative_to(self.run.resolve()), 'Output escaped run')
        source = self.run / 'inputs/operations.java'
        require(file_hash(source) == payload['harness_sha256'], 'Candidate changed')
        staging = self.run / 'application-output' / lane
        staging.mkdir(parents=True, exist_ok=False)
        app = self.owner + '-application-' + lane
        worker = self.root / 'tools/ms94_b06_observed_worker.py'
        built = self.plan.get('built_runtime') is not None
        launch = None
        if built:
            from tools.ms94_b06_built_runtime import prepare
            mount_args, expected_mounts, launch = prepare(self.root, self.run, self.plan, staging)
        else:
            # Historical plans retain their historical worker; fresh built plans never fall back.
            mount_args = ['--mount', f'type=bind,src={source},dst=/candidate/LightyearOperationsTest.java,readonly',
                '--mount', f'type=bind,src={worker},dst=/runtime/worker.py,readonly',
                '--mount', f'type=bind,src={staging},dst=/results']
            expected_mounts = [dict(destination='/candidate/LightyearOperationsTest.java',writable=False),
                dict(destination='/runtime/worker.py',writable=False),dict(destination='/results',writable=True)]
        image = launch['image'] if built else self.plan['local']['runner_image']
        carrier = ['--entrypoint','/bin/sh'] if built else []
        tail = ['-c','exec sleep infinity'] if built else []
        docker('create', '--name', app, '--label', self.label, '--network', self.network, '--memory', '8g', '--cpus', '4',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--tmpfs', '/secrets:rw,noexec,nosuid,size=268435456',
               *mount_args, *carrier, image, *tail)
        self.remember('container', app); docker('start', app)
        app_info = inspect('container', app); mounts = app_info['Mounts']
        require(sorted((m['Destination'],m['RW']) for m in mounts if m['Type']=='bind') ==
                sorted((m['destination'],m['writable']) for m in expected_mounts), 'Unexpected application mount')
        if built:
            require(app_info['Image']==launch['image'] and app_info['HostConfig']['ReadonlyRootfs'] is True,
                    'Built application image or readonly root changed')
        self.record_guard('before-candidate:' + lane)
        self.assert_real_runtime(app); self.before_candidate(lane)
        before = self.trusted_identity(lane); started = time.monotonic()
        broker = PostingBroker(self, lane, app, self.signer)
        process = None
        try:
            broker.start()
            process = subprocess.Popen(['docker', 'exec', '-i', app, 'python', '/runtime/worker.py'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            data = canonical({'lane': lane, 'password': self.password, 'timeout_seconds': payload['timeout_seconds'],
                              'scenario_date': self.plan['calendar']['scenario_date']})
            while True:
                try:
                    stdout, stderr = process.communicate(input=data, timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    data = None; self.check_cancel()
                    require(broker.failure is None, 'Trusted posting observer failed')
                    if time.monotonic() - started > timeout:
                        raise CandidateTimeout()
            require(process.returncode == 0, 'Separate application worker failed')
            response = json.loads(stdout); code = response['exit_code']
            if built:
                require(response.get('launch_sha256')==launch['content_sha256'] and response.get('offline_maven') is False,
                        'Built worker response binding')
            if code != 124:
                require(broker.done.wait(15) and broker.failure is None, 'Trusted posting observer incomplete')
        finally:
            if process is not None and process.poll() is None:
                process.kill(); process.communicate()
            docker('stop', '--time', '2', app, check_code=False)
            broker.cancel()
        after = self.trusted_identity(lane)
        out.mkdir(parents=True, exist_ok=False)
        for name in (('journey.xml','runtime.log','built-before.json','built-after.json') if built else ('journey.xml','maven.log')):
            path = staging / name
            require(not path.is_symlink(), 'Symbolic application output')
            if path.exists():
                (out / name).write_bytes(path.read_bytes().replace(self.password.encode(), b'[redacted]'))
        (out / 'harness.java').write_bytes(source.read_bytes())
        facts = {'native_database_instance': before['name'], 'expected_database_address':
            'jdbc:oracle:thin:@//oracle:1521/freepdb1' if lane == 'oracle' else
            'jdbc:postgresql://postgresql:5432/idempiere?encoding=unicode&applicationname=idempiere&stringtype=unspecified&tcpkeepalive=true'}
        value = seal({'lane': lane, 'runtime_facts': facts, 'exit_code': code,
            'elapsed_seconds': round(time.monotonic() - started, 1), 'native_clock_before': before['clock'],
            'native_clock_after': after['clock'], 'harness_sha256': payload['harness_sha256'],
            'application_source_commit': payload['source_commit'], 'journey_output_exists': (out / 'journey.xml').exists(),
            'offline_maven': not built, 'private_judge_mount': False, 'trusted_execution_envelope_written_by': 'host-controller',
            'application_mounts': [{'destination': m['Destination'], 'writable': m['RW']} for m in mounts if m['Type'] == 'bind'],
            'posting_observer': 'external-jdi-with-suspended-native-readback-v1'})
        if built:
            body={k:v for k,v in value.items() if k!='content_sha256'}
            body.update(launch_sha256=launch['content_sha256'],runtime_image=launch['image'],application_readonly=True,
                built_runtime_checks_sha256={n:file_hash(out/n) for n in ('built-before.json','built-after.json')})
            value=seal(body)
            from tools.ms94_b06_built_runtime import replay
            replay(self.root,self.plan,value,out)
        save(out / 'execution.json', value)
        if code != 124:
            broker.finish(value)
        return value
