from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from lightyear_factory.contracts import ContractError
from lightyear_factory.workspace import IsolatedWorkspace
from lightyear_factory.gates import builder_failure_view
from lightyear_factory.orchestrator import FactoryOrchestrator
from lightyear_factory.isolation_scan import scan

class FactoryAllowlistFeedbackTests(unittest.TestCase):
    def test_copy_only_exact_files_without_history_or_private_judge(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir()
            for p,text in {'public/input.txt':'public fixture','.git/config':'history',
                           'private/reference.txt':'secret expected output'}.items():
                target=source/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
            manifest={'public/input.txt':sha256(b'public fixture').hexdigest()}
            workspace=IsolatedWorkspace(source,root/'workspace',('candidate',),manifest)
            workspace.create();self.assertEqual(manifest,workspace.full_manifest())
            self.assertFalse((workspace.root/'.git').exists());self.assertFalse((workspace.root/'private').exists())
            (workspace.root/'candidate').mkdir();(workspace.root/'candidate/toy.txt').write_text('fixture output')
            self.assertIn('candidate/toy.txt',workspace.verify_read_boundary())
            (workspace.root/'public/input.txt').write_text('changed')
            with self.assertRaisesRegex(ContractError,'readonly-changed'):workspace.verify_read_boundary()

    def test_hash_path_and_link_refusals_precede_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.mkdir();(source/'input').write_text('input')
            for path in ('../escape','.git/config','.GIT/config','/absolute','C:/escape',r'a\b','a//b'):
                with self.assertRaises(ContractError):IsolatedWorkspace(source,root/'dest',('candidate',),{path:'a'*64})
            workspace=IsolatedWorkspace(source,root/'dest',('candidate',),{'input':'0'*64})
            with self.assertRaisesRegex(ContractError,'hash-mismatch'):workspace.create()
            self.assertFalse(workspace.root.exists())
            if os.name!='nt':
                (source/'link').symlink_to(source/'input')
                linked=IsolatedWorkspace(source,root/'linked',('candidate',),{'link':sha256(b'input').hexdigest()})
                with self.assertRaisesRegex(ContractError,'symlink'):linked.create()
            workspace=IsolatedWorkspace(source,root/'dest',('candidate',),{'input':sha256(b'input').hexdigest()});workspace.create()
            (workspace.root/'unlisted').write_text('unexpected')
            with self.assertRaisesRegex(ContractError,'unlisted-file'):workspace.verify_read_boundary()
            (workspace.root/'unlisted').unlink();(workspace.root/'.git').mkdir()
            with self.assertRaisesRegex(ContractError,'history'):workspace.verify_read_boundary()

    def test_gateway_never_forwards_values_trace_output_or_analyst_prose(self):
        vocabulary=dict(screens=['FIXTURE'],fields=['FIELD'],tables=['TABLE'])
        private='expected-private-value-012345678901234567890123456789'
        report=dict(status='failed',expected=private,trace=private,gates=[dict(expose_output_to_builder=True,stdout=private)],
                    differences=[dict(interaction=7,screen='FIXTURE',field='FIELD',category='value',expected=private,actual=private)])
        public=builder_failure_view(report,vocabulary)
        self.assertEqual(dict(status='failed',differences=[dict(interaction=7,screen='FIXTURE',field='FIELD',category='value')]),public)
        envelope=FactoryOrchestrator._failure_envelope(public,dict(summary=private,builder_guidance=private),include_diagnosis=False)
        self.assertNotIn(private,json.dumps(envelope));self.assertEqual(public,envelope)
        for key,value in [('screen',private),('field',private),('category',private),('interaction',True)]:
            bad=json.loads(json.dumps(report));bad['differences'][0][key]=value
            with self.assertRaises(ContractError):builder_failure_view(bad,vocabulary)

    def test_three_canary_classes_and_any_expected_forty_character_run_fail(self):
        canaries={k:k+'-UNIQUE-'+'x'*40 for k in ('expected-state','reference-output','session-answer')}
        expected='0123456789'*6
        clean=scan([('fixture prompt','public inputs only')],canaries,[expected]);self.assertEqual('passed',clean['status'])
        for text in [*canaries.values(),expected[9:49]]:
            for artifact in ('prompt','response','tool-call','workspace-file'):
                with self.assertRaisesRegex(ContractError,'^isolation-breach$'):scan([(artifact,text)],canaries,[expected])
        escaped='line\n'*12
        with self.assertRaisesRegex(ContractError,'isolation-breach'):
            scan([('response',json.dumps({'content':escaped}))],canaries,[escaped])
        with self.assertRaisesRegex(ContractError,'canary-classes'):scan([],{},[])
