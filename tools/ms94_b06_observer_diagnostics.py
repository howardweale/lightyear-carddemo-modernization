"""Exact prospective engineering diagnostics; no execution or approval on import."""
import hashlib
import json
from pathlib import Path
import subprocess
from tools.ms94_b06_admission import check, sign_once
from tools.ms94_b06_engineering import LIMITS, attempt_limits

POLICY = 'native-diagnostics-v1'
MODES = ('strict', 'diagnostic-unmatched-return')


def configuration(mode):
    check(mode in MODES, 'observer-diagnostic-mode')
    return dict(policy=POLICY, mode=mode, unmatched_return_cap=LIMITS['unmatched_return_cap'],
                heap_guard_percent=LIMITS['heap_guard_percent'],
                telemetry_events=LIMITS['telemetry_events'], pending_cap=LIMITS['pending_cap'])


def validate(plan):
    spec = plan.get('posting_observer', {}).get('native_diagnostics')
    if spec is None:
        return None
    check(plan.get('run_class') == 'engineering' and plan.get('qualification_credit') is False and
          plan.get('measurement_credit') is False, 'observer-diagnostics-engineering-only')
    check(plan.get('engineering_limits') in (LIMITS,attempt_limits(2)) and
          (plan.get('engineering_limits')==LIMITS or spec.get('mode')=='diagnostic-unmatched-return'), 'observer-engineering-limits')
    check(spec == configuration(spec.get('mode')), 'observer-native-diagnostics-config')
    return spec


def container_args(plan, private):
    spec = validate(plan)
    if spec is None:
        return ['--memory', '768m', '--cpus', '1']
    private = Path(private).resolve()
    check(not any(p.is_symlink() for p in (private, *private.parents)), 'observer-private-link')
    return ['--memory', str(LIMITS['observer_memory_mib'])+'m', '--cpus', str(LIMITS['observer_cpus']),
            '--mount', f'type=bind,src={private},dst=/observer-private']


def java_options(plan):
    if validate(plan) is None:
        return []
    extra=[]
    if plan['engineering_limits']!=LIMITS:
        extra=['-Db06.observer.audit_records='+str(plan['engineering_limits']['audit_records']),
               '-Db06.observer.audit_bytes='+str(plan['engineering_limits']['audit_bytes'])]
    return extra+['-Xmx'+str(LIMITS['observer_heap_mib'])+'m',
            '--add-opens=jdk.jdi/com.sun.tools.jdi=ALL-UNNAMED',
            '-XX:SoftRefLRUPolicyMSPerMB='+str(LIMITS['soft_ref_lru_ms_per_mb']),
            '-Db06.observer.state_dir=/observer-private', '-XX:+HeapDumpOnOutOfMemoryError',
            '-XX:HeapDumpPath=/observer-private/heap.hprof']


def observer_args(plan):
    spec = validate(plan)
    if spec is None:
        return []
    return ['bounded-observer-v1', POLICY, spec['mode'], 'unmatched-return-cap='+str(spec['unmatched_return_cap']),
            'heap-guard-percent='+str(spec['heap_guard_percent']),
            'heap-telemetry-interval='+str(spec['telemetry_events']), 'pending-cap='+str(spec['pending_cap'])]


def file_digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


class DiskRecords:
    """Re-iterable broker spool; retain only the immediately preceding event."""
    def __init__(self, path):
        self.path=Path(path);self.count=0;self.last=None
    def append(self, item):
        self.count+=1;self.last=item
    def __len__(self): return self.count
    def __getitem__(self, index):
        if index != -1 or self.last is None: raise IndexError(index)
        return self.last
    def __iter__(self):
        if self.count == 0: return
        with self.path.open('rb') as stream:
            for index, line in enumerate(stream):
                if index >= self.count: break
                yield json.loads(line)


def guard_stop(broker, event, event_sha256):
    """Collect a private histogram while the JVM waits at its guard checkpoint."""
    pid=event.get('observer_pid')
    check(type(pid) is int and pid > 0, 'observer-guard-pid')
    check(event.get('kind') == 'observer-resource-limit' and event.get('checkpoint') is True,
          'observer-resource-stop-shape')
    path=broker.private/'guard-histogram.txt'
    error=None; code=None
    try:
        with path.open('xb') as output, (broker.private/'guard-histogram.stderr').open('xb') as errors:
            result=subprocess.run(['docker','exec',broker.name,'jcmd',str(pid),'GC.class_histogram'],
                                  stdout=output,stderr=errors,timeout=15,check=False)
        code=result.returncode
    except Exception as exc:
        error=type(exc).__name__
    return sign_once(broker.private/'guard-stop.json', dict(
        artifact_type='b06-engineering-observer-resource-stop/1',
        plan_sha256=broker.runner.plan['content_sha256'], lane=broker.lane,
        reason=event.get('reason'), event_sha256=event_sha256,
        generation_entry_count=broker.generation_entries,
        histogram_sha256=file_digest(path) if path.is_file() else None,
        histogram_bytes=path.stat().st_size if path.is_file() else 0,
        histogram_complete=code==0, histogram_exit_code=code, histogram_error_type=error,
        heap_dump_private_path='heap.hprof', qualification_credit=False,measurement_credit=False),broker.signer)
