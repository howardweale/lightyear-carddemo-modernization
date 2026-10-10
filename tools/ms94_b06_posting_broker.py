"""Host-owned external JVM event collection plus independent SQL readback.

No model transport. This is prospective equipment, not qualified evidence.
Candidate containers have no mounts into the broker's private output directory.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

from lightyear_calibration.contracts import canonical, read_json, seal, verify
from lightyear_calibration.journey_runtime import docker, inspect
from tools.ms94_b06_admission import check, bound_file, sign_once
from tools.ms94_b06_bytecode_policy import validate_jvm


class PostingBroker:
    def __init__(self, runner, lane, app_name, signer):
        self.runner, self.lane, self.app, self.signer = runner, lane, app_name, signer
        self.spec = runner.plan['posting_observer']
        self.name = runner.owner + '-posting-observer-' + lane
        self.private = runner.run / 'posting-observer' / lane
        self.private.mkdir(parents=True, exist_ok=False)
        self.process, self.thread, self.failure = None, None, None
        self.done, self.ready, self.stop_requested = threading.Event(), threading.Event(), threading.Event()
        self.records, self.previous = [], None
        self.runtime_files, self.v2_records = {}, []

    def start(self):
        runner = self.runner
        classes = (runner.root / self.spec['classes_directory']).resolve()
        check(classes.is_relative_to(runner.root.resolve()), 'observer-classes-escaped')
        for name, expected in self.spec['class_files_sha256'].items(): bound_file(classes, name, expected)
        check({p.relative_to(classes).as_posix() for p in classes.rglob('*') if p.is_file()} ==
              set(self.spec['class_files_sha256']), 'observer-extra-classpath-file')
        info = inspect('container', self.app)
        check(info['Image'] == runner.plan.get('built_runtime', {}).get('image',runner.plan['local']['runner_image']), 'observer-target-image-changed')
        check(set(info['NetworkSettings']['Networks']) == {runner.network}, 'observer-target-network-changed')
        check(not info['HostConfig'].get('PortBindings'), 'observer-debug-port-published')
        check(all(not Path(m['Source']).resolve().is_relative_to(self.private.resolve())
                  for m in info['Mounts'] if m['Type'] == 'bind'), 'observer-output-visible-to-candidate')
        self.runtime_files = {}
        if self.spec.get('observer_binding_v2') is not None:
            from tools.ms94_b06_observer_v2 import load_manifest
            manifest, _ = load_manifest(runner.root, self.spec, info['Image'])
            check(info['HostConfig'].get('ReadonlyRootfs') is True, 'observer-v2-writable-root')
            for target in manifest['runtime_files']:
                from pathlib import PurePosixPath
                for mount in info['Mounts']:
                    path=PurePosixPath(mount['Destination'])
                    if PurePosixPath(target)==path or PurePosixPath(target).is_relative_to(path):
                        check(mount.get('RW') is False, 'observer-v2-writable-runtime-overlay')
            source = bound_file(runner.root, 'tools/ms94_b06_runtime_files_probe.py',
                runner.plan['implementation_sha256']['tools/ms94_b06_runtime_files_probe.py'])
            probe = docker('exec', '-i', self.app, 'python', '-c', source.read_text(encoding='utf-8'),
                           input=canonical(manifest['runtime_files']), timeout=120)
            self.v2_java_path = manifest['jdk']['java']
            self.runtime_files = json.loads(probe.stdout)
            check(self.runtime_files == manifest['runtime_files'], 'observer-v2-runtime-measurement')
        self.host_jar_entries = {}
        if self.spec.get('forwarding_stub') is not None:
            host_spec = self.spec['host_jar_entries']
            for item in host_spec.values():
                jar = Path(item['jar'])
                check(not any(jar == Path(m['Destination']) or jar.is_relative_to(Path(m['Destination']))
                              for m in info['Mounts']), 'observer-framework-jar-shadowed')
            source = bound_file(runner.root, 'tools/ms94_b06_host_jar_probe.py',
                                runner.plan['implementation_sha256']['tools/ms94_b06_host_jar_probe.py'])
            probe = docker('exec', '-i', self.app, 'python', '-c', source.read_text(encoding='utf-8'),
                           input=canonical(host_spec), timeout=60)
            self.host_jar_entries = json.loads(probe.stdout)
        docker('create', '--name', self.name, '--label', runner.label, '--network', runner.network,
               '--memory', '768m', '--cpus', '1', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--mount', f'type=bind,src={classes},dst=/observer-classes,readonly', runner.plan['local']['runner_image'])
        runner.remember('container', self.name); docker('start', self.name)
        runner.assert_real_runtime(self.name)
        self.target = {'container_id': info['Id'], 'image': info['Image'], 'network': runner.network,
                       'addresses': info['NetworkSettings']['Networks'][runner.network],
                       'ports_published': False, 'observer_private_mount_absent': True}
        if 'built_runtime' in runner.plan:
            from tools.ms94_b06_built_runtime import contract, mount_contract
            manifest,launch,_=contract(runner.root,runner.plan)
            mounts=sorted((m['Destination'],m['RW']) for m in info['Mounts'] if m['Type']=='bind')
            check(info['HostConfig']['ReadonlyRootfs'] is True and mounts==mount_contract(manifest,launch['overlays']),
                  'observer-built-runtime-mounts')
            self.target.update(readonly_rootfs=True,built_launch_sha256=launch['content_sha256'],
                application_mounts=[list(m) for m in mounts])
        self.thread = threading.Thread(target=self._collect, name='b06-posting-' + self.lane, daemon=True)
        self.thread.start()

    def _collect(self):
        try:
            # The target JVM opens JDWP before running any candidate code. The
            # broker must attach to that listener; it never accepts a candidate
            # reverse connection or a candidate-created event file.
            deadline = time.monotonic() + 120
            while True:
                self.runner.check_cancel()
                check(not self.stop_requested.is_set(), 'observer-start-cancelled')
                probe_source = bound_file(self.runner.root, 'tools/ms94_b06_posting_listener.py',
                    self.runner.plan['implementation_sha256']['tools/ms94_b06_posting_listener.py'])
                probe = docker('exec', self.app, 'python', '-c', probe_source.read_text(encoding='utf-8'), timeout=10)
                owners = json.loads(probe.stdout)
                if owners:
                    check(len(owners) == 1, 'observer-ambiguous-listener')
                    owner = owners[0]
                    validate_jvm(owner, self.spec)
                    if self.spec.get('observer_binding_v2') is not None:
                        check(owner['executable'] == self.v2_java_path, 'observer-v2-java-path-differs')
                    self.target['jvm'] = owner
                    break
                check(time.monotonic() < deadline, 'observer-target-listener-timeout')
                self.stop_requested.wait(.1)
            stderr_stream = (self.private / 'collector.stderr').open('xb')
            self.process = subprocess.Popen(['docker', 'exec', '-i', self.name, 'java', '--add-modules', 'jdk.jdi',
                '-cp', '/observer-classes', 'lightyear.observer.PostingObserver', self.app, '5005',
                *(['observer-binding-v2'] if self.spec.get('observer_binding_v2') is not None else [])],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr_stream)
            stderr_stream.close()
            events = queue.Queue(maxsize=16)
            def enqueue(line):
                while not self.stop_requested.is_set():
                    try:
                        events.put(line, timeout=.5)
                        return
                    except queue.Full:
                        continue
            def consume():
                try:
                    for line in iter(lambda: self.process.stdout.readline(4 * 1024 * 1024 + 1), b''):
                        enqueue(line)
                        if len(line) > 4 * 1024 * 1024: break
                finally: enqueue(None)
            threading.Thread(target=consume, daemon=True).start()
            sequence, death = 0, False
            from tools.ms94_b06_observer_audit import Audit
            audit = Audit()
            evidence_count = 0
            audit_required = False
            with (self.private / 'events.jsonl').open('xb') as log:
                while True:
                    self.runner.check_cancel()
                    check(not self.stop_requested.is_set(), 'observer-collection-cancelled')
                    try: line = events.get(timeout=.5)
                    except queue.Empty: continue
                    if line is None: break
                    check(len(line) <= 4 * 1024 * 1024, 'observer-event-too-large')
                    event = json.loads(line)
                    sequence += 1
                    check(event['sequence'] == sequence, 'observer-sequence-invalid')
                    if event['kind'] == 'observer-audit':
                        check(audit_required, 'observer-audit-unannounced')
                        audit.event(event)
                    else:
                        evidence_count += 1
                        check(evidence_count <= 50000, 'observer-sequence-invalid')
                    readback = None
                    if event.get('document'):
                        check(event['checkpoint'] is True, 'observer-readback-without-suspension')
                        result = docker('exec', '-i', self.runner.runner, 'python', '-m',
                            'lightyear_calibration.b06_posting_probe', input=canonical({
                                'lane': self.lane, 'password': self.runner.password,
                                'document': event['document'], 'event_sequence': sequence}), timeout=20)
                        readback = json.loads(result.stdout); verify(readback)
                        path = self.private / ('readback-%06d.json' % sequence)
                        with path.open('xb') as stream: stream.write(canonical(readback))
                    item = seal({'event': event, 'previous_sha256': self.previous,
                                 'readback_sha256': readback['content_sha256'] if readback else None,
                                 'real_utc': datetime.now(timezone.utc).isoformat()})
                    log.write(canonical(item) + b'\n'); log.flush()
                    self.previous = item['content_sha256']; self.records.append(item)
                    from tools.ms94_b06_fault_hook import inject
                    inject(self.runner, self.lane, item, self.signer)
                    if event['kind'] == 'ready':
                        from tools.ms94_b06_observer_audit import POLICY
                        check(event.get('audit_policy') in (None, POLICY), 'observer-audit-policy')
                        audit_required = event.get('audit_policy') == POLICY
                        self.ready.set()
                    if event['kind'] == 'vm-death':
                        if audit_required: audit.complete()
                        death = True
                    if event['checkpoint']:
                        self.process.stdin.write((str(sequence) + '\n').encode()); self.process.stdin.flush()
            code = self.process.wait(timeout=10)
            check(code == 0 and death and self.ready.is_set(), 'observer-incomplete-lifecycle')
        except Exception as exc:
            self.failure = type(exc).__name__ + ': ' + str(exc)
            # Preserve a stopped checkpoint without inventing its SQL readback
            # or a complete collector receipt. No exception prose is exported.
            try:
                sign_once(self.private / 'failure.json', {
                    'artifact_type': 'ms94-b06-posting-collector-failure/1',
                    'plan_sha256': self.runner.plan['content_sha256'], 'lane': self.lane,
                    'real_utc': datetime.now(timezone.utc).isoformat(),
                    'exception_type': type(exc).__name__, 'event_count': len(self.records),
                    'last_event_sha256': self.previous, 'complete': False,
                    'native_qualification': False,
                }, self.signer)
            except Exception as signing_error:
                self.failure += '; failure-record:' + type(signing_error).__name__
        finally:
            # Commit to all retained definitions/adjacent host observations even if
            # execution or collection fails. This record grants no frame trust.
            try:
                from tools.ms94_b06_forwarding_stub import receipt_records
                self.frame_census = receipt_records(self.records)
                from tools.ms94_b06_observer_v2 import commitments
                self.v2_records = commitments(self.records) if self.spec.get('observer_binding_v2') is not None else []
                sign_once(self.private / 'frame-census.json', {
                    'artifact_type':'ms94-b06-generated-frame-census/1',
                    'plan_sha256':self.runner.plan['content_sha256'], 'lane':self.lane,
                    'complete':self.failure is None, 'event_count':len(self.records),
                    'last_event_sha256':self.previous, 'frame_records':self.frame_census,
                    'host_jar_entries':self.host_jar_entries,
                    'v2_records':self.v2_records, 'runtime_files':self.runtime_files,
                    'event_file_sha256':hashlib.sha256((self.private/'events.jsonl').read_bytes()).hexdigest(),
                    'native_qualification':False, 'model_calls':0,
                }, self.signer)
            except Exception as census_error:
                self.failure = (self.failure or '') + '; census-record:' + type(census_error).__name__
            self.stop_requested.set()
            if self.process is not None and self.process.poll() is None:
                self.process.kill(); self.process.wait()
            self.done.set()

    def finish(self, execution):
        check(self.done.wait(15), 'observer-finalization-timeout')
        check(self.failure is None, 'observer-failed')
        return sign_once(self.private / 'receipt.json', {
            'artifact_type': 'ms94-b06-posting-collector-receipt/1', 'plan_sha256': self.runner.plan['content_sha256'],
            'lane': self.lane, 'execution_sha256': execution['content_sha256'], 'target': self.target,
            'observer_class_files_sha256': self.spec['class_files_sha256'],
            'event_count': len(self.records), 'last_event_sha256': self.previous,
            'event_file_sha256': hashlib.sha256((self.private / 'events.jsonl').read_bytes()).hexdigest(),
            'frame_records': self.frame_census,
            'host_jar_entries': self.host_jar_entries,
            'v2_records': self.v2_records, 'runtime_files': self.runtime_files,
            'complete': True, 'native_qualification': False,
        }, self.signer)

    def cancel(self):
        self.stop_requested.set()
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
        if self.thread is not None:
            check(self.done.wait(30), 'observer-thread-not-finalized')
