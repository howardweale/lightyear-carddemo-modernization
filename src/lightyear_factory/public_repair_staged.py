"""Public-only staged controller and selected-jar retention; no hidden executor.

Admission authenticates commitments and the operator's approval outside this
module. Timestamp ordering alone is not evidence of prior publication. The
admission port must check the exact pre-run commitment receipt independently.
"""
from datetime import datetime
from functools import partial
import inspect
import json
import os
from pathlib import Path
import stat
import time

from lightyear_factory import public_repair_controller as c
from lightyear_factory import public_repair_durable as durable
from lightyear_factory import public_value_feedback as values

JAR_BYTES = 16777216
LEAF = 'selected-candidate.jar'
POLICY = dict(schema='staged-public-policy/1', mode='STAGED_PUBLIC',
    hidden_operation='separate-human-verifier', hidden_invocations=0,
    selection='maximum-public-match-ties-latest', jar_bytes_max=JAR_BYTES,
    retention_seconds=600, models_closed_before_retention=True,
    rebuild_allowed=False, reselection_allowed=False, public_perfect_required=True)
POLICY_HASH = c.digest(POLICY)
CODES = frozenset(('staged-binding', 'staged-commitment', 'staged-time',
    'staged-retention', 'staged-jar', 'staged-build-join', 'staged-worker',
    'staged-path', 'staged-file', 'staged-posix', 'staged-json', 'staged-closed'))


def strict(raw):
    def pairs(items):
        row = {}
        for key, value in items:
            c.require(key not in row, 'staged-json')
            row[key] = value
        return row
    def invalid(_):
        raise c.Refused('staged-json')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=invalid,
                           parse_constant=invalid)
        c.canonical(value)
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise c.Refused('staged-json') from None


def instant(value):
    c.require(type(value) is str and len(value) <= 40, 'staged-time')
    try:
        result = datetime.fromisoformat(value)
        c.require(result.tzinfo is not None and result.utcoffset() is not None,
                  'staged-time')
        return result
    except ValueError:
        raise c.Refused('staged-time') from None


def validate_binding(row, context):
    extra = ('mode pre_run_commitment approval_timestamp public_answer_key_sha256 '
             'staged_policy_sha256 worker_source_sha256 build_profile').split()
    c.require(type(row) is dict and all(k in row for k in extra), 'staged-binding')
    base = {k: v for k, v in row.items() if k not in extra}
    c.require(base.get('schema') == 'staged-public-binding/1'
              and row['mode'] == 'STAGED_PUBLIC'
              and row['staged_policy_sha256'] == POLICY_HASH, 'staged-binding')
    base['schema'] = 'public-repair-binding/1'
    if base.get('feedback_contract_sha256') == values.HASH:
        c.require(base.get('public_suite_sha256') == values.SUITE
                  and row['public_answer_key_sha256'] == values.KEY, 'feedback-join')
        c.validate_binding(base, context, feedback_hash=values.HASH)
    else:
        c.validate_binding(base, context)
    c.require(base['public_case_count'] == 16, 'staged-binding')
    for key in ('public_answer_key_sha256', 'worker_source_sha256'):
        c.require(c.hash_ok(row[key]), 'staged-binding')
    profile = row['build_profile']
    c.shape(profile, 'cli_sha256 helper_sha256 jdk_sha256 jre_sha256', 'staged-binding')
    c.require(all(c.hash_ok(v) for v in profile.values()), 'staged-binding')
    commitment = row['pre_run_commitment']
    c.shape(commitment, 'schema committed_at commitment_sha256 publication_receipt_sha256',
            'staged-commitment')
    c.require(commitment['schema'] == 'heldout-pre-run-commitment/1'
              and all(c.hash_ok(v) for k, v in commitment.items() if k.endswith('_sha256'))
              and c.digest(commitment) == base['heldout_commitment_sha256'], 'staged-commitment')
    c.require(instant(commitment['committed_at']) < instant(row['approval_timestamp']),
              'staged-time')


def validate_descriptor(row, selected, binding, closure):
    c.shape(row, 'schema binding_sha256 source_sha256 jar_sha256 jar_bytes '
            'build_receipt_sha256 public_receipt_sha256 retained_leaf readback_sha256 '
            'runtime_profile_sha256 worker_source_sha256 closure_record_sha256 '
            'heldout_commitment_sha256', 'staged-retention')
    c.require(row['schema'] == 'retained-selected-jar/1'
              and all(c.hash_ok(v) for k, v in row.items() if k.endswith('_sha256'))
              and row['binding_sha256'] == c.digest(binding)
              and row['source_sha256'] == selected['artifact_sha256']
              and row['build_receipt_sha256'] == selected['build_receipt_sha256']
              and row['public_receipt_sha256'] == selected['public_receipt_sha256']
              and row['jar_sha256'] == row['readback_sha256']
              and row['runtime_profile_sha256'] == binding['runtime_profile_sha256']
              and row['worker_source_sha256'] == binding['worker_source_sha256']
              and row['closure_record_sha256'] == closure
              and row['heldout_commitment_sha256'] == binding['heldout_commitment_sha256']
              and row['retained_leaf'] == LEAF
              and type(row['jar_bytes']) is int and 0 < row['jar_bytes'] <= JAR_BYTES,
              'staged-retention')
    return strict(c.canonical(row))


class StagedController(c.Controller):
    """Graph-off only. Retention port cannot grant stage-2 execution authority."""
    validate = staticmethod(validate_binding)

    def finish_selected(self, selected):
        c.require(self.closed, 'staged-closed')
        closure = dict(schema='staged-model-closure/1', binding_sha256=self.binding_sha256,
                       model_ports_closed=True, further_model_calls_allowed=False)
        self.record('models-closed', closure)
        self.closure_hash = c.sha(c.canonical(closure) + b'\n')
        self.retained_jar = None
        if selected is None:
            return 'CANDIDATE_FAIL', dict(status='NOT_RUN', reason='no-evaluated-candidate')
        if selected['different']:
            return 'PUBLIC_FAIL', dict(status='NOT_RUN', reason='public-fail')
        self.stage = 'retain-selected-jar'
        deadline = self.phase(600)
        row = self.ports.retain_selected_jar(selected, self.binding, self.closure_hash, deadline)
        self.now_before(deadline)
        self.retained_jar = validate_descriptor(row, selected, self.binding, self.closure_hash)
        self.record('retained-selected-jar', self.retained_jar)
        return 'PUBLIC_COMPLETE_HIDDEN_PENDING', dict(status='PENDING',
            reason='separate-human-verifier', selected_jar_sha256=self.retained_jar['jar_sha256'])

    def result_record(self, selected, status, hidden):
        result = super().result_record(selected, status, hidden)
        result.update(schema='staged-public-result/1', mode='STAGED_PUBLIC',
            pre_run_commitment_sha256=self.binding['heldout_commitment_sha256'],
            public_answer_key_sha256=self.binding['public_answer_key_sha256'],
            closure_record_sha256=self.closure_hash, retained_jar=self.retained_jar,
            hidden_execution_authorized=False, mainframe_qualification_claimed=False)
        return result

    def failure(self, name, error):
        if isinstance(error, c.Refused) and str(error) in CODES:
            try:
                self.record(name, dict(failure_schema='public-repair-failure/1',
                    refusal_code=str(error), stage=self.stage))
            except BaseException:
                pass
        else:
            super().failure(name, error)


def validate_value_binding(row, context):
    validate_binding(row, context)
    c.require(row['feedback_contract_sha256'] == values.HASH, 'binding-hash')


class ValueStagedController(StagedController):
    validate = staticmethod(validate_value_binding)
    check_feedback = staticmethod(values.validate)
    project = staticmethod(partial(c.projection, feedback_validator=values.validate))


class StagedDurablePorts(durable.DurablePorts):
    """Adds only a bounded binary slot, using P3's exclusive full-sync readback."""
    def retain_jar(self, raw):
        def write():
            c.require(type(raw) is bytes and 0 < len(raw) <= JAR_BYTES, 'staged-jar')
            return self._write(LEAF, raw)
        return self._operation(write)


def read_owned(path, cap):
    """Production POSIX read; no symlink, hardlink, writable peer or partial read."""
    c.require(os.name == 'posix', 'staged-posix')
    path = Path(path)
    c.require(path.is_absolute() and path == path.resolve(strict=True), 'staged-path')
    for parent in (path.parent, *path.parents):
        info = parent.stat()
        c.require(info.st_uid in (0, os.getuid()) and not stat.S_IMODE(info.st_mode) & 0o022,
                  'staged-path')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        c.require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                  and before.st_uid == os.getuid()
                  and stat.S_IMODE(before.st_mode) in (0o400, 0o444, 0o600)
                  and 0 < before.st_size <= cap, 'staged-file')
        chunks, remaining = [], cap + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b''.join(chunks)
        after, named = os.fstat(fd), path.stat(follow_symlinks=False)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        c.require(all(getattr(before, k) == getattr(after, k) == getattr(named, k) for k in fields)
                  and len(raw) == before.st_size, 'staged-file')
        return raw
    finally:
        os.close(fd)


class P5SelectedJarRetainer:
    """Read P5's existing build registry and receipt; never invoke a build.

    L1 wires this method only after close_models succeeds. The binding admits
    the P5 implementation and image/helper/CLI hashes. P5 need not be imported
    here (it can be independently reviewed/merged); its closed receipt is joined.
    """
    def __init__(self, worker, storage, *, clock=time.monotonic):
        self.worker, self.storage, self.clock = worker, storage, clock
        self.used = False

    def retain_selected_jar(self, selected, binding, closure, deadline):
        c.require(not self.used and self.clock() < deadline, 'staged-retention')
        self.used = True  # any uncertainty consumes this retention attempt
        c.require(not self.worker.failed, 'staged-worker')
        module_path = inspect.getsourcefile(type(self.worker))
        c.require(module_path is not None and
                  c.sha(Path(module_path).read_bytes()) == binding['worker_source_sha256'],
                  'staged-worker')
        key = selected['build_receipt_sha256']
        c.require(key in self.worker.built, 'staged-build-join')
        source, jar, jar_hash = self.worker.built[key]
        root = Path(self.worker.root) / ('build-' + str(selected['round']))
        c.require(Path(jar) == root / 'candidate.jar'
                  and source == selected['artifact_sha256'] and c.hash_ok(jar_hash),
                  'staged-build-join')
        receipt_bytes = read_owned(root / 'receipt.json', 65536)
        c.require(c.sha(receipt_bytes) == key, 'staged-build-join')
        receipt = strict(receipt_bytes)
        c.shape(receipt, 'schema operation result cleanup_sha256 cli_sha256 helper_sha256 '
                'jdk_sha256 jre_sha256 public_only', 'staged-build-join')
        c.require(receipt['schema'] == 'public-worker-receipt/1'
                  and receipt['operation'] == 'compile' and receipt['public_only'] is True
                  and all(receipt[k] == v for k, v in binding['build_profile'].items()),
                  'staged-build-join')
        result = receipt['result']
        c.require(type(result) is dict and type(result.get('exit_code')) is int
                  and result['exit_code'] == 0 and result.get('artifact_sha256') == source
                  and result.get('jar_sha256') == jar_hash, 'staged-build-join')
        cleanup_bytes = read_owned(root / 'cleanup.json', 65536)
        c.require(c.sha(cleanup_bytes) == receipt['cleanup_sha256'], 'staged-build-join')
        cleanup = strict(cleanup_bytes)
        c.require(type(cleanup) is dict and cleanup.get('cleanup') is True, 'staged-build-join')
        raw = read_owned(jar, JAR_BYTES)
        c.require(c.sha(raw) == jar_hash and self.clock() < deadline, 'staged-jar')
        readback = self.storage.retain_jar(raw)
        c.require(readback == jar_hash and self.clock() < deadline, 'staged-retention')
        return validate_descriptor(dict(schema='retained-selected-jar/1',
            binding_sha256=c.digest(binding), source_sha256=source, jar_sha256=jar_hash,
            jar_bytes=len(raw), build_receipt_sha256=key,
            public_receipt_sha256=selected['public_receipt_sha256'], retained_leaf=LEAF,
            readback_sha256=readback, runtime_profile_sha256=binding['runtime_profile_sha256'],
            worker_source_sha256=binding['worker_source_sha256'], closure_record_sha256=closure,
            heldout_commitment_sha256=binding['heldout_commitment_sha256']), selected, binding, closure)
