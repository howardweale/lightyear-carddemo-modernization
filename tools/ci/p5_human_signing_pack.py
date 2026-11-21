"""CI-only unsigned public signing pack; no proof, signer, import or execution."""
import argparse
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess

DOCUMENTS = 'docs/factory/p5-human-clean-control/'
FIXTURES = 'tests/fixtures/p5_public/human-clean-control/'
WORKFLOW = '.github/workflows/p5-human-clean-control.yml'
REPOSITORY = 'howardweale/lightyear-carddemo-modernization'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def build_unsigned_documents(order, policy, executable, bound, outputs, isolation,
                             observer_hash, worker_hash, window, nonce_sha256):
    """Pure draft construction and native contract validation, never approval."""
    from lightyear_factory.contracts import canonical_hash
    from lightyear_control_tower.factory_policy import validate_contract
    from lightyear_execution.public_drill_outputs import require_public_contract_source
    require(re.fullmatch('[0-9a-f]{40}', executable) is not None, 'signing-pack-executable')
    require(re.fullmatch('[0-9a-f]{64}', nonce_sha256) is not None, 'signing-pack-nonce')
    require(type(window) is dict and set(window) == {'start', 'end'}, 'signing-pack-window')
    start, end = (datetime.fromisoformat(window[k]) for k in ('start', 'end'))
    require(start.tzinfo is not None and end.tzinfo is not None
            and 0 < (end-start).total_seconds() <= policy.max_work_order_ttl_seconds,
            'signing-pack-window')
    require(order.order_id == 'human-clean-control' and order.baseline_first
            and order.max_attempts == 1 and order.max_model_calls == 1
            and not order.allow_network and not policy.allowed_secret_names
            and policy.signature_algorithm == 'FACTORY-TOWER-PROOF', 'signing-pack-clean-scope')
    names = {'scope', 'freeze', 'workspace', 'execution_policy'}
    require(type(bound) is dict and set(bound) == names, 'signing-pack-input-set')
    filenames = {'scope': 'scope.json', 'freeze': 'freeze.json', 'workspace': 'workspace.json',
                 'execution_policy': 'execution-policy.json'}
    for name, row in bound.items():
        require(type(row) is dict and set(row) == {'path', 'sha256'}
                and row['path'] == DOCUMENTS+filenames[name]
                and re.fullmatch('[0-9a-f]{64}', row['sha256']) is not None, 'signing-pack-input')
    for row, name in ((outputs, 'public-outputs.json'), (isolation, 'public-isolation.json')):
        require(type(row) is dict and set(row) == {'path', 'sha256'}
                and row['path'] == DOCUMENTS+name
                and re.fullmatch('[0-9a-f]{64}', row['sha256']) is not None, 'signing-pack-public-input')
    caps = dict(max_attempts=1, max_repair_loops=1, max_elapsed_seconds=order.max_elapsed_seconds,
                max_model_calls=1, max_model_tokens=order.max_model_tokens,
                cost_cap_microusd=int(order.max_model_cost_usd*1000000))
    require(caps['cost_cap_microusd']/1000000 == order.max_model_cost_usd, 'signing-pack-exact-cap')
    plan = dict(schema='factory-build-plan/1', work_order_sha256=order.content_sha256,
        executable_commit=executable, caps=caps, bound_inputs=bound,
        roles={role: dict(provider='p5-scripted', model='p5-stub-2026-10-28')
               for role in ('planner', 'builder', 'analyst')},
        public_drill_outputs=outputs, public_drill_isolation=isolation,
        drill_admission=dict(schema='factory-human-drill-admission/1', case_id='human-clean-control',
            nonce_sha256=nonce_sha256, work_order_sha256=order.content_sha256,
            execution_policy_sha256=policy.content_sha256,
            role_actions={role: list(actions) for role, actions in policy.role_actions.items()},
            ci=dict(repository=REPOSITORY, workflow_ref=REPOSITORY+'/'+WORKFLOW+'@'+executable,
                    job='human-clean-control', run_attempt=1),
            stub_only=True, external_model_calls=0, max_attempts=1))
    plan['content_sha256'] = canonical_hash(plan)
    contract = dict(schema='factory-contract/1', kind='engineering-run-approval', program='factory',
        sources=[dict(row, commit=executable) for row in [*bound.values(), outputs, isolation]],
        details=dict(executable_commit=executable, request_seal=plan['content_sha256'],
            observer_sha256=observer_hash, class_hashes={'PublicArithmeticWorker': worker_hash},
            window=window, caps=caps))
    validate_contract(contract, check_evidence=False)
    require_public_contract_source(contract, outputs)
    require_public_contract_source(contract, isolation)
    return plan, contract


def prepare(root, executable, window, nonce_sha256):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'signing-pack-ci-only')
    from lightyear_factory.contracts import WorkOrder
    from lightyear_execution.contracts import ExecutionPolicy
    from lightyear_control_tower.decisions import canonical
    from tools.ci.p5_human_case_inputs import prepare as prepare_inputs
    root = Path(root).resolve(strict=True)
    command = ['git', '--no-optional-locks', '-C', str(root)]
    def git(*args): return subprocess.check_output(command+list(args))
    require(re.fullmatch('[0-9a-f]{40}', executable) is not None
            and git('rev-parse', 'HEAD').decode().strip() == executable
            and not git('status', '--porcelain=v1', '--untracked-files=all'), 'signing-pack-clean-executable')
    def committed(relative):
        path = root / relative
        require(path.is_file() and path.stat().st_nlink == 1 and path.stat().st_size <= 1048576
                and all(not p.is_symlink() and not getattr(p, 'is_junction', lambda: False)()
                        for p in (path, *path.parents)), 'signing-pack-regular-input')
        raw = path.read_bytes()
        require(len(raw) <= 1048576 and raw == git('show', executable+':'+relative), 'signing-pack-committed-input')
        return raw
    generated = prepare_inputs(root)  # Native formatter only; never a provider call.
    for name in ('public-outputs.json', 'public-isolation.json'):
        expected = json.dumps(generated[name], sort_keys=True, separators=(',', ':')).encode()+b'\n'
        require(committed(DOCUMENTS+name) == expected, 'signing-pack-generated-input-mismatch')
    order = WorkOrder.from_dict(json.loads(committed(FIXTURES+'work-order.json')))
    policy = ExecutionPolicy.from_dict(json.loads(committed(DOCUMENTS+'execution-policy.json')))
    committed(WORKFLOW)
    def binding(relative): return dict(path=relative, sha256=sha256(committed(relative)).hexdigest())
    bound = {name: binding(DOCUMENTS+file) for name, file in
             [('scope','scope.json'),('freeze','freeze.json'),('workspace','workspace.json'),('execution_policy','execution-policy.json')]}
    plan, contract = build_unsigned_documents(order, policy, executable, bound,
        binding(DOCUMENTS+'public-outputs.json'), binding(DOCUMENTS+'public-isolation.json'),
        sha256(committed('tools/ci/p5_human_positive.py')).hexdigest(),
        sha256(committed(FIXTURES+'worker.py')).hexdigest(), window, nonce_sha256)
    require(not git('status', '--porcelain=v1', '--untracked-files=all')
            and git('rev-parse', 'HEAD').decode().strip() == executable, 'signing-pack-source-changed')
    return {'plan.json': canonical(plan), 'contract.json': canonical(contract)}


def main(argv=None):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'signing-pack-ci-only')
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--executable', required=True)
    parser.add_argument('--window-start', required=True)
    parser.add_argument('--window-end', required=True)
    parser.add_argument('--nonce-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    target = args.output
    require(target.is_absolute() and not target.exists() and target.parent.is_dir()
            and not target.resolve().is_relative_to(args.source_root.resolve())
            and all(not p.is_symlink() and not getattr(p, 'is_junction', lambda: False)()
                    for p in (target, *target.parents)), 'signing-pack-new-external-output')
    files = prepare(args.source_root, args.executable,
                    {'start': args.window_start, 'end': args.window_end}, args.nonce_sha256)
    target.mkdir()
    for name, raw in files.items():
        with (target/name).open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps(dict(status='unsigned-signing-proposal', files={k:sha256(v).hexdigest() for k,v in files.items()},
        proof_created=False, signatures_created=0, nonce_consumed=False, execution_authorized=False)))
    return 0


if __name__ == '__main__': raise SystemExit(main())
