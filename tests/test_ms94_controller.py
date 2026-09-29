import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from lightyear_calibration.contracts import seal,CalibrationError
from tools.ms94_tool_policy import verify_events
from tools.ms94_builder_mcp import transcript,RecordedTools,TOOLS,SERVER
from tools.ms94_measure import decision,interval
from tools.ms94_controller import assemble,stage_a

ROOT=Path(__file__).resolve().parents[1]


class ControllerTests(unittest.TestCase):
    def record(self):
        i=seal({'tool':'public_contract','arguments':{'scenario':'operations'},'ordinal':1,'previous_sha256':None})
        return {'invocation':i,'result':seal({'invocation_sha256':i['content_sha256'],'output':{'contract':'public'}})}

    def event(self):
        return {'type':'item.completed','item':{'id':'tool-1','type':'mcp_tool_call','server':SERVER,
          'tool':'public_contract','arguments':{'scenario':'operations'},'error':None,
          'result':{'content':[{'type':'text','text':'{"contract":"public"}'}]}}}

    def test_tool_arguments_and_outputs_are_part_of_provenance(self):
        e=self.event();r=self.record();self.assertTrue(verify_events([e],'builder',[r])['verified'])
        e['item']['arguments']['scenario']='procure-to-pay'
        with self.assertRaises(CalibrationError):verify_events([e],'builder',[r])
        e=self.event();e['item']['result']['content'][0]['text']='{"contract":"tampered"}'
        with self.assertRaises(CalibrationError):verify_events([e],'builder',[r])

    def test_tool_allowlist_is_closed(self):
        for kind in ('command_execution','file_change','web_search','unknown_future_tool'):
            with self.assertRaises(CalibrationError):verify_events([{'item':{'type':kind}}],'builder',[])
        with self.assertRaises(CalibrationError):verify_events([self.event()],'analyst',[self.record()])
        with self.assertRaises(CalibrationError):verify_events([self.event()],'builder',[])

    def test_terminal_equipment_failure_cannot_create_rate(self):
        self.assertEqual(decision(10,10,True),'void-equipment-failure-no-rate')
        self.assertEqual(decision(7,9),'incomplete-no-rate')
        self.assertIn('separately-authorized',decision(7,10))
        self.assertIn('no-further-generation',decision(3,10))
        self.assertIn('no-automatic',decision(5,10))
        self.assertLess(interval(7,10)['lower'],0.7);self.assertGreater(interval(7,10)['upper'],0.7)

    def test_support_assembly_cannot_be_overridden(self):
        source='package org.idempiere.test;\nclass LightyearOperationsTest extends AbstractTestCase {}'
        result=assemble(ROOT,source)
        self.assertTrue(result.startswith(source+'\n'))
        self.assertEqual(result.count('package org.idempiere.test;'),1)
        self.assertEqual(result.count('final class JourneySupport'),1)
        with self.assertRaises(CalibrationError):assemble(ROOT,source+'\nclass JourneySupport {}')

    def test_failing_stage_a_blocks_generation(self):
        with patch('pathlib.Path.read_bytes',return_value=b'test'),patch('tools.ms94_controller.read_json',side_effect=CalibrationError('Stage A stopped')):
            with self.assertRaises(CalibrationError):stage_a(ROOT,ROOT/'work/no-equipment')

    def test_broker_errors_are_closed_and_every_call_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);public=root/'factory/idempiere/qualification-ms94';public.mkdir(parents=True)
            for s in ('operations-shapes-v2.json','procure-to-pay-shapes.json'):(public/s).write_text('{}')
            fake=Mock();fake.root=root;fake.session=root/'work/ms93/builder-workspaces/session-test';fake.session.mkdir(parents=True)
            fake.public_contract.side_effect=RuntimeError('PRIVATE_EXPECTED_AMOUNT_AND_DATABASE_ROW')
            with patch('tools.ms94_builder_mcp.BuilderTools',return_value=fake):
                broker=RecordedTools(root,1,'test');out=broker.call('public_contract',{'scenario':'operations'})
            self.assertEqual(out,{'status':'tool-rejected','error_code':'RuntimeError'})
            records=transcript(root,'test');self.assertEqual(len(records),1)
            self.assertNotIn('PRIVATE_',json.dumps(records))
            p=fake.session/'tool-transcript/00001/result.json'
            value=json.loads(p.read_text());value['output']={'injected':'answer'};p.write_text(json.dumps(value))
            with self.assertRaises(CalibrationError):transcript(root,'test')


if __name__=='__main__':unittest.main()
