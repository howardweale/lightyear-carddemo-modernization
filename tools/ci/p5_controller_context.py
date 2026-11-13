"""CI-only context contamination at the real assembler's disposable file input."""
import base64
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from lightyear_execution.backend import OCIContainerBackend
from lightyear_execution.integration import HardenedExecutionContext
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.budgeted_providers import AccountedModelProvider
from lightyear_factory.context import GraphContextAssembler
from lightyear_factory.contracts import ContractError
from lightyear_factory import isolation_scan
from lightyear_factory.orchestrator import FactoryOrchestrator
from tools.ci.p5_budget_evidence import retain as retain_budget
from tools.ci.p5_context_evidence import CASES, ORIGIN, validate
from tools.ci.p5_controller_budgets import BudgetStub
from tools.ci.p5_fixture import Fixture


def observe_case(parent, repository, case):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or case not in CASES:
        raise ValueError('p5-context-ci-only')
    parent = Path(parent)
    parent.mkdir()
    fixture = Fixture(parent, repository, controller_probe=True)
    try:
        digest = lambda raw: hashlib.sha256(raw).hexdigest()
        stub = BudgetStub('control', fixture.order)
        agents = ModelAgentSet(stub)
        _, admission = fixture.verify_order()
        context = HardenedExecutionContext(fixture.policy,
            OCIContainerBackend(fixture.policy, 'docker', execute=False), admission, fixture.key)
        runs = parent/'runs'
        run_id = 'p5-context-'+case
        controller = FactoryOrchestrator(fixture.root, runs, agents,
            execution_context=context, model_admission=fixture.admission,
            factory_input_paths=fixture.input_paths,
            workspace_read_manifest=fixture.runtime()['workspace_read_manifest'],
            private_expected_values_path=fixture.private_values_path)
        source_before = (fixture.root/'worker.py').read_bytes()
        scans, assembly = [], {}
        real_scan, real_assemble = isolation_scan.scan, GraphContextAssembler.assemble

        def recording_scan(artifacts, canaries, expected_values):
            artifacts = list(artifacts)
            # This wrapper observes the real scanner and forwards results/errors unchanged.
            rows = [dict(surface=name, sha256=digest(raw if isinstance(raw, bytes) else raw.encode()),
                         outcome='passed') for name, raw in artifacts]
            try:
                result = real_scan(artifacts, canaries, expected_values)
            except ContractError as error:
                if str(error) == 'isolation-breach':
                    scans.extend(dict(row, outcome='isolation-breach') for row in rows)
                raise
            scans.extend(rows)
            return result

        def contaminated_input(assembler, order, workspace_root):
            target = workspace_root/'worker.py'
            if assembly or target.resolve() == (fixture.root/'worker.py').resolve():
                raise ValueError('p5-context-injection-boundary')
            before = target.read_bytes()
            if before != source_before or not any(row == dict(surface='initial-workspace-file',
                    sha256=digest(before), outcome='passed') for row in scans):
                raise ValueError('p5-context-initial-scan-required')
            if case != 'clean':
                # Only this disposable fixture's approved synthetic value is used.
                value = json.loads(fixture.private_values_path.read_bytes())['values'][0]
                planted = (' '.join(value.upper()) if case == 'normalized' else
                           base64.b64encode(value.encode()).decode() if case == 'base64' else value.encode().hex())
                target.write_bytes(('# '+planted+'\n').encode('utf-8'))
            after = target.read_bytes()
            result = real_assemble(assembler, order, workspace_root)
            files = result['allowed_files']
            if len(files) != 1 or files[0]['path'] != 'worker.py' or files[0]['truncated'] is not False:
                raise ValueError('p5-context-real-assembly-file')
            if files[0]['content'].encode('utf-8') != after or files[0]['sha256'] != digest(after):
                raise ValueError('p5-context-real-assembly-bytes')
            assembly.update(injection_boundary='copied worker.py immediately before real assemble',
                source_before_sha256=digest(source_before), workspace_before_sha256=digest(before),
                workspace_after_sha256=digest(after), assembled_file_sha256=files[0]['sha256'],
                context_sha256=digest(json.dumps(result, sort_keys=True, ensure_ascii=False).encode('utf-8')))
            return result

        refused = False
        with patch.object(isolation_scan, 'scan', recording_scan), patch.object(GraphContextAssembler, 'assemble', contaminated_input):
            try:
                controller.run(fixture.order, run_id)
            except ContractError as error:
                if str(error) != 'factory-isolation-run-refused':
                    raise ValueError('p5-context-wrong-controller-refusal') from None
                refused = True
        budget = agents.bounded_provider
        if type(budget) is not AccountedModelProvider or len(budget.calls) != stub.calls:
            raise ValueError('p5-context-accounted-provider-required')
        assembly['source_after_sha256'] = digest((fixture.root/'worker.py').read_bytes())
        value = dict(schema='p5-retained-context-evidence/1', origin=ORIGIN, case=case,
            run_id=run_id, work_order_sha256=fixture.order.content_sha256,
            controller_refused=refused, transport_calls=stub.calls,
            assembly=assembly, scanner_observations=scans)
        directory = runs/run_id
        if case == 'clean':
            value['clean_control'] = retain_budget(directory, budget.calls, case='control',
                run_id=run_id, work_order_sha256=fixture.order.content_sha256)
        else:
            for kind, filename in (('receipt', 'receipt.json'), ('identity', 'attempt-identity.json'), ('ledger', 'events.jsonl')):
                raw = (directory/filename).read_bytes()
                value[kind+'_utf8'], value[kind+'_sha256'] = raw.decode('utf-8'), digest(raw)
        validate(value, case=case, work_order_sha256=fixture.order.content_sha256)
        return value
    finally:
        fixture.close()


def observe(fixture, repository):
    root = fixture.parent/'context-controller-probes'
    root.mkdir()
    return [observe_case(root/case, repository, case) for case in CASES]
