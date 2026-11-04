"""No-spend component CI; no API, keys, original checkout or private judge."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from lightyear_factory.agents import BUILDER_SCHEMA
from lightyear_factory.contracts import ContractError, WorkOrder
from lightyear_factory.workspace import IsolatedWorkspace
from tools.ci import supervised_intcalc_boundary as boundary


class SupervisedIntcalcBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[1]
        cls.original = subprocess.check_output(['git', '-C', str(cls.repo),
            'show', 'HEAD:' + boundary.PATH])
        cls.seed = cls.original.replace(b'MONTHS_PERCENT = 1200', b'MONTHS_PERCENT = 100')

    def proposal(self, value=1200):
        return dict(summary='engineering proposal', blocked_reason=None,
            edits=[dict(path=boundary.PATH, find='MONTHS_PERCENT = 100',
                        replace='MONTHS_PERCENT = '+str(value), rationale='public monthly rule')])

    def response(self):
        return dict(model=boundary.MODEL, service_tier='flex', status='completed',
            usage=dict(input_tokens=1000, output_tokens=100),
            output=[dict(type='message', role='assistant', status='completed',
                         content=[dict(type='output_text', text=json.dumps(self.proposal()))])])

    def parse(self, response):
        return boundary.response_proposal(json.dumps(response).encode(), self.seed)

    def test_only_public_literal_can_vary(self):
        self.assertEqual(boundary.checked_candidate(self.seed), b'MONTHS_PERCENT = 100')
        for data in (self.seed+b'\n', self.seed.replace(b'ROUNDING = "down"', b'ROUNDING = "up"'),
                     self.seed+b'import os\n', self.seed.replace(b'\n', b'\r\n')):
            with self.subTest(data=data[-40:]), self.assertRaises(ContractError):
                boundary.checked_candidate(data)

    def test_literal_limits_and_types(self):
        for value in (b'0', b'-1', b'True', b'1.5', b'1000001', b'__import__("os")', b'1;print(1)'):
            with self.subTest(value=value), self.assertRaises(ContractError):
                boundary.checked_candidate(self.seed.replace(b'MONTHS_PERCENT = 100', b'MONTHS_PERCENT = '+value))
        boundary.checked_candidate(self.seed.replace(b'MONTHS_PERCENT = 100', b'MONTHS_PERCENT = 1000000'))

    def test_request_is_fixed_flex_without_tools_or_count(self):
        request = json.loads(boundary.generation_request(self.seed))
        self.assertEqual(request['model'], 'gpt-5.4-2026-03-05')
        self.assertEqual(request['service_tier'], 'flex')
        self.assertEqual(request['max_output_tokens'], 4096)
        self.assertEqual(request['tools'], [])
        self.assertEqual(request['tool_choice'], 'none')
        self.assertFalse(request['background']); self.assertFalse(request['store'])
        self.assertFalse(request['stream']); self.assertNotIn('previous_response_id', request)
        self.assertIn(boundary.LABEL, request['instructions'])
        self.assertEqual(request['input'].encode(), self.seed)
        self.assertLessEqual(len(boundary.generation_request(self.seed)), 32768)

    def test_original_builder_schema_is_preserved(self):
        before = copy.deepcopy(BUILDER_SCHEMA)
        request = json.loads(boundary.generation_request(self.seed))
        self.assertEqual(request['text']['format']['schema'], before)
        request['text']['format']['schema']['properties'].clear()
        self.assertEqual(BUILDER_SCHEMA, before)

    def test_documented_envelope_is_below_cap_without_usage_discount(self):
        from decimal import Decimal
        self.assertEqual(boundary.documented_two_call_envelope(), Decimal('17.886'))
        self.assertLess(boundary.documented_two_call_envelope(), Decimal(25))

    def test_valid_proposal_changes_only_integer(self):
        self.assertEqual(boundary.checked_proposal(self.seed, self.proposal()), self.original)
        other = boundary.checked_proposal(self.seed, self.proposal(25))
        self.assertEqual(other, self.seed.replace(b'MONTHS_PERCENT = 100', b'MONTHS_PERCENT = 25'))

    def test_path_and_executable_injection_refuse(self):
        for field, value in (('path','../candidate.py'), ('find','100'),
                             ('replace','MONTHS_PERCENT = 1200\nimport os'),
                             ('replace','MONTHS_PERCENT = 1200 # comment')):
            item = self.proposal(); item['edits'][0][field] = value
            with self.subTest(field=field,value=value), self.assertRaises(ContractError):
                boundary.checked_proposal(self.seed, item)

    def test_multiple_noop_blocked_or_extra_fields_refuse(self):
        examples=[self.proposal(100), self.proposal(), self.proposal(), self.proposal()]
        examples[1]['edits'] *= 2; examples[2]['blocked_reason']='cannot repair'; examples[3]['approved']=True
        for item in examples:
            with self.subTest(item=item), self.assertRaises(ContractError):
                boundary.checked_proposal(self.seed,item)

    def test_response_requires_exact_model_tier_and_completion(self):
        self.assertEqual(self.parse(self.response()), self.proposal())
        for key,value in (('model','gpt-5.4'),('service_tier','default'),('status','incomplete')):
            response=self.response();response[key]=value
            with self.subTest(key=key), self.assertRaises(ContractError):self.parse(response)

    def test_tool_refusal_and_ambiguous_response_refuse(self):
        for output in ([dict(type='function_call')], [], self.response()['output']*2,
                       [dict(type='message',role='assistant',status='completed',content=[dict(type='refusal',refusal='no')])]):
            response=self.response();response['output']=output
            with self.subTest(output=output), self.assertRaises(ContractError):self.parse(response)

    def test_duplicate_json_and_bad_numeric_usage_refuse(self):
        with self.assertRaises(ContractError):boundary.response_proposal(b'{"model":"x","model":"y"}', self.seed)
        for key,value in (('input_tokens',True),('input_tokens',-1),('input_tokens',1050001),
                          ('output_tokens',4097),('output_tokens',float('nan'))):
            response=self.response();response['usage'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ContractError):self.parse(response)

    def test_missing_usage_and_oversized_response_refuse(self):
        response=self.response();del response['usage']
        with self.assertRaises(ContractError):self.parse(response)
        with self.assertRaises(ContractError):boundary.response_proposal(b' '*1048577,self.seed)

    def test_original_broker_applies_in_disposable_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'source'; source.mkdir(); target=source/boundary.PATH
            target.parent.mkdir(parents=True);target.write_bytes(self.seed)
            import hashlib
            workspace=IsolatedWorkspace(source,root/'candidate',(boundary.PATH,),
                read_manifest={boundary.PATH:hashlib.sha256(self.seed).hexdigest()})
            workspace.create()
            order=WorkOrder.from_dict(json.loads((self.repo/'factory/work-orders/intcalc-repair.example.json').read_bytes()))
            result=boundary.apply_checked_proposal(order,workspace,self.seed,self.proposal())
            self.assertEqual(workspace.resolve(boundary.PATH).read_bytes(),self.original)
            self.assertEqual(target.read_bytes(),self.seed)
            self.assertEqual(result['label'],boundary.LABEL)
            self.assertFalse(result['qualification_evidence'])
            self.assertEqual(result['broker']['files_changed'],1)

    def test_changed_workspace_refuses_before_broker_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'source'; source.mkdir(); target=source/boundary.PATH
            target.parent.mkdir(parents=True);target.write_bytes(self.seed)
            import hashlib
            workspace=IsolatedWorkspace(source,root/'candidate',(boundary.PATH,),
                read_manifest={boundary.PATH:hashlib.sha256(self.seed).hexdigest()})
            workspace.create(); path=workspace.resolve(boundary.PATH);path.write_bytes(self.seed+b'\n')
            order=WorkOrder.from_dict(json.loads((self.repo/'factory/work-orders/intcalc-repair.example.json').read_bytes()))
            with self.assertRaises(ContractError):boundary.apply_checked_proposal(order,workspace,self.seed,self.proposal())
            self.assertEqual(path.read_bytes(),self.seed+b'\n')
