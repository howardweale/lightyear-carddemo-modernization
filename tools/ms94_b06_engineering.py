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
              application_memory_mib=8192, observer_memory_mib=768,
              database_cpus=2, carrier_cpus=4, application_cpus=4, observer_cpus=1,
              output_bytes=8*1024**3, minimum_free_bytes=60*1024**3,
              audit_records=500000, audit_bytes=128*1024**2, evidence_records=50000)


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


def proposal(start, end, excluded_windows, evidence_runs, output_root, run_cap=10):
    value = seal(dict(artifact_type='b06-engineering-standing-proposal/1', **LABEL,
        image=IMAGE, observer_source=OBSERVER_SOURCE, scope='J1-retained-reference-oracle-only',
        run_cap=run_cap, not_before_utc=start, deadline_utc=end, limits=LIMITS,
        excluded_windows=excluded_windows, evidence_runs=evidence_runs, output_root=str(Path(output_root).resolve()),
        model_calls=0, approved=False, no_degradation=True, no_automatic_retries=True))
    validate(value)
    return value


def validate(value):
    verify(value)
    require(value.get('run_class')=='engineering' and value.get('qualification_credit') is False and value.get('measurement_credit') is False, 'labels')
    require(value.get('image') == IMAGE and value.get('observer_source') == OBSERVER_SOURCE, 'fixed-runtime')
    require(value.get('scope') == 'J1-retained-reference-oracle-only', 'scope')
    require(type(value.get('run_cap')) is int and 1 <= value['run_cap'] <= 10, 'run-cap')
    require(value.get('limits') == LIMITS and value.get('model_calls') == 0 and
            value.get('no_degradation') is True and value.get('no_automatic_retries') is True, 'limits')
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
    require(approval.get('artifact_type') == 'b06-engineering-standing-approval/1' and
            approval.get('approved') is True and approval.get('approved_by') == 'Howard' and
            isinstance(approval.get('approval_reference'), str) and approval['approval_reference'], 'approval-required')
    utc(approval['approved_at_utc'])


def guard(approval, moment=None, starting=False):
    validate(approval)
    moment = moment or now()
    require(utc(approval['not_before_utc']) <= moment < utc(approval['deadline_utc']), 'outside-window')
    remaining = (utc(approval['deadline_utc'])-moment).total_seconds()
    require(not starting or remaining >= LIMITS['run_seconds']+LIMITS['cleanup_seconds'], 'full-run-budget')
    for name in approval['evidence_runs']:
        path = Path(name)
        require(path.is_dir(), 'evidence-registry-unavailable')
        if (path/'armed.json').exists():
            require((path/'exited.json').is_file(), 'evidence-launcher-active')
        if (path/'execution/started.json').exists():
            require((path/'execution/report.json').is_file() and (path/'exited.json').is_file(), 'evidence-active')


class Ledger:
    def __init__(self, root, approval):
        self.root = Path(root).resolve(); self.approval = approval
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
            if sys.exc_info()[0] is None and all((r/'artifacts.json').is_file() and (r/'terminal.json').is_file() and read_json(r/'terminal.json').get('cleanup_verified') is True for r in runs):
                path.unlink()

    def reserve(self, source_commit):
        guard(self.approval, starting=True)
        require(re.fullmatch('[0-9a-f]{40}', source_commit) is not None, 'source-commit')
        runs = sorted((self.session/'runs').glob('journey-*'))
        require(len(runs) < self.approval['run_cap'], 'run-cap-exhausted')
        for run in runs:
            require((run/'artifacts.json').is_file() and (run/'terminal.json').is_file() and read_json(run/'terminal.json').get('cleanup_verified') is True, 'prior-run-unsealed')
        number = len(runs)+1
        run = self.session/'runs'/('journey-'+uuid.uuid4().hex)
        run.mkdir(parents=True, exist_ok=False)
        write_new(run/'engineering.json', seal(dict(**LABEL, artifact_type='b06-engineering-run/1',
            run_number=number, source_commit=source_commit, runtime_source_commit=OBSERVER_SOURCE,
            image=IMAGE, approval_sha256=self.approval['content_sha256'], owner=run.name,
            started_utc=now().isoformat(), model_calls=0)))
        return run


class EngineeringSigner:
    def __init__(self, signer): self.signer, self.public = signer, signer.public
    def sign(self, body):
        require('signature' not in body and 'content_sha256' not in body, 'already-signed-body')
        return self.signer.sign({**body, **LABEL})


def seal_artifacts(run, signer):
    run = Path(run)
    entries = []
    for path in sorted(run.rglob('*')):
        require(not path.is_symlink(), 'artifact-link')
        if path.is_file():
            entries.append(dict(**LABEL, path=path.relative_to(run).as_posix(), sha256=sha(path), bytes=path.stat().st_size))
    value = signer.sign(dict(**LABEL, artifact_type='b06-engineering-artifacts/1', artifacts=entries))
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
