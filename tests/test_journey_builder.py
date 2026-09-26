"""Transport fixtures test builder boundaries, never claim model execution."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lightyear_calibration import journey_builder as builder
from lightyear_calibration.contracts import read_json
from lightyear_calibration.journey_order import save

ROOT=Path(__file__).resolve().parents[1]


class BuilderTests(unittest.TestCase):
    def invoke(self,root,*,tool=False,path='LightyearPartialInvoiceTest.java',replace=None,previous=(),repair=None):
        declaration=read_json(ROOT/builder.ORDER);save(root/builder.ORDER,declaration)
        prompt=root/'prompt.json';save(prompt,{'declaration':declaration,**({'single_call_repair':repair} if repair is not None else {})})
        executable=root/'fixture-executable';executable.write_bytes(b'unit-test-only')
        for number,events in enumerate(previous, 2):
            prior=root/f'build-{number:02d}';prior.mkdir()
            save(prior/'invocation.json',{'fixture':True})
            (prior/'events.jsonl').write_text(''.join(json.dumps(event)+'\n' for event in events),encoding='utf-8')
        class Transport:
            returncode=0
            def __init__(self,args,**kwargs):
                self.args=args;self.out=kwargs['stdout']
            def communicate(self,payload,timeout):
                events=[{'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}}]
                if tool:events.insert(0,{'type':'item.completed','item':{'type':'command_execution'}})
                for event in events:self.out.write(json.dumps(event).encode()+b'\n')
                self.out.flush()
                proposal={'summary':'Fixture only','blocked_reason':None,'edits':[{'path':path,'find':builder.PLACEHOLDER,
                    'replace':replace or 'public class LightyearPartialInvoiceTest extends AbstractTestCase {}\n','rationale':'Fixture only'}]}
                save(Path(self.args[self.args.index('-o')+1]),proposal)
        with patch.object(builder.subprocess,'Popen',Transport):
            return builder.build(root,root/'build-01',executable,prompt)

    def test_broker_proposal_never_claims_native_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt=self.invoke(Path(temp))
            self.assertEqual(1,receipt['provider_invocations'])
            self.assertFalse(receipt['native_execution_verified'])
            self.assertFalse(receipt['gate_output_exposed'])

    def test_tool_operation_and_verifier_patch_are_rejected(self):
        for change in ({'tool':True},{'path':'../verifier.py'}, {'replace':'public class LightyearPartialInvoiceTest extends AbstractTestCase { ProcessBuilder forbidden; }'}):
            with tempfile.TemporaryDirectory() as temp,self.assertRaises(ValueError):self.invoke(Path(temp),**change)

    def test_line_budget_is_enforced_before_execution(self):
        with tempfile.TemporaryDirectory() as temp,self.assertRaisesRegex(ValueError,'max_changed_lines'):
            self.invoke(Path(temp),replace='public class LightyearPartialInvoiceTest extends AbstractTestCase {\n'+'// excessive\n'*421+'}\n')

    def test_failed_transport_consumes_budget_but_not_completed_turn(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt=self.invoke(Path(temp),previous=(
                [{'type':'turn.failed','error':{'message':'fixture incompatible client'}}],
                [{'type':'turn.completed','usage':{'input_tokens':7,'output_tokens':3}}],
            ))
            self.assertEqual(3,receipt['provider_invocations'])
            self.assertEqual(2,receipt['completed_turns'])
            self.assertEqual(1,receipt['completed_turns_current'])
            self.assertEqual([0,1],[entry['completed_turns'] for entry in receipt['prior_invocations']])
            self.assertEqual('current successful generation',receipt['usage_scope'])

    def test_exhausted_budget_refuses_another_transport(self):
        budget=read_json(ROOT/builder.ORDER)['policy']['max_builder_invocations']
        with tempfile.TemporaryDirectory() as temp,self.assertRaisesRegex(ValueError,'budget exhausted'):
            self.invoke(Path(temp),previous=tuple([] for _ in range(budget)))

    def test_single_call_repair_refuses_any_other_source_change(self):
        original='public class LightyearPartialInvoiceTest extends AbstractTestCase { /* oldCall */ }\n'
        expected=original.replace('oldCall','newCall')
        repair={'source':original,'find':'oldCall','replace':'newCall',
                'source_sha256':hashlib.sha256(original.encode()).hexdigest(),
                'expected_sha256':hashlib.sha256(expected.encode()).hexdigest()}
        with tempfile.TemporaryDirectory() as temp:
            receipt=self.invoke(Path(temp),replace=expected,repair=repair)
            self.assertEqual(repair['expected_sha256'],receipt['harness_sha256'])
        with tempfile.TemporaryDirectory() as temp,self.assertRaisesRegex(ValueError,'outside the approved'):
            self.invoke(Path(temp),replace=expected+'// unapproved change\n',repair=repair)


if __name__=='__main__':unittest.main()
