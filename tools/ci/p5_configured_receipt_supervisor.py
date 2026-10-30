"""Observe the original child process of one configured receipt invocation.

Diagnostic text only: no signed outcome, admission, descendant-death or crash
qualification. Missing terminal observation means unknown. Never retry or kill.
The child retains every original native proof, nonce, lease and receipt check.
"""
import os,subprocess,sys,time
from datetime import datetime,timezone
from contextlib import contextmanager
from pathlib import Path

def _write(stream,event,**values):
    # Fixed public fields only. Never serialize argv, environment, keys or
    # exception messages. This text is not consumed as authority by any reader.
    row={'event':event,'utc':datetime.now(timezone.utc).isoformat(),
         'monotonic_ns':time.monotonic_ns(),**values}
    stream.write(' '.join(str(k)+'='+str(v) for k,v in row.items())+'\n')
    stream.flush();os.fsync(stream.fileno())

def _discard_parent_provider_environment():
    # Delete names without reading, returning, logging or persisting values.
    # This changes only this supervisor process, not the already-created child
    # or the runner/job environment. It is not secure memory erasure.
    for name in ('OPENAI_API_KEY','FACTORY_TRANSPORT_KEY'):
        if name in os.environ:del os.environ[name]

def _launch_and_wait(command,cwd,stream):
    _write(stream,'launch-intent')
    try:
        child=subprocess.Popen(command,cwd=cwd,stdin=subprocess.DEVNULL,
                               close_fds=True,shell=False)
    except OSError:
        _write(stream,'launch-refused')
        raise
    # If retaining the PID fails, still wait on this same original handle.
    # A parent cancellation/host crash is not converted into a death claim.
    try:
        # Popen has already copied the original environment to the sole child.
        # Keep the wait in finally even if deleting a parent name fails.
        _discard_parent_provider_environment()
        _write(stream,'child-created',pid=child.pid)
    finally:
        result=child.wait()
    _write(stream,'original-child-reaped',pid=child.pid,returncode=result)
    return result

def _diagnose_reaped_abort(root,review,live_ci,stream):
    # Called only after the original wait and its durable reaped observation.
    # These public digests are diagnostic; original file bytes stay at source.
    # Neither a text row nor a passed relation establishes descendant death,
    # genuine admission, an authenticated outcome or a strict case result.
    try:
        from hashlib import sha256
        from lightyear_factory.contracts import canonical_hash
        from lightyear_execution.configured_abort_preflight_join import read_preflight_bound_abort
        observed=read_preflight_bound_abort(root,review,live_ci)
        for name,raw in sorted(observed['original_files'].items()):
            _write(stream,'abort-original-file',name=name,bytes=len(raw),sha256=sha256(raw).hexdigest())
        for name,row in sorted(observed['service_observations'].items()):
            _write(stream,'abort-service-document',name=name,canonical_sha256=canonical_hash(row))
        _write(stream,'abort-prelaunch-relations-observed',review_sha256=review['content_sha256'])
    except Exception:
        # Preserve the child's original return code even if diagnostics fail.
        # Missing admission/terminal rows, service outage and unstable files
        # remain unknown; no exception details or keys are emitted.
        try:_write(stream,'abort-observation-unavailable')
        except Exception:pass

def _diagnose_reaped_terminal(root,review,live_ci,stream,*,runtime):
    # Separate terminal-file path. Retained bytes and service metadata remain
    # unsigned diagnostics, never original-controller or strict outcome authority.
    try:
        from hashlib import sha256
        from lightyear_factory.contracts import canonical_hash
        from lightyear_execution.configured_terminal_preflight_join import read_preflight_bound_terminal
        observed=read_preflight_bound_terminal(root,review,live_ci,runtime=runtime)
        for name,raw in sorted(observed['original_files'].items()):
            _write(stream,'terminal-original-file',name=name,bytes=len(raw),sha256=sha256(raw).hexdigest())
        for name,row in sorted(observed['service_observations'].items()):
            _write(stream,'terminal-service-document',name=name,canonical_sha256=canonical_hash(row))
        _write(stream,'terminal-prelaunch-relations-observed',review_sha256=review['content_sha256'])
    except Exception:
        # No fallback to abort on malformed/partial terminal evidence, no proof
        # reentry and no conversion of the original failed child result.
        try:_write(stream,'terminal-observation-unavailable')
        except Exception:pass


@contextmanager
def _observe_preflight_timing():
    # Real local clocks only, never passed to proof/expiry/admission checks.
    # CI stderr is diagnostic and may be lost on abrupt process/host death.
    start=None
    try:start=(datetime.now(timezone.utc).isoformat(),time.monotonic_ns())
    except Exception:pass
    completed=False
    try:
        yield
        completed=True
    finally:
        try:
            if start is None:
                print('configured-preflight-timing-unavailable',file=sys.stderr,flush=True)
            else:
                end_ns=time.monotonic_ns();end_utc=datetime.now(timezone.utc).isoformat()
                if end_ns<start[1]:raise ValueError('preflight-clock-order')
                print('configured-preflight-timing'
                    +' start_utc='+start[0]+' end_utc='+end_utc
                    +' start_monotonic_ns='+str(start[1])+' end_monotonic_ns='+str(end_ns)
                    +' elapsed_ns='+str(end_ns-start[1])+' completed='+str(completed),
                    file=sys.stderr,flush=True)
        except Exception:
            # Timing or ordinary output errors cannot replace original return
            # or exception. Missing output remains unknown, never zero duration.
            try:print('configured-preflight-timing-unavailable',file=sys.stderr,flush=True)
            except Exception:pass


def _main(argv=None):
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise ValueError('configured-supervisor-ci-only')
    from lightyear_factory.cli import build_parser
    from lightyear_execution.configured_receipt_dispatch import _prepare,_dispatch_paths
    from lightyear_execution.human_drill_dispatch import _fresh_directory
    arguments=list(sys.argv[1:] if argv is None else argv)
    args=build_parser().parse_args(['human-configured-receipt-execute',*arguments])
    # Genuine read-only proof/workflow/runtime preflight before allocating any
    # diagnostic path or starting a child. No nonce or key lease in the parent.
    with _observe_preflight_timing():
        bundle=_prepare(args)
    root,_=_dispatch_paths(args,bundle)
    source=bundle['admission'].root
    # Capture actual parent CI values before launch; no caller-supplied expected
    # identity is accepted by the fixed production entry.
    live_ci=dict(repository=os.environ['GITHUB_REPOSITORY'],
        run_id=int(os.environ['GITHUB_RUN_ID']),run_attempt=int(os.environ['GITHUB_RUN_ATTEMPT']),
        job=os.environ['GITHUB_JOB'])
    target=_fresh_directory(root.parent/(root.name+'-supervisor'),source)
    target.mkdir()
    with (target/'original-process.txt').open('x',encoding='ascii',newline='\n') as stream:
        # Fixed native entry and original Python executable, one invocation.
        result=_launch_and_wait([sys.executable,'-B','-m',
            'tools.ci.p5_configured_receipt_positive',*arguments],source,stream)
        if result!=0:
            run=root/('drill-'+bundle['review']['drill_binding']['nonce_sha256'][:32])
            terminal_paths=(run/'receipt.json',run/'summary.json',root/'terminal-originals')
            if any(p.exists() or p.is_symlink() for p in terminal_paths):
                _diagnose_reaped_terminal(root,bundle['review'],live_ci,stream,runtime=bundle['runtime'])
            else:
                _diagnose_reaped_abort(root,bundle['review'],live_ci,stream)
    # Preserve a failure for signal termination instead of Python's modulo
    # conversion of a negative return code. No retry/resume interpretation.
    return result if result>=0 else min(255,128-result)

def main(argv=None):
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise ValueError('configured-supervisor-ci-only')
    try:
        return _main(argv)
    finally:
        # Also discard names after parse/preflight/intent/spawn failures. Never
        # restore them for a retry. Child admission and lease checks are intact.
        _discard_parent_provider_environment()

if __name__=='__main__':raise SystemExit(main())
