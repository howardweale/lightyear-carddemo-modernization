"""CI-only real OCI negative probe; fixture data, no models or signing."""
import json
import os
from pathlib import Path
import tempfile
from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.contracts import ExecutionPolicy
from lightyear_factory.contracts import GateContract
from lightyear_factory.gates import GateRunner


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('CI-only container probe')
    root = Path(__file__).resolve().parents[2]
    policy = ExecutionPolicy.load(root/'factory/execution/policy.json')
    with tempfile.TemporaryDirectory() as d:
        fixture = Path(d); workspace = fixture/'workspace'; workspace.mkdir()
        private = fixture/'expected-state.txt'; private.write_text('private-fixture-value-never-mounted')
        (workspace/'build.py').write_text(
            "from pathlib import Path\n"
            "assert str(Path.cwd()) == '/tmp/factory-build'\n"
            "Path('build-output.txt').write_text('built only inside container')\n"
            "print('fixture build passed')\n")
        (workspace/'attack.py').write_text(
            "import sys\nfrom pathlib import Path\n"
            "try: data = Path(sys.argv[1]).read_text()\n"
            "except OSError:\n    print('isolation-breach: expected-state access denied')\n    raise SystemExit(86)\n"
            "print(data)\n")
        runner = GateRunner(workspace, backend=OCIContainerBackend(policy, 'docker', execute=True), require_container=True)
        def gate(name, command):
            return GateContract.from_dict(dict(id=name, command=command, timeout_seconds=60,
                                               expose_output_to_builder=False))
        build = runner.run((gate('build', ['python3', 'build.py']),))
        assert build['status'] == 'passed', build
        assert not (workspace/'build-output.txt').exists(), 'candidate modified host workspace'
        denied = runner.run((gate('excluded-read', ['python3', 'attack.py', str(private)]),))
        row = denied['gates'][0]
        assert denied['status'] == 'failed' and row['exit_code'] == 86, denied
        assert 'isolation-breach: expected-state access denied' in row['stdout'], denied
        assert 'private-fixture-value-never-mounted' not in json.dumps(denied)
        for result in (build, denied):
            evidence = result['gates'][0]['execution']
            assert evidence['enforced'] is True and evidence['network_mode'] == 'none'
            assert evidence['workspace_read_only'] is True and evidence['candidate_build_root'] == '/tmp/factory-build'
        print(json.dumps(dict(receipt_type='factory-container-negative-probe/1', status='passed',
                              build=build, excluded_read=denied, production_ready=False)))


if __name__ == '__main__':
    main()
