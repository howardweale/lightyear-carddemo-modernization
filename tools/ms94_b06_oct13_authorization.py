"""Branch-only Oct13 gate: explicit exact Howard go required; no side effects."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import re
from lightyear_calibration.contracts import read_json, verify

SCHEMA='b06-oct13-executable-request/1'
WINDOW=('2026-10-13T16:00:00Z','2026-10-13T19:00:00Z')
_ACTIVE=ContextVar('b06_oct13_exact_go',default=None)

def expected_go(request):
    return 'go B06 '+request['implementation_commit']+' '+request['content_sha256']

def validate_request(request):
    from tools.ms94_b06_engineering import validate, validate_instrumented, require, attempt_limits, utc
    verify(request);validate(request);validate_instrumented(request)
    require(request.get('artifact_type')==SCHEMA and request.get('approved') is False,'oct13-request-shape')
    require((request['not_before_utc'],request['deadline_utc'])==WINDOW,'oct13-calendar')
    for name in ('asset_index_sha256','asset_index_file_sha256','cap_projection_sha256','host_witness_validation_sha256','mirror_adapter_source_sha256'):
        require(re.fullmatch('[0-9a-f]{64}',request.get(name,'')) is not None,'oct13-'+name)
    require(len(request['observer_class_files_sha256'])==14,'oct13-compiled-class-count')
    require(request.get('source_change_reason')=='B3.4 genuine generation-input witnesses and attempt2 metadata caps; baseline observer preserved','oct13-source-change-disclosure')
    require(request.get('attempt_limits')==[attempt_limits(1),attempt_limits(2)],'oct13-attempt-limits')
    require(utc(request['full_plan_delivered_at_utc'])<=utc('2026-10-13T00:00:00Z'),'oct13-delivery-deadline')
    require(request.get('cause_identified_criteria')==CAUSE_CRITERIA,'oct13-cause-criteria')
    require(request.get('class_input_witness_policy')=='generation-inputs-v1','oct13-input-witness')
    require(request.get('automatic_second_attempt') is False and request.get('stop_after_two') is True,'oct13-sequence')
    require(request.get('observer_source_baseline_sha256')=='02b2f7fd4080bfbcd821ef51147c455d7f57620eac797b809d406d73f935c64b','oct13-baseline')

CAUSE_CRITERIA={
 'a': 'At the first unmatched-return sequence, a lifecycle or class-prepare record explains the missed entry breakpoint by request disabled, class redefined/reloaded, or thread-filter mismatch.',
 'b': 'An application-phase marker ties the approximately 12,400-generation point to one operation and reproduces in both attempts.',
 'otherwise': 'Cause not identified: stop observer repair; Howard selects an alternative. No further repair attempt.'}

def require_active(request=None):
    from tools.ms94_b06_engineering import require
    active=_ACTIVE.get()
    require(active is not None,'on-hold-review-291-302-renewed-approval-required')
    if request is not None:
        require((request.get('implementation_commit'),request.get('content_sha256'))==active,'oct13-go-request-mismatch')

def active_go(request):
    require_active(request);return expected_go(request)

@contextmanager
def authorized(request_path,expected_file_sha256,go):
    from tools.ms94_b06_engineering import sha, require
    from tools.ms94_b06_engineering_run import source_commit
    path=Path(request_path);request=read_json(path)
    require(sha(path)==expected_file_sha256,'approval-file-changed');validate_request(request)
    require(go==expected_go(request),'oct13-exact-howard-go-required')
    require(source_commit(Path(__file__).resolve().parents[1])==request['implementation_commit'],'implementation-commit-changed')
    token=_ACTIVE.set((request['implementation_commit'],request['content_sha256']))
    try:yield request
    finally:_ACTIVE.reset(token)
