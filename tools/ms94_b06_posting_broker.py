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

    def start(self):
        runner = self.runner
        classes = (runner.root / self.spec['classes_directory']).resolve()
        check(classes.is_relative_to(runner.root.resolve()), 'observer-classes-escaped')
        for name, expected in self.spec['class_files_sha256'].items(): bound_file(classes, name, expected)
        check({p.relative_to(classes).as_posix() for p in classes.rglob('*') if p.is_file()} ==
              set(self.spec['class_files_sha256']), 'observer-extra-classpath-file')
        info = inspect('container', self.app)
        check(info['Image'] == runner.plan['local']['runner_image'], 'observer-target-image-changed')
        check(set(info['NetworkSettings']['Networks']) == {runner.network}, 'observer-target-network-changed')
        check(not info['HostConfig'].get('PortBindings'), 'observer-debug-port-published')
        check(all(not Path(m['Source']).resolve().is_relative_to(self.private.resolve())
                  for m in info['Mounts'] if m['Type'] == 'bind'), 'observer-output-visible-to-candidate')
        docker('create', '--name', self.name, '--label', runner.label, '--network', runner.network,
               '--memory', '768m', '--cpus', '1', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--mount', f'type=bind,src={classes},dst=/observer-classes,readonly', runner.plan['local']['runner_image'])
        runner.remember('container', self.name); docker('start', self.name)
        runner.assert_real_runtime(self.name)
        self.target = {'container_id': info['Id'], 'image': info['Image'], 'network': runner.network,
                       'addresses': info['NetworkSettings']['Networks'][runner.network],
                       'ports_published': False, 'observer_private_mount_absent': True}
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
                    self.target['jvm'] = owner
                    break
                check(time.monotonic() < deadline, 'observer-target-listener-timeout')
                self.stop_requested.wait(.1)
            stderr_stream = (self.private / 'collector.stderr').open('xb')
            self.process = subprocess.Popen(['docker', 'exec', '-i', self.name, 'java', '--add-modules', 'jdk.jdi',
                '-cp', '/observer-classes', 'lightyear.observer.PostingObserver', self.app, '5005'],
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
                    check(event['sequence'] == sequence and sequence <= 50000, 'observer-sequence-invalid')
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
                    if event['kind'] == 'ready': self.ready.set()
                    if event['kind'] == 'vm-death': death = True
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
            'complete': True, 'native_qualification': False,
        }, self.signer)

    def cancel(self):
        self.stop_requested.set()
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
        if self.thread is not None:
            check(self.done.wait(30), 'observer-thread-not-finalized')
