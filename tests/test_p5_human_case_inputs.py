"""Unsigned input-compiler tests; none can substitute for a signed CI pilot."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.ci.p5_human_case_inputs import CASE, PREFIX, DOCUMENTS, WORKER, WORKER_BYTES, prepare, main


class PublicHumanCaseInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        source = Path(__file__).resolve().parents[1] / PREFIX
        shutil.copytree(source, self.root / PREFIX)
        shutil.copytree(Path(__file__).resolve().parents[1] / DOCUMENTS, self.root / DOCUMENTS)
        self.env = patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_compiler_has_no_provider_or_process_execution(self):
        with (patch('subprocess.run', side_effect=AssertionError('no process')),
             patch('subprocess.check_output', side_effect=AssertionError('no process')),
             patch('lightyear_factory.agents.ModelAgentSet._provider_for', side_effect=AssertionError('no provider'))):
            result = prepare(self.root)
        proposal = result['input-proposal.json']
        self.assertEqual(proposal['status'], 'unsigned-inputs-only')
        self.assertFalse(proposal['execution_authorized'])
        self.assertFalse(proposal['signature_created'])
        self.assertFalse(proposal['nonce_consumed'])
        self.assertFalse(proposal['controller_executed'])
        self.assertEqual(proposal['provider_calls'], 0)
        self.assertIn('genuine-human-public-proof', proposal['missing'])

    def test_native_formatter_and_output_plan_share_exact_request(self):
        from lightyear_factory.contracts import canonical_hash, WorkOrder
        from lightyear_factory.context import GraphContextAssembler
        from lightyear_factory.agents import ModelAgentSet, PLANNER_SCHEMA
        from lightyear_execution.public_drill_runtime import match_invocation
        result = prepare(self.root)
        order = WorkOrder.load(self.root / PREFIX / 'work-order.json')
        agent = ModelAgentSet(None)
        with patch.object(agent, '_call') as capture:
            agent.plan(order, GraphContextAssembler(None, None).assemble(order, self.root))
        current, role, instruction, payload, schema = capture.call_args.args
        self.assertIs(current, order)
        self.assertEqual(role, 'planner')
        self.assertEqual(schema, PLANNER_SCHEMA)
        request = dict(instruction=instruction, payload=payload, schema=schema)
        self.assertEqual(result['planner-request.json'], request)
        step = result['public-outputs.json']['steps'][0]
        self.assertEqual(match_invocation(step, 1, role, instruction, payload, schema), request)
        self.assertEqual(step['invocation_sha256'], canonical_hash(request))
        with self.assertRaisesRegex(ValueError, 'public-drill-unapproved-invocation'):
            match_invocation(step, 1, role, instruction + ' changed', payload, schema)

    def test_refuses_worker_or_manifest_drift(self):
        worker = self.root / WORKER
        worker.write_bytes(WORKER_BYTES + b'# changed\n')
        with self.assertRaisesRegex(ValueError, 'public-case-exact-worker'):
            prepare(self.root)
        worker.write_bytes(WORKER_BYTES)
        (self.root / DOCUMENTS / 'workspace.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'public-case-exact-workspace'):
            prepare(self.root)

    def test_refuses_network_graph_or_more_than_one_call(self):
        path = self.root / PREFIX / 'work-order.json'
        original = path.read_text(encoding='utf-8')
        for section, key, value in [('policy', 'allow_network', True),
                                    ('policy', 'max_model_calls', 2),
                                    ('metadata', 'graph', 'on-demand')]:
            with self.subTest(key=key):
                order = json.loads(original)
                order[section][key] = value
                path.write_text(json.dumps(order), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'public-case-order-scope'):
                    prepare(self.root)
        path.write_text(original, encoding='utf-8')

    def test_only_external_fresh_output_and_no_overwrite(self):
        output = Path(self.temp.name) / 'prepared'
        self.assertEqual(main(['--source-root', str(self.root), '--output', str(output)]), 0)
        self.assertEqual(set(p.name for p in output.iterdir()),
                         {'planner-request.json', 'public-outputs.json', 'public-isolation.json', 'input-proposal.json'})
        with self.assertRaisesRegex(ValueError, 'public-case-new-external-output'):
            main(['--source-root', str(self.root), '--output', str(output)])
        with self.assertRaisesRegex(ValueError, 'public-case-new-external-output'):
            main(['--source-root', str(self.root), '--output', str(self.root / 'output')])

    def test_refuses_outside_ci_before_import_or_file_read(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': ''}):
            with self.assertRaisesRegex(ValueError, 'public-case-ci-only'):
                prepare(Path(self.temp.name) / 'absent')

    def test_deterministic_input_proposals_across_workspace_locations(self):
        second = Path(self.temp.name) / 'second'
        shutil.copytree(self.root, second)
        self.assertEqual(prepare(self.root), prepare(second))


if __name__ == '__main__':
    unittest.main()
