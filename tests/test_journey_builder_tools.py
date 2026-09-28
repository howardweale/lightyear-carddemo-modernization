"""Public builder boundary, durable budgets and real MCP registration."""
import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.journey_builder_mcp import BuilderTools,create_server
from tools.journey_development_tools import PUBLIC,api,structural
from lightyear_calibration.contracts import CalibrationError


class BuilderBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        p=self.root/PUBLIC;p.mkdir(parents=True)
        (p/'operations.json').write_text('{"public":true}')
        (p/'JourneySupport.java').write_text('public class JourneySupport {}')
        config=self.root/'work/ms87/local-runtime.json';config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'runner_image':'sha256:'+'a'*64}))

    def test_public_contract_refuses_path_selection(self):
        b=BuilderTools(self.root)
        with self.assertRaises(CalibrationError):b.public_contract('../../private/judge')
        self.assertEqual({'public':True},b.public_contract('operations'))

    def test_changed_inputs_close_session(self):
        b=BuilderTools(self.root)
        (self.root/PUBLIC/'JourneySupport.java').write_text('changed')
        with self.assertRaises(CalibrationError):b.support()

    def test_tool_failure_consumes_budget_and_records_no_exception_payload(self):
        b=BuilderTools(self.root,1)
        with patch('tools.journey_builder_mcp.compile_candidate',side_effect=RuntimeError('PRIVATE_DATABASE_VALUE')):
            out=b.compile('class Candidate {}')
        self.assertEqual('development-tool-error',out['status'])
        self.assertNotIn('PRIVATE',json.dumps(out))
        self.assertTrue((b.session/'1/invocation.json').exists())
        self.assertEqual(out,json.loads((b.session/'1/receipt.json').read_text()))
        with self.assertRaises(CalibrationError):b.compile('another')

    def test_arbitrary_api_name_cannot_read_paths(self):
        with self.assertRaises(CalibrationError):api(self.root,'../../judge')

    def test_server_restart_cannot_reset_compile_budget(self):
        first=BuilderTools(self.root,1,'persistent-test')
        with patch('tools.journey_builder_mcp.compile_candidate',return_value={'status':'compile-failed'}):
            first.compile('source')
        restarted=BuilderTools(self.root,1,'persistent-test')
        with self.assertRaises(CalibrationError):restarted.compile('again')
        with self.assertRaises(CalibrationError):BuilderTools(self.root,2,'persistent-test')

    def test_process_network_and_private_path_requests_rejected(self):
        prefix='class LightyearOperationsTest extends AbstractTestCase '
        for forbidden in ('ProcessBuilder','Runtime.getRuntime','java.net.','/verifier/','System.getenv'):
            self.assertFalse(structural(prefix+forbidden)['passed'])


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'Install the agent extra for MCP transport tests')
class Registration(unittest.IsolatedAsyncioTestCase):
    async def test_only_public_tools_registered(self):
        with patch('tools.journey_builder_mcp.BuilderTools'):
            server=create_server(Path('.'))
            listed=await server.list_tools()
        self.assertEqual({'public_contract','public_api','deterministic_support','check_structure','compile_candidate_source'},
                         {tool.name for tool in listed})


if __name__=='__main__':unittest.main()
