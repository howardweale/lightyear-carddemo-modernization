"""B06-only observed execution; inherited J1 predicates/equipment remain untouched."""
import json
from pathlib import Path
import subprocess
import time

from lightyear_calibration.contracts import canonical, require, seal
from lightyear_calibration.journey_order import file_hash, save
from lightyear_calibration.journey_runtime import docker, inspect, JourneyAbort
from tools.ms94_b06_native import NativeRunner
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
        docker('create', '--name', app, '--label', self.label, '--network', self.network, '--memory', '8g', '--cpus', '4',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--tmpfs', '/secrets:rw,noexec,nosuid,size=268435456',
               '--mount', f'type=bind,src={source},dst=/candidate/LightyearOperationsTest.java,readonly',
               '--mount', f'type=bind,src={worker},dst=/runtime/worker.py,readonly',
               '--mount', f'type=bind,src={staging},dst=/results', self.plan['local']['runner_image'])
        self.remember('container', app); docker('start', app)
        mounts = inspect('container', app)['Mounts']
        require({m['Destination'] for m in mounts if m['Type'] == 'bind'} ==
                {'/candidate/LightyearOperationsTest.java', '/runtime/worker.py', '/results'}, 'Unexpected application mount')
        require(all(not m['RW'] for m in mounts if m['Destination'] in
                    ('/candidate/LightyearOperationsTest.java', '/runtime/worker.py')), 'Writable application input')
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
                        raise JourneyAbort('application-timeout')
            require(process.returncode == 0, 'Separate application worker failed')
            code = json.loads(stdout)['exit_code']
            require(broker.done.wait(15) and broker.failure is None, 'Trusted posting observer incomplete')
        finally:
            if process is not None and process.poll() is None:
                process.kill(); process.communicate()
            docker('stop', '--time', '2', app, check_code=False)
            broker.cancel()
        after = self.trusted_identity(lane)
        out.mkdir(parents=True, exist_ok=False)
        for name in ('journey.xml', 'maven.log'):
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
            'offline_maven': True, 'private_judge_mount': False, 'trusted_execution_envelope_written_by': 'host-controller',
            'application_mounts': [{'destination': m['Destination'], 'writable': m['RW']} for m in mounts if m['Type'] == 'bind'],
            'posting_observer': 'external-jdi-with-suspended-native-readback-v1'})
        save(out / 'execution.json', value)
        broker.finish(value)
        return value
