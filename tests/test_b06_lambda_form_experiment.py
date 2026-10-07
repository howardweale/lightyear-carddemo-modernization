"""Incomplete LambdaForm work must never be promoted to native admission."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from tools.b06_host_probe.lambda_form_replay import replay_body, expression_recipe, emission_definition_binding, class_data_initialization

AREA=Path(__file__).resolve().parents[1]/'work/b06-observer-v2-host'
OBS=AREA/'generation-proof-attempt8/observations.json'


class FailClosedGraphTests(unittest.TestCase):
    def test_missing_graph_fails(self):
        for value in (None,{}, {'root':'missing','nodes':{}}):
            with self.assertRaises(ValueError):expression_recipe(value)


@unittest.skipUnless(OBS.exists(),'local external-JDI evidence absent')
class LocalLambdaFormTests(unittest.TestCase):
    def setUp(self):
        self.d=json.loads(OBS.read_text(encoding='utf-8'))
        self.records=[r for r in self.d['records'] if r['kind']=='generation' and 'lambda_form_graph' in r]
    def test_emitter_return_and_actual_definition_bytes_match(self):
        returns={r['returned_bytes_object_id']:r for r in self.d['records'] if r['kind']=='generator-bytecode'}
        self.assertEqual(len(returns),24);self.assertEqual(len(self.records),24)
        for r in self.records:
            emitted=returns[r['definition_input_object_id']]
            self.assertEqual(emitted['thread_id'],r['thread_id'])
            self.assertEqual(emitted['returned_bytes_hex'],r['definition_input_hex'])
            self.assertEqual(hashlib.sha256(bytes.fromhex(r['definition_input_hex'])).hexdigest(),r['definition_input_sha256'])
            runtime=self.d['definitions'][str(r['returned_class']['class_object_id'])]
            self.assertTrue(emission_definition_binding(emitted,r,runtime)['emission_definition_bound'])
    def test_expression_match_does_not_claim_full_proof(self):
        passed=0;rejected=[]
        for r in self.records:
            d=self.d['definitions'][str(r['returned_class']['class_object_id'])]
            name=next(m['name'] for m in d['methods'] if m['name']!='<clinit>')
            try:p=replay_body(d,r['lambda_form_graph'],name)
            except ValueError as e:rejected.append(str(e));continue
            self.assertFalse(p['adapter_body_verified']);self.assertFalse(p['native_admission']);passed+=1
        self.assertEqual(passed,24)
        self.assertEqual(rejected,[])
    def test_forged_emitter_array_loader_or_graph_fails(self):
        originals={r['returned_bytes_object_id']:r for r in self.d['records'] if r['kind']=='generator-bytecode'}
        for change in ('emitter','array','loader','graph','runtime-code','runtime-pool'):
            r=copy.deepcopy(self.records[0]);e=copy.deepcopy(originals[r['definition_input_object_id']]);d=copy.deepcopy(self.d['definitions'][str(r['returned_class']['class_object_id'])])
            if change=='emitter':e['entry_method']='candidate.Forged.generateCustomizedCodeBytes()[B'
            elif change=='array':e['returned_bytes_object_id']+=1
            elif change=='loader':d['loader']='candidate'
            elif change=='graph':e['lambda_form_graph']['nodes'][e['lambda_form_graph']['root']]['fields']['java.lang.invoke.LambdaForm.result']='-1'
            elif change=='runtime-code':
                m=d['methods'][0];code=b'\x00'+bytes.fromhex(m['bytecode_hex']);m['bytecode_hex']=code.hex();m['sha256']=hashlib.sha256(code).hexdigest()
            else:
                cp=bytes.fromhex(d['constant_pool_hex'])+b'\x01\x00\x01x';d['constant_pool_hex']=cp.hex();d['constant_pool_sha256']=hashlib.sha256(cp).hexdigest()
            with self.assertRaises(Exception):emission_definition_binding(e,r,d)
    def test_extra_logic_and_wrong_graph_fail(self):
        r=self.records[0];d=copy.deepcopy(self.d['definitions'][str(r['returned_class']['class_object_id'])])
        m=next(m for m in d['methods'] if m['name']!='<clinit>')
        code=b'\x00'+bytes.fromhex(m['bytecode_hex']);m['bytecode_hex']=code.hex();m['sha256']=hashlib.sha256(code).hexdigest()
        with self.assertRaisesRegex(ValueError,'opcode'):replay_body(d,r['lambda_form_graph'],m['name'])
        graph=copy.deepcopy(r['lambda_form_graph'])
        graph['nodes'][graph['root']]['fields']['java.lang.invoke.LambdaForm.arity']='999'
        with self.assertRaisesRegex(ValueError,'shape'):expression_recipe(graph)

    def test_class_data_initializers_and_changed_object_fail_closed(self):
        for record in self.records:
            self.assertTrue(class_data_initialization(record)['class_data_initialization_verified'])
            bad=copy.deepcopy(record);bad['class_data_graph']['root']='other'
            with self.assertRaisesRegex(ValueError,'object-differs'):class_data_initialization(bad)
            bad=copy.deepcopy(record)
            raw=bytes.fromhex(bad['definition_input_hex'])
            # Mutate classData's exact accessor name while preserving pool size.
            self.assertIn(b'classData',raw);raw=raw.replace(b'classData',b'wrongData')
            bad['definition_input_hex']=raw.hex();bad['definition_input_sha256']=hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError,'wrong-accessor'):class_data_initialization(bad)


if __name__=='__main__':unittest.main()
