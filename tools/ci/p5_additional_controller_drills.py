"""CI-only, keyless controller observations; failed expectations retain original bytes."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading

from lightyear_execution.contracts import ExecutionPolicy
from lightyear_factory.contracts import canonical_hash
from tools.ci import p5_controller_network as network_probe
from tools.ci import p5_terminal_deadline as deadline_probe


SOURCES = (
    'tools/ci/p5_workspace_replacement.py',
    'tests/test_p5_workspace_replacement.py',
    'tests/test_p5_additional_collection.py',
    'src/lightyear_factory/contracts.py',
    'tests/test_p5_deadline_retention.py',
    'tools/ci/p5_drills.py',
    'tools/ci/p5_additional_controller_drills.py',
    'tools/ci/p5_controller_network.py', 'tools/ci/p5_terminal_deadline.py',
    'tests/test_p5_controller_network_keyless.py', 'tests/test_p5_terminal_deadline.py',
    'src/lightyear_factory/orchestrator.py', 'src/lightyear_factory/gates.py',
    'src/lightyear_factory/providers.py', 'src/lightyear_factory/agents.py',
    'src/lightyear_factory/budgeted_providers.py', 'src/lightyear_factory/ledger.py',
    'src/lightyear_factory/workspace.py',
    'src/lightyear_execution/backend.py', 'factory/execution/policy.json',
)


def encoded(raw):
    return dict(base64=base64.b64encode(raw).decode('ascii'),
                sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def retain_control(result):
    return dict(argv=result.args, exit_code=result.returncode,
                stdout=encoded(result.stdout), stderr=encoded(result.stderr))


def deadline_valid(value):
    """Original receipt and ledger must bind the clock experiment and expected outcome."""
    try:
        if type(value['expired']) is not bool:
            return False
        receipt_raw = value['receipt_utf8'].encode()
        ledger_raw = value['ledger_utf8'].encode()
        if hashlib.sha256(receipt_raw).hexdigest() != value['receipt_sha256']:
            return False
        if hashlib.sha256(ledger_raw).hexdigest() != value['ledger_sha256']:
            return False
        receipt = json.loads(receipt_raw)
        if receipt['content_sha256'] != canonical_hash(receipt, {'content_sha256'}):
            return False
        if receipt['run_id'] != 'p5-terminal-deadline' or value['production_controller_receipt'] is not False:
            return False
        if receipt['execution_security']['production_ready'] is not False:
            return False
        if receipt['work_order_sha256'] != value['work_order_sha256']:
            return False
        if value['source_before_sha256'] != value['source_after_sha256']:
            return False
        refs = receipt['artifacts']; retained = value['artifacts']; reports = []
        if len(refs) != len(retained):
            return False
        for ref, artifact in zip(refs, retained):
            raw = artifact['utf8'].encode('utf-8')
            if ref['path'] != artifact['path'] or hashlib.sha256(raw).hexdigest() != artifact['sha256']:
                return False
            envelope = json.loads(raw)
            if envelope['content_sha256'] != canonical_hash(envelope, {'content_sha256'}):
                return False
            if envelope['content_sha256'] != ref['content_sha256'] or envelope['artifact_type'] != ref['artifact_type']:
                return False
            if envelope['run_id'] != receipt['run_id']:
                return False
            if envelope['artifact_type'] == 'verification-report':
                reports.append(envelope['content'])
        if reports != value['gate_reports']:
            return False
        events = [json.loads(line) for line in ledger_raw.splitlines()]
        previous = None
        for sequence, event in enumerate(events, 1):
            if event['sequence'] != sequence or event['previous_sha256'] != previous:
                return False
            if event['event_sha256'] != canonical_hash(event, {'event_sha256'}):
                return False
            previous = event['event_sha256']
        if previous != receipt['ledger_head_sha256'] or len(events) != receipt['event_count']:
            return False
        if value['scripted_roles'] != ['planner'] or len(value['gate_reports']) != 1:
            return False
        gate = value['gate_reports'][0]['gates'][0]
        if gate['status'] != 'passed' or gate['exit_code'] != 0 or gate['timed_out'] is not False:
            return False
        if value['expired']:
            return (value['clock_delta'] > value['wall_seconds'] and receipt['status'] == 'blocked'
                    and value['error'] == 'Factory exceeded max_elapsed_seconds')
        return value['clock_delta'] == 0 and receipt['status'] == 'passed' and value['error'] is None
    except (KeyError, ValueError, TypeError, IndexError):
        return False



def network_controls_valid(value, policy):
    """Bind both real connectivity controls to the exact isolated gate experiment."""
    try:
        controller = value['controller']
        if not network_probe.validate(controller):
            return False
        command = controller['command']
        if (not isinstance(command, list) or len(command) != 5
                or command[:2] != ['python3', '-c']
                or not all(isinstance(part, str) for part in command)):
            return False
        expected = ['docker', 'run', '--rm', '--network', 'bridge', '--read-only',
                    '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                    '--user', policy.run_as_user, policy.image_reference, *command]
        for name in ('positive_before', 'positive_after'):
            row = value[name]
            if type(row['exit_code']) is not int or row['exit_code'] != 0 or row['argv'] != expected:
                return False
            for stream_name in ('stdout', 'stderr'):
                stream = row[stream_name]
                raw = base64.b64decode(stream['base64'], validate=True)
                if (type(stream['bytes']) is not int or len(raw) != stream['bytes']
                        or hashlib.sha256(raw).hexdigest() != stream['sha256']):
                    return False
        reports = [json.loads(item['utf8']) for item in controller['artifacts']
                   if json.loads(item['utf8'])['artifact_type'] == 'verification-report']
        if len(reports) != 1:
            return False
        execution = reports[0]['content']['gates'][0]['execution']
        return execution['image'] == policy.image_reference and execution['network_mode'] == 'none'
    except (KeyError, ValueError, TypeError, IndexError, AttributeError):
        return False

def network_case(parent, policy):
    class Probe(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.sendall(b'P5-REACHABLE')
    server = socketserver.ThreadingTCPServer(('0.0.0.0', 0), Probe)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    observed = dict(scope='real scripted controller and OCI candidate gate; no admission or signing',
                    production_controller_receipt=False, expectation_met=False)
    try:
        bridge = json.loads(subprocess.check_output(['docker', 'network', 'inspect', 'bridge'], timeout=15))
        gateway = bridge[0]['IPAM']['Config'][0]['Gateway']
        port = str(server.server_address[1])
        code = ("import socket,sys\ntry:\n s=socket.create_connection((sys.argv[1],int(sys.argv[2])),2)\n"
                " data=s.recv(32);s.close();sys.exit(0 if data==b'P5-REACHABLE' else 43)\n"
                "except OSError:sys.exit(42)\n")
        command = ('python3', '-c', code, gateway, port)
        control = ['docker', 'run', '--rm', '--network', 'bridge', '--read-only',
                   '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                   '--user', policy.run_as_user, policy.image_reference, *command]
        before = subprocess.run(control, capture_output=True, timeout=30, check=False)
        observed['positive_before'] = retain_control(before)
        # Even a failed positive control must not be relabelled as proof of network denial.
        try:
            observed['controller'] = network_probe.observe(parent/'controller', policy, command)
        finally:
            after = subprocess.run(control, capture_output=True, timeout=30, check=False)
            observed['positive_after'] = retain_control(after)
        try:
            valid = network_probe.validate(observed['controller'])
        except ValueError as exc:
            valid = False
            observed['validation_error'] = str(exc)
        observed['expectation_met'] = valid and before.returncode == 0 and after.returncode == 0 and network_controls_valid(observed, policy)
    except Exception as exc:
        observed['harness_error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    return observed


def collect(repository, output):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or output.exists():
        raise ValueError('p5-additional-ci-exclusive-output')
    output.mkdir(parents=True)
    report = dict(schema='p5-additional-controller-observations/1',
        commit=os.environ.get('GITHUB_SHA'), run_id=os.environ.get('GITHUB_RUN_ID'),
        production_controller_receipt=False, real_model_calls=0, signing=False,
        source_sha256={path: hashlib.sha256((repository/path).read_bytes()).hexdigest() for path in SOURCES},
        cases=[], strict_qualified=False,
        gaps=['Tower append transport/fallback contract unidentified.',
              'Signed admission, full production receipt and reservation accounting are unproved.'])
    with tempfile.TemporaryDirectory(prefix='p5-keyless-additional-') as temp:
        parent = Path(temp)
        policy = ExecutionPolicy.load(repository/'factory/execution/policy.json')
        report['cases'].append(dict(id='controller-worker-network', **network_case(parent, policy)))
        for expired in (False, True):
            row = dict(id='terminal-deadline-expired' if expired else 'terminal-deadline-clean', expectation_met=False)
            try:
                row['observed'] = deadline_probe.observe(parent/row['id'], expired)
                row['expectation_met'] = deadline_valid(row['observed'])
            except Exception as exc:
                row['harness_error'] = type(exc).__name__ + ': ' + str(exc)
            report['cases'].append(row)
        # Additional native-controller observations retain all original bytes.
        # They do not replace any existing row or change strict qualification.
        from tools.ci import p5_workspace_replacement as workspace_probe
        for case in workspace_probe.CASES:
            row = dict(id='controller-workspace-'+case, expectation_met=False)
            try:
                row['observed'] = workspace_probe.observe_controller_case(parent/row['id'], case)
                row['expectation_met'] = workspace_probe.validate_controller_case(row['observed'])
            except Exception as exc:
                row['harness_error'] = type(exc).__name__ + ': ' + str(exc)
            report['cases'].append(row)
        # Preserve every generated public JSON/ledger document even after an early defect.
        report['original_documents'] = {path.relative_to(parent).as_posix(): encoded(path.read_bytes())
            for path in sorted(parent.rglob('*')) if path.is_file() and path.suffix in ('.json', '.jsonl')}
    report['expectations_met'] = all(row['expectation_met'] for row in report['cases'])
    report['content_sha256'] = canonical_hash(report)
    (output/'observations.json').write_text(json.dumps(report, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    return report['expectations_met']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    raise SystemExit(0 if collect(Path(__file__).resolve().parents[2], arguments.output) else 1)
