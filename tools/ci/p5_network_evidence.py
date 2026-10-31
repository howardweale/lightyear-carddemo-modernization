"""Retain the existing real OCI network-denial experiment without qualification claims."""
import base64
import hashlib
import json
import re


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def capture(raw):
    if not isinstance(raw, bytes) or len(raw) > 65536:
        raise ValueError('p5-network-output-limit')
    return dict(base64=base64.b64encode(raw).decode('ascii'), sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))


def validate(value):
    def require(ok):
        if not ok: raise ValueError('p5-network-evidence-invalid')
    def stream(row):
        raw = base64.b64decode(row['base64'], validate=True)
        require(type(row['size']) is int and len(raw) == row['size'] <= 65536)
        require(hashlib.sha256(raw).hexdigest() == row['sha256'])
    try:
        require(value['schema'] == 'p5-retained-oci-network/1')
        require(value['scope'] == 'OCI component denial; controller receipt remains unmeasured')
        require(value['production_controller_receipt'] is False)
        require(re.fullmatch('[0-9a-f]{64}', value['policy_sha256']) is not None)
        code = value['probe_code']; require(isinstance(code, str) and 0 < len(code) < 4096)
        require(hashlib.sha256(code.encode()).hexdigest() == value['probe_sha256'])
        gateway, port = value['gateway'], value['port']
        require(isinstance(gateway, str) and type(port) is int and 1 <= port <= 65535)
        tail = [value['image'], 'python3', '-c', code, gateway, str(port)]
        first, last = value['positive_before'], value['positive_after']
        for row in (first, last):
            require(type(row['exit_code']) is int and row['exit_code'] == 0)
            require(row['argv'][-6:] == tail)
            require(row['argv'][:6] == ['docker', 'run', '--rm', '--network', 'bridge', '--read-only'])
            for name in ('stdout', 'stderr'): stream(row[name])
        require(first['argv'] == last['argv'])
        isolated = value['isolated']
        require(type(isolated['exit_code']) is int and isolated['exit_code'] == 42)
        require(isolated['timed_out'] is False and type(isolated['duration_ms']) is int and isolated['duration_ms'] >= 0)
        for name in ('stdout', 'stderr'): stream(isolated[name])
        evidence = isolated['evidence']
        require(hashlib.sha256(canonical(evidence)).hexdigest() == isolated['evidence_sha256'])
        require(evidence['backend'] == 'oci-docker' and evidence['assurance'] == 'enforced' and evidence['enforced'] is True)
        require(evidence['network_mode'] == 'none' and evidence['image'] == value['image'])
        require(evidence['command'] == tail[1:])
        for key in ('read_only_root', 'workspace_read_only', 'cap_drop_all', 'no_new_privileges'):
            require(evidence[key] is True)
        require(re.fullmatch('[0-9a-f]{64}', evidence['runtime_binary_sha256']) is not None)
        plan = {k: v for k, v in evidence.items() if k not in ('content_sha256', 'runtime_binary_sha256', 'enforced')}
        require(hashlib.sha256(canonical(plan)).hexdigest() == evidence['content_sha256'])
        return True
    except (KeyError, TypeError, ValueError, IndexError):
        raise ValueError('p5-network-evidence-invalid') from None


def retain(before, result, after, policy, code, gateway, port):
    def positive(completed):
        return dict(argv=list(completed.args), exit_code=completed.returncode,
                    stdout=capture(completed.stdout), stderr=capture(completed.stderr))
    value = dict(schema='p5-retained-oci-network/1',
        scope='OCI component denial; controller receipt remains unmeasured',
        production_controller_receipt=False, policy_sha256=policy.content_sha256,
        image=policy.image_reference, probe_code=code, probe_sha256=hashlib.sha256(code.encode()).hexdigest(),
        gateway=gateway, port=port, positive_before=positive(before), positive_after=positive(after),
        isolated=dict(exit_code=result.exit_code, timed_out=result.timed_out, duration_ms=result.duration_ms,
                      stdout=capture(result.stdout), stderr=capture(result.stderr), evidence=result.evidence,
                      evidence_sha256=hashlib.sha256(canonical(result.evidence)).hexdigest()))
    validate(value)
    return value


class NetworkControlTimeout(TimeoutError):
    """Public stage label only; never retain command, output or exception text."""

    def __init__(self, stage):
        if stage not in ('positive-before', 'positive-after'):
            raise ValueError('p5-network-timeout-stage')
        self.stage = stage
        super().__init__('p5-network-positive-control-timeout')


def run_positive_control(stage, argv):
    # Same command, timeout and pass criteria; no retry after an ambiguous timeout.
    import subprocess
    if stage not in ('positive-before', 'positive-after'):
        raise ValueError('p5-network-timeout-stage')
    try:
        return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30, check=False)
    except subprocess.TimeoutExpired:
        raise NetworkControlTimeout(stage) from None


def timeout_diagnostic(error):
    if type(error) is not NetworkControlTimeout:
        return None
    if error.stage not in ('positive-before', 'positive-after'):
        return None
    return dict(schema='p5-network-timeout-diagnostic/1', stage=error.stage,
                timeout_seconds=30, accepted_drill_result=False)
