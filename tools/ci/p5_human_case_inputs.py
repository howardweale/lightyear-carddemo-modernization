"""CI-only unsigned public-case input preparation, never execution admission.

Capture the native planner formatter before provider dispatch. No controller,
transport, OCI process, signer, consumption API or genuine proof is invoked.
The resulting proposal must be committed and bound before Howard signs a plan.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path

CASE = 'human-clean-control'
PREFIX = 'tests/fixtures/p5_public/' + CASE + '/'
DOCUMENTS = 'docs/factory/p5-human-clean-control/'
WORKER = PREFIX + 'worker.py'
WORKER_BYTES = b'def add(left, right):\n    return left + right\n\n\nif __name__ == "__main__":\n    assert add(19, 23) == 42\n    print("public-clean-control-passed")\n'


def require(value, message):
    if not value:
        raise ValueError(message)


def prepare(root):
    """Return unsigned data only; imports/calls are permitted in CI, not locally."""
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'public-case-ci-only')
    from lightyear_factory.agents import ModelAgentSet
    from lightyear_factory.context import GraphContextAssembler
    from lightyear_factory.contracts import WorkOrder, canonical_hash
    from lightyear_factory.providers import _validate_schema
    from lightyear_execution.contracts import ExecutionPolicy
    from lightyear_execution.public_drill_outputs import validate_public_output_plan
    root = Path(root).resolve(strict=True)

    def read(relative):
        path = root / relative
        require(not path.is_symlink() and path.is_file(), 'public-case-regular-input')
        require(all(not p.is_symlink() and not getattr(p, 'is_junction', lambda: False)()
                    for p in (path, *path.parents)), 'public-case-input-link')
        require(path.stat().st_size <= 65536, 'public-case-input-size')
        raw = path.read_bytes()
        require(len(raw) <= 65536, 'public-case-input-size')
        return raw

    require(read(WORKER) == WORKER_BYTES, 'public-case-exact-worker')
    order = WorkOrder.from_dict(json.loads(read(PREFIX + 'work-order.json')))
    policy = ExecutionPolicy.from_dict(json.loads(read(DOCUMENTS + 'execution-policy.json')))
    manifest = json.loads(read(DOCUMENTS + 'workspace.json'))
    require(manifest == {WORKER: sha256(WORKER_BYTES).hexdigest()}, 'public-case-exact-workspace')
    require(order.allowed_paths == (WORKER,) and order.graph_node_ids == ()
            and order.baseline_first is True and order.max_attempts == 1
            and order.allow_network is False and order.max_model_calls == 1
            and order.metadata == {'context_schema': '1.0', 'graph': 'packed'},
            'public-case-order-scope')
    require(len(order.gates) == 1 and order.gates[0].command == ('python3', WORKER)
            and order.gates[0].expose_output_to_builder is False,
            'public-case-exact-gate')
    require(policy.signature_algorithm == 'FACTORY-TOWER-PROOF'
            and not policy.allowed_secret_names, 'public-case-human-policy')
    context = GraphContextAssembler(None, None).assemble(order, root)
    response = dict(summary='Verify the unchanged public arithmetic fixture.', tasks=[dict(
        id='verify-public-baseline', objective=order.goal, paths=[WORKER],
        graph_node_ids=[], evidence_capsule_ids=[])], risks=[
        'This public clean control does not establish COPAU or production qualification.'])

    class FormatOnly(ModelAgentSet):
        def __init__(self):
            super().__init__(None)
            self.requests = []

        def _call(self, current_order, role, instruction, payload, schema):
            require(current_order is order and role == 'planner' and not self.requests,
                    'public-case-one-planner-format')
            _validate_schema(response, schema, 'public-case-planner-response')
            self.requests.append(deepcopy(dict(instruction=instruction, payload=payload, schema=schema)))
            return deepcopy(response)

    formatter = FormatOnly()
    require(formatter.plan(order, context) == response and len(formatter.requests) == 1,
            'public-case-planner-format')
    invocation = formatter.requests[0]
    script = dict(schema='factory-public-drill-outputs/1', case_id=CASE,
        work_order_sha256=order.content_sha256, provider='p5-scripted', model='p5-stub-2026-10-28',
        steps=[dict(sequence=1, role='planner', invocation_sha256=canonical_hash(invocation),
                    schema_sha256=canonical_hash(invocation['schema']), response_content=response,
                    response_sha256=canonical_hash({'content': response}))])
    script['content_sha256'] = canonical_hash(script)
    validate_public_output_plan(script, order.content_sha256, CASE)
    isolation = dict(schema='factory-public-drill-isolation/1', case_id=CASE,
        work_order_sha256=order.content_sha256, values=[
            'PUBLIC synthetic isolation canary alpha for the human clean control only.',
            'PUBLIC synthetic isolation canary beta for the human clean control only.',
            'PUBLIC synthetic isolation canary gamma for the human clean control only.'])
    isolation['content_sha256'] = canonical_hash(isolation)
    inputs = {name: dict(path=DOCUMENTS + filename, sha256=sha256(read(DOCUMENTS + filename)).hexdigest())
              for name, filename in [('scope', 'scope.json'), ('freeze', 'freeze.json'),
                                     ('workspace', 'workspace.json'), ('execution_policy', 'execution-policy.json')]}
    result = dict(schema='factory-public-case-input-proposal/1', case_id=CASE,
        work_order_sha256=order.content_sha256, execution_policy_sha256=policy.content_sha256,
        bound_inputs=inputs, execution_authorized=False, signature_created=False,
        nonce_consumed=False, provider_calls=0, controller_executed=False,
        status='unsigned-inputs-only', missing=['approved-executable', 'reviewed-ci-workflow',
            'window-and-nonce', 'sealed-plan-and-contract', 'genuine-human-public-proof',
            'independent-current-trust', 'positive-ci-execution'])
    result['content_sha256'] = canonical_hash(result)
    return {'planner-request.json': invocation, 'public-outputs.json': script,
            'public-isolation.json': isolation, 'input-proposal.json': result}


def main(argv=None):
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'public-case-ci-only')
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.source_root.resolve(strict=True)
    target = args.output
    require(target.is_absolute() and not target.exists() and target.parent.is_dir()
            and not target.resolve().is_relative_to(root), 'public-case-new-external-output')
    require(all(not p.is_symlink() and not getattr(p, 'is_junction', lambda: False)()
                for p in (target, *target.parents)), 'public-case-output-link')
    values = prepare(root)
    target.mkdir()
    for name, value in values.items():
        with (target / name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
