"""CI-only workflow text checks; no workflow, proof or execution authority."""
import ast,os,unittest
from pathlib import Path
from tools.ci.p5_configured_receipt_inputs import _review_workflow_entry

class PackWorkflowBindingTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.raw=b'jobs:\n  configured-build-control:\n    steps:\n      - run: |\n          python -B -m tools.ci.p5_configured_receipt_supervisor --source-root "$GITHUB_WORKSPACE" \\\n            --execution-runtime docker\n'
    def test_fixed_supervisor_entry_has_no_returned_authority(self):
        self.assertIsNone(_review_workflow_entry(self.raw,'configured-build-control'))
    def test_legacy_direct_positive_entry_refuses(self):
        with self.assertRaisesRegex(ValueError,'reviewed-workflow-job'):
            _review_workflow_entry(self.raw.replace(b'receipt_supervisor',b'receipt_positive'),'configured-build-control')
    def test_supervisor_mention_in_comment_does_not_count(self):
        with self.assertRaises(ValueError):
            _review_workflow_entry(self.raw.replace(b'          python',b'          # python'),'configured-build-control')
    def test_duplicate_supervisor_command_refuses(self):
        with self.assertRaises(ValueError):
            _review_workflow_entry(self.raw+b'          python -B -m tools.ci.p5_configured_receipt_supervisor --other\n','configured-build-control')
    def test_changed_or_duplicate_job_header_refuses(self):
        for raw in (self.raw.replace(b'  configured-build-control:',b'  other:'),self.raw+b'  configured-build-control:\n'):
            with self.assertRaises(ValueError):_review_workflow_entry(raw,'configured-build-control')
    def test_nonbytes_wrong_job_and_lookalike_module_refuse(self):
        for raw,job in ((self.raw.decode(),'configured-build-control'),(self.raw,'other'),(self.raw.replace(b'receipt_supervisor',b'receipt_supervisor_fake'),'configured-build-control')):
            with self.assertRaises(ValueError):_review_workflow_entry(raw,job)
    def test_direct_positive_command_cannot_coexist(self):
        with self.assertRaises(ValueError):
            _review_workflow_entry(self.raw+b'          python -B -m tools.ci.p5_configured_receipt_positive --other\n','configured-build-control')
    def test_original_supervisor_launches_positive_once_without_override(self):
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'tools/ci/p5_configured_receipt_supervisor.py').read_bytes())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_launch_and_wait']
        self.assertEqual(len(calls),1)
        command=calls[0].args[0];self.assertIsInstance(command,ast.List)
        self.assertEqual([n.value for n in command.elts if isinstance(n,ast.Constant)],['-B','-m','tools.ci.p5_configured_receipt_positive'])
        self.assertIsInstance(command.elts[-1],ast.Starred)
