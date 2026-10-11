"""Standing-approval engineering ledger. No implicit approval, Docker or retries.

Raw #293 artifacts keep their original bytes; labelled signed descriptors bind
each of them. The enclosing run, plan, receipts and all descriptors are tainted.
"""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re
import uuid

from lightyear_calibration.contracts import canonical, read_json, seal, verify
from tools.ms94_b06_engineering_boundary import LABEL

IMAGE = 'sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268'
OBSERVER_SOURCE = 'b0d5749c0a876b7977d8c64bdeca65706b6c129f'
LIMITS = dict(run_seconds=3600, cleanup_seconds=600, candidate_seconds=1800,
              database_memory_mib=6144, carrier_memory_mib=8192,
              application_memory_mib=8192, observer_memory_mib=2048, observer_heap_mib=1536,
              unmatched_return_cap=10, heap_guard_percent=85, telemetry_events=1000, pending_cap=512,
              class_index_slots=262144, class_cache_entries=256, soft_ref_lru_ms_per_mb=0,
              database_cpus=2, carrier_cpus=4, application_cpus=4, observer_cpus=1,
              output_bytes=8*1024**3, minimum_free_bytes=60*1024**3,
              audit_records=500000, audit_bytes=128*1024**2, evidence_records=50000)


# Old approvals remain held. The isolated October 13 branch opens only inside
# a context bound to the exact new request, actual implementation and Howard go.
# A JSON approval flag or an old approval digest cannot open that context.
def require_execution_ready(approval=None):
    from tools.ms94_b06_oct13_authorization import require_active
    require_active(approval)


def attempt_limits(number):
    require(type(number) is int and number in (1,2),'attempt-number')
    return dict(LIMITS,**(dict(evidence_records=150000,audit_records=1500000,audit_bytes=384*1024**2) if number==2 else {}))


def require(ok, reason):
    if not ok: raise ValueError('engineering-' + reason)


def utc(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(stamp.tzinfo is not None, 'timezone-required')
    return stamp.astimezone(timezone.utc)


def now(): return datetime.now(timezone.utc)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def write_new(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(canonical(value)+b'\n')


def proposal(start, end, excluded_windows, evidence_runs, output_root, run_cap=2):
    from tools.ms94_b06_engineering_key import ENGINEERING_KEY_SHA256
    value = seal(dict(artifact_type='b06-engineering-standing-proposal/1', **LABEL,
        image=IMAGE, observer_source=OBSERVER_SOURCE, scope='J1-retained-reference-oracle-only',
        run_cap=run_cap, attempt_modes=["strict", "diagnostic-unmatched-return"],
        engineering_key_sha256=ENGINEERING_KEY_SHA256,
        not_before_utc=start, deadline_utc=end, limits=LIMITS,
        excluded_windows=excluded_windows, evidence_runs=evidence_runs, output_root=str(Path(output_root).resolve()),
        model_calls=0, approved=False, no_degradation=True, no_automatic_retries=True))
    validate(value)
    return value


def validate(value):
    verify(value)
    require(value.get('run_class')=='engineering' and value.get('qualification_credit') is False and value.get('measurement_credit') is False, 'labels')
    require(value.get('image') == IMAGE and value.get('observer_source') == value.get('implementation_commit', OBSERVER_SOURCE), 'fixed-runtime')
    require(value.get('scope') == 'J1-retained-reference-oracle-only', 'scope')
    require(type(value.get('run_cap')) is int and value['run_cap'] == 2, 'run-cap')
    require(value.get('limits') == LIMITS and value.get('model_calls') == 0 and
            value.get('no_degradation') is True and value.get('no_automatic_retries') is True, 'limits')
    from tools.ms94_b06_engineering_key import ENGINEERING_KEY_SHA256
    require(value.get('engineering_key_sha256') == ENGINEERING_KEY_SHA256, 'key-fingerprint')
    require(value.get('attempt_modes') == ['strict', 'diagnostic-unmatched-return'], 'attempt-sequence')
    root=Path(value['output_root'])
    require(root.is_absolute() and root.name=='b06-engineering', 'output-root')
    begin, end = utc(value['not_before_utc']), utc(value['deadline_utc'])
    require(begin < end and (end-begin).total_seconds() <= 24*3600, 'calendar')
    require(isinstance(value['evidence_runs'], list) and value['evidence_runs'], 'evidence-registry')
    for path in value['evidence_runs']: require(Path(path).is_absolute(), 'evidence-run-path')
    for window in value['excluded_windows']:
        a,b = utc(window['start']), utc(window['end'])
        require(a < b and not (begin < b and end > a), 'evidence-window-overlap')


def approve_check(approval, expected_file_sha256, path):
    # The caller must supply the digest Howard approved; this module cannot
    # manufacture it from a proposal or persist approval on his behalf.
    require(sha(path) == expected_file_sha256, 'approval-file-changed')
    validate(approval)
    from tools.ms94_b06_oct13_authorization import SCHEMA, validate_request, require_active
    if approval.get('artifact_type')==SCHEMA:
        validate_request(approval);require_active(approval);return
    require(approval.get('artifact_type') == 'b06-engineering-standing-approval/1' and
            approval.get('approved') is True and approval.get('approved_by') == 'Howard' and
            isinstance(approval.get('approval_reference'), str) and approval['approval_reference'], 'approval-required')
    utc(approval['approved_at_utc'])
    validate_instrumented(approval)


def guard(approval, moment=None, starting=False, attempt_number=1):
    validate(approval)
    moment = moment or now()
    require(utc(approval['not_before_utc']) <= moment < utc(approval['deadline_utc']), 'outside-window')
    remaining = (utc(approval['deadline_utc'])-moment).total_seconds()
    require(type(attempt_number) is int and 1 <= attempt_number <= approval['run_cap'], 'attempt-number')
    attempts_remaining=approval['run_cap']-attempt_number+1
    require(not starting or remaining >= attempts_remaining*(LIMITS['run_seconds']+LIMITS['cleanup_seconds']), 'full-run-budget')
    for name in approval['evidence_runs']:
        path = Path(name)
        require(path.is_dir(), 'evidence-registry-unavailable')
        if (path/'armed.json').exists():
            require((path/'exited.json').is_file(), 'evidence-launcher-active')
        if (path/'execution/started.json').exists():
            require((path/'execution/report.json').is_file() and (path/'exited.json').is_file(), 'evidence-active')


class Ledger:
    def __init__(self, root, approval, public=None):
        self.root = Path(root).resolve(); self.approval = approval; self.public=public
        require(self.root.name == 'b06-engineering' and not any(p.is_symlink() for p in (self.root,*self.root.parents)), 'output-root')
        require(self.root==Path(approval['output_root']).resolve(), 'approval-output-root')
        self.session = self.root/approval['content_sha256']

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        # A crash leaves the lease in place. No stale-lock auto-recovery.
        path = self.root/'active.lock'
        with path.open('x') as stream: stream.write(self.approval['content_sha256'])
        try: yield
        finally:
            # Retain the lease after incomplete cleanup or an interrupted run.
            runs = sorted((self.session/'runs').glob('journey-*'))
            import sys
            if sys.exc_info()[0] is None:
                self.verify_prior_runs()
                path.unlink()

    def verify_prior_runs(self):
        from tools.ms94_b06_engineering_evidence import verify_prior
        numbers=[]
        for run in sorted((self.session/'runs').glob('journey-*')):
            numbers.append(verify_prior(run,self.approval,self.public)['run_number'])
        require(sorted(numbers)==list(range(1,len(numbers)+1)),'prior-attempt-sequence')

    def next_attempt_number(self):
        number=len(list((self.session/'runs').glob('journey-*')))+1
        require(number <= self.approval['run_cap'], 'run-cap-exhausted')
        return number

    def reserve(self, source_commit):
        number=self.next_attempt_number()
        guard(self.approval, starting=True, attempt_number=number)
        require(re.fullmatch('[0-9a-f]{40}', source_commit) is not None, 'source-commit')
        runs = sorted((self.session/'runs').glob('journey-*'))
        require(len(runs) < self.approval['run_cap'], 'run-cap-exhausted')
        self.verify_prior_runs()
        number = len(runs)+1
        run = self.session/'runs'/('journey-'+uuid.uuid4().hex)
        run.mkdir(parents=True, exist_ok=False)
        write_new(run/'engineering.json', seal(dict(**LABEL, artifact_type='b06-engineering-run/1',
            run_number=number, source_commit=source_commit, runtime_source_commit=self.approval['observer_source'],
            image=IMAGE, approval_sha256=self.approval['content_sha256'], owner=run.name,
            mode=self.approval['attempt_modes'][number-1],
            engineering_key_sha256=self.approval['engineering_key_sha256'],
            started_utc=now().isoformat(), model_calls=0)))
        return run


class EngineeringSigner:
    def __init__(self, signer): self.signer, self.public = signer, signer.public
    def sign(self, body):
        require('signature' not in body and 'content_sha256' not in body, 'already-signed-body')
        return self.signer.sign({**body, **LABEL})


def seal_artifacts(run, signer, approval=None):
    run = Path(run)
    entries = []
    for path in sorted(run.rglob('*')):
        require(not path.is_symlink(), 'artifact-link')
        if path.is_file():
            entries.append(dict(**LABEL, path=path.relative_to(run).as_posix(), sha256=sha(path), bytes=path.stat().st_size))
    from tools.ms94_b06_engineering_evidence import binding
    bound=binding(run,approval) if approval is not None else {}
    value = signer.sign(dict(**LABEL, **bound, artifact_type='b06-engineering-artifacts/1', artifacts=entries))
    write_new(run/'artifacts.json', value)
    return value


def refusal_context(run):
    path = Path(run)/'posting-observer/oracle/events.jsonl'
    last = None
    if path.exists():
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                require(len(line) <= 4*1024*1024+1, 'event-too-large')
                row = json.loads(line); event = row.get('event', row)
                if event.get('kind') == 'observer-audit':
                    from tools.ms94_b06_observer_format import audit_detail
                    event=audit_detail(event)
                    if event.get('action') == 'jdi-event': last = event
                    if event.get('action') == 'dispatch-refused':
                        return dict(refusal=event, preceding_event=last)
    return None


def append_log(path, record, terminal, context):
    # Hash-only/context identifiers, never arbitrary exception text or values.
    detail = ((context or {}).get('preceding_event') or {}).get('detail', {})
    def safe(value): return str(value if value is not None else 'n/a').replace('|','/').replace('\n',' ')[:300]
    cells = [record['run_number'], record['source_commit'], terminal['outcome'],
             ((context or {}).get('refusal') or {}).get('sequence'), detail.get('thread_id'),
             (detail.get('location') or {}).get('method', detail.get('method')), detail.get('depth')]
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write('| '+' | '.join(map(safe,cells))+' | engineering | false | false |\n')


def validate_instrumented(value):
    """Exact implementation binding; execution additionally requires the branch gate."""
    require(re.fullmatch('[0-9a-f]{40}',value.get('implementation_commit','')) is not None,'implementation-commit')
    for name in ('native_template_sha256','observer_source_sha256'):
        require(re.fullmatch('[0-9a-f]{64}',value.get(name,'')) is not None,name)
    classes=value.get('observer_class_files_sha256',{})
    require(bool(classes) and all(name.endswith('.class') and re.fullmatch('[0-9a-f]{64}',digest)
            for name,digest in classes.items()),'compiled-observer-bindings')
    require(value.get('observer_configuration') == dict(mode_sequence=['strict','diagnostic-unmatched-return'],
        format='bounded-observer-v1',unmatched_return_cap=10,heap_guard_percent=85,pending_cap=512), 'observer-configuration')
    require((utc(value['not_before_utc'])-utc(value['full_plan_delivered_at_utc'])).total_seconds() >= 4*3600,
            'four-hour-plan-review')


def instrumented_proposal(start,end,excluded_windows,evidence_runs,output_root,*,
                          implementation_commit,native_template_sha256,observer_source_sha256,
                          observer_class_files_sha256,full_plan_delivered_at_utc):
    value=proposal(start,end,excluded_windows,evidence_runs,output_root)
    body={k:v for k,v in value.items() if k!='content_sha256'}
    body.update(implementation_commit=implementation_commit,observer_source=implementation_commit,
        native_template_sha256=native_template_sha256,
        observer_source_sha256=observer_source_sha256,observer_class_files_sha256=observer_class_files_sha256,
        full_plan_delivered_at_utc=full_plan_delivered_at_utc,
        observer_configuration=dict(mode_sequence=['strict','diagnostic-unmatched-return'],
            format='bounded-observer-v1',unmatched_return_cap=10,heap_guard_percent=85,pending_cap=512))
    result=seal(body);validate(result);validate_instrumented(result);return result


def validate_run_binding(run, approval, plan=None):
    """Refuse altered attempt order/mode before key loading or native execution."""
    run=Path(run).resolve();validate(approval);validate_instrumented(approval)
    require(run.parent==Path(approval['output_root']).resolve()/approval['content_sha256']/'runs',
            'attempt-session-path')
    require(re.fullmatch('journey-[0-9a-f]{32}',run.name) is not None,'attempt-owner')
    record=read_json(run/'engineering.json');verify(record)
    number=record.get('run_number')
    require(type(number) is int and 1 <= number <= 2,'attempt-number')
    require(len(list(run.parent.glob('journey-*')))==number,'attempt-current-sequence')
    require(record.get('owner')==run.name and record.get('approval_sha256')==approval['content_sha256'] and
            record.get('source_commit')==approval['implementation_commit'] and
            record.get('runtime_source_commit')==approval['observer_source'] and
            record.get('engineering_key_sha256')==approval['engineering_key_sha256'] and
            record.get('mode')==approval['attempt_modes'][number-1] and
            all(record.get(k)==v for k,v in LABEL.items()),'attempt-approval-binding')
    if plan is not None:
        verify(plan)
        from tools.ms94_b06_observer_diagnostics import validate as validate_diagnostics
        diagnostics=validate_diagnostics(plan)
        require(diagnostics is not None and diagnostics['mode']==record['mode'] and
                plan.get('engineering_approval_sha256')==approval['content_sha256'] and
                plan.get('engineering_key_sha256')==approval['engineering_key_sha256'] and
                plan.get('engineering_template_sha256')==approval['native_template_sha256'] and
                plan.get('engineering_limits')==(attempt_limits(number) if approval.get('attempt_limits') else LIMITS) and
                plan.get('posting_observer',{}).get('class_files_sha256')==approval['observer_class_files_sha256'],
                'attempt-plan-binding')
    return record
