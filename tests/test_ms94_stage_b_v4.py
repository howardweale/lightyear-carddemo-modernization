import hashlib
import json
import re
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from lightyear_calibration.contracts import CalibrationError, read_json, seal
from lightyear_calibration.journey_order import save, file_hash
from tools.ms94_controller_v4 import assemble, public_prompt, SUPPORT
from tools.ms94_builder_mcp_v4 import RecordedTools, transcript, TOOLS, SERVER
from tools.ms94_tool_policy_v4 import arguments, verify_events
from tools.ms94_public_api_v4 import api, CATALOG
from tools.ms94_stage_b_evidence import stage_a

ROOT = Path(__file__).resolve().parents[1]


class StageBEquipment04(unittest.TestCase):
    def test_reviewed_support_assembly_is_the_qualified_reference_assembly(self):
        support = (ROOT/SUPPORT).read_text(encoding='utf-8')
        embedded = support.replace('package org.idempiere.test;', '', 1).replace(
            'public final class JourneySupport', 'final class JourneySupport', 1)
        reference = (ROOT/SUPPORT.parent.parent/'references/operations/LightyearOperationsTest.java').read_text(encoding='utf-8')
        self.assertTrue(reference.rstrip().endswith(embedded.strip()))
        source = reference.rstrip()[:-len(embedded.strip())].rstrip()
        self.assertEqual(assemble(ROOT, source).rstrip(), reference.rstrip())
        with self.assertRaises(CalibrationError):
            assemble(ROOT, source+'\nclass JourneySupport {}')

    def test_prompt_and_broker_use_reviewed_contracts(self):
        prompt = public_prompt(ROOT)
        self.assertEqual(prompt['public_shapes'], read_json(ROOT/SUPPORT.parent/'operations-shapes.json'))
        self.assertEqual(prompt['public_trace_contract'], read_json(ROOT/SUPPORT.parent/'operations.json'))
        self.assertNotIn('Do not use tools.', prompt['instruction'])
        self.assertNotIn('references/operations', json.dumps(prompt))
        self.assertIn('compile', prompt['instruction'])

    def test_only_five_declared_tools_in_transport_configuration(self):
        args = arguments(ROOT, Path('python.exe'), 'test', 3)
        config = tomllib.loads(next(s for s in args if s.startswith('mcp_servers=')))
        self.assertEqual(set(config['mcp_servers']), {SERVER})
        server = config['mcp_servers'][SERVER]
        self.assertEqual(server['enabled_tools'], list(TOOLS))
        self.assertEqual(server['args'][1], 'tools.ms94_builder_mcp_v4')
        self.assertTrue(server['required'])
        self.assertIn('--ignore-user-config', args)
        for kind in ('command_execution', 'file_change', 'web_search', 'new_unknown_tool'):
            with self.assertRaises(CalibrationError):
                verify_events([{'item':{'type':kind}}], 'builder', [])

    def test_api_has_no_path_or_arbitrary_method_access(self):
        with self.assertRaises(CalibrationError): api(ROOT, '../../private/reference')
        with self.assertRaises(CalibrationError): api(ROOT, 'MInvoice', '.*')
        value = api(ROOT, 'MInvoice', 'setC_Order_ID')
        self.assertTrue(value['inherited_generated_api'][0]['signatures'])
        for parent in value['inherited_generated_api']:
            self.assertTrue(all(re.search(r'\bsetC_Order_ID\s*\(', s) for s in parent['signatures']))
        self.assertNotIn('private_business', json.dumps(value))

    def test_compiler_budget_survives_broker_restart_and_errors_do_not_leak(self):
        from tools.ms94_broker_v4 import BuilderTools
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(ROOT/SUPPORT.parent, root/SUPPORT.parent)
            save(root/'work/ms87/local-runtime.json', {'runner_image':'sha256:'+'a'*64})
            first = BuilderTools(root, 1, 'test')
            with patch('tools.ms94_broker_v4.compile_candidate', side_effect=RuntimeError('PRIVATE_DATABASE_VALUE')):
                value = first.compile('class LightyearOperationsTest extends AbstractTestCase {}')
            self.assertEqual(value, {'status':'development-tool-error','error_type':'RuntimeError'})
            second = BuilderTools(root, 1, 'test')
            with self.assertRaises(CalibrationError): second.compile('another source')

    def test_every_closed_error_is_recorded_and_chain_is_tamper_evident(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); shutil.copytree(ROOT/SUPPORT.parent, root/SUPPORT.parent)
            save(root/'work/ms87/local-runtime.json', {'runner_image':'sha256:'+'a'*64})
            broker = RecordedTools(root, 1, 'test')
            with patch.object(broker.broker, 'public_contract', side_effect=RuntimeError('PRIVATE_ANSWER')):
                result = broker.call('public_contract', {'scenario':'operations'})
            self.assertEqual(result, {'status':'tool-rejected','error_code':'RuntimeError'})
            records = transcript(root, 'test')
            self.assertEqual(len(records), 1); self.assertNotIn('PRIVATE_ANSWER', json.dumps(records))
            event = {'type':'item.completed','item':{'id':'one','type':'mcp_tool_call','server':SERVER,
                'tool':'public_contract','arguments':{'scenario':'operations'},'error':None,
                'result':{'structuredContent':result}}}
            self.assertTrue(verify_events([event], 'builder', records)['verified'])
            event['item']['result']['structuredContent'] = {'secret':'injection'}
            with self.assertRaises(CalibrationError): verify_events([event], 'builder', records)
            with self.assertRaises(CalibrationError): verify_events([event], 'analyst', records)

    def test_equipment_guard_requires_full_publication_and_unchanged_sources(self):
        # The committed records are authentic. Route hash reads to the preserved
        # snapshot only for this working-tree CRLF fixture; never normalize data.
        frozen = ROOT/'work/ms94/execution-snapshots/equipment-04'
        if not frozen.exists(): self.skipTest('local accepted native evidence required')
        equipment = ROOT/'docs/calibration/idempiere-ms94/equipment-04'
        plan, accepted = stage_a(frozen, equipment)
        self.assertEqual(len(plan['schedule']), 62); self.assertTrue(accepted['passed'])
        with patch('tools.ms94_stage_b_evidence.file_hash', return_value='changed'):
            with self.assertRaises(CalibrationError): stage_a(frozen, equipment)
        with self.assertRaises(CalibrationError): stage_a(frozen, equipment, live=True)

    def test_stopping_result_is_visible_before_publication_replay(self):
        from tools import ms94_measure_v4 as measure
        from lightyear_calibration.journey_runtime import JourneySigner
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); output=root/'campaign'; signer=JourneySigner(root)
            slots=[{'phase':phase,'index':i,'path':f'campaign/trials/{phase}-{i}',
                    'plan_sha256':f'{phase}-{i}'}
                   for phase,count in [('pilot',3),('cohort',10)] for i in range(1,count+1)]
            plan=seal({'slots':slots,'max_elapsed_seconds':3600})
            save(output/'plan.json',plan)
            for name in ('authorization','declaration'):
                save(output/(name+'.json'),signer.sign({'plan_sha256':plan['content_sha256']}))
            result={'content_sha256':'result','status':'void-equipment-failure','first_try_pass':False,
                    'repaired_pass':False,'cost':{},'attempts':[{'result_class':'judge-error','run_directory':'native/test'}]}
            def publish(*args):
                self.assertEqual(read_json(output/'stopping.json')['status'],'void-equipment-failure')
                self.assertEqual(len(read_json(output/'progress.json')['results']),1)
                raise RuntimeError('retained replay failure')
            with patch.object(measure.controller,'frozen',return_value={'content_sha256':'pilot-1'}), \
                 patch.object(measure.controller,'run',return_value=result) as run, \
                 patch('tools.ms94_publication_b_v4.publish',side_effect=publish):
                report=measure.run(root,output,Path('unused'))
                self.assertEqual(run.call_count,1)
            self.assertTrue(report['cohort_void']); self.assertIsNone(report['rate'])
            self.assertEqual(report['unstarted_slots'],12)
            self.assertEqual(report['results'][0]['attempts'][0]['result_class'],'judge-error')
            # A failed terminal run cannot be resumed or replace its first slot.
            with self.assertRaises(FileExistsError): measure.run(root,output,Path('unused'))

    def test_native_setup_exception_leaves_signed_inspectable_gate(self):
        from tools import ms94_native_b_v4 as native
        from lightyear_control_tower.decisions import verify_envelope
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); campaign=root/'campaign'; build=campaign/'calls/001-builder/build'
            source=build/'workspace/LightyearOperationsTest.java'
            source.parent.mkdir(parents=True); source.write_text('candidate',encoding='utf-8')
            files=['tools/ms94_native_b_v4.py','tools/ms94_v4_gate.py','tools/ms94_v3_negative_checks.py',
                   'tools/qualification_private_runner.py','tools/qualification_application_worker.py',
                   str(native.AREA/'public/JourneySupport.java'),str(native.AREA/'public/operations-shapes.json'),
                   str(native.AREA/'private/history-bound.json'),str(native.INVENTORY)]
            for name in files:
                path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('{}',encoding='utf-8')
            save(root/native.REGISTER,seal({}))
            cp={'content_sha256':'trial','equipment_directory':'equipment','support_sha256':'support',
                'implementation_sha256':{},'assessed_on':'2026-09-29'}
            ep={'base_plan':{'declaration':{'application':{'source_commit':'commit'}}}}
            builder={'harness_sha256':file_hash(source),'provider_invocations':1}
            with patch('tools.ms94_controller_v4.frozen',return_value=cp), \
                 patch('tools.ms94_controller_v4.stage_a',return_value=(ep,{})), \
                 patch.object(native,'archived',return_value={}), \
                 patch.object(native.subprocess,'Popen'), \
                 patch('tools.qualification_private_runner.PrivateRunner',side_effect=RuntimeError('setup failed')):
                run,receipt=native.execute_native(root,campaign,build,builder,60)
            self.assertEqual(receipt['status'],'execution-failure')
            self.assertTrue(verify_envelope(receipt,(run/'authority.public.pem').read_bytes()))
            gate=read_json(run/'gate.json')
            self.assertEqual(gate,native.evaluate(run))
            self.assertEqual(gate['status'],'execution-failure')


if __name__ == '__main__': unittest.main()
