"""CI-only original assembler/scanner probes; no admitted case is constructed.

Only disposable copies of the committed public worker are changed. Original
GraphContextAssembler and scan are invoked directly without patching either.
A native component breach is not controller admission, no-send evidence, or
strict answer-fragment qualification; the full case route remains required.
"""
import base64,copy,hashlib,json,os,tempfile,unittest
from pathlib import Path
from lightyear_factory.context import GraphContextAssembler
from lightyear_factory.contracts import ContractError,WorkOrder
from lightyear_factory.isolation_scan import scan
from lightyear_execution.configured_receipt_scan_match import classify_stopping_view
import test_configured_receipt_scan_observation as fixtures


class NativeAssemblerFragmentProbes(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.source=Path(__file__).resolve().parents[1]
        self.document=json.loads((self.source/'docs/factory/p5-human-clean-control/configured-build-control/work-order.json').read_bytes())
        self.assertEqual(self.document['metadata'],{'context_schema':'1.0','graph':'packed'})
        self.order=WorkOrder.from_dict(copy.deepcopy(self.document))
        self.assertEqual(len(self.order.allowed_paths),1)
        self.relative=self.order.allowed_paths[0];self.original=self.source/self.relative
        self.original_bytes=self.original.read_bytes()
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.assert_original_unchanged)
        self.root=Path(self.tmp.name).resolve();self.worker=self.root/self.relative
        self.worker.parent.mkdir(parents=True);self.worker.write_bytes(self.original_bytes)
        # Original scanner sees a clean copied public worker before any stimulus.
        self.assertEqual(scan([('initial-workspace-file',self.worker.read_bytes())],
            fixtures.CANARIES,[fixtures.PUBLIC])['status'],'passed')
    def assert_original_unchanged(self):
        self.assertEqual(self.original.read_bytes(),self.original_bytes)
    def assemble(self,raw=None,**policy):
        if raw is not None:self.worker.write_bytes(raw)
        document=copy.deepcopy(self.document);document['policy'].update(policy)
        order=WorkOrder.from_dict(document)
        context=GraphContextAssembler(None,None).assemble(order,self.root)
        # Same JSON expression as the original _scan_controller_value boundary.
        encoded=json.dumps(context,sort_keys=True,ensure_ascii=False).encode('utf-8')
        return context,encoded
    def expect_breach(self,raw):
        context,encoded=self.assemble(raw)
        self.assertEqual(len(context['allowed_files']),1)
        row=context['allowed_files'][0]
        self.assertEqual(row['path'],self.relative)
        self.assertEqual(row['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(row['bytes'],len(raw));self.assertFalse(row['truncated'])
        self.assertEqual(row['content'],raw.decode('utf-8'))
        try:scan([('controller-context',encoded)],fixtures.CANARIES,[fixtures.PUBLIC])
        except ContractError as error:
            self.assertEqual(error.args,('isolation-breach',))
            trace=error.__traceback__
            try:
                while trace.tb_next is not None:trace=trace.tb_next
                self.assertIs(trace.tb_frame.f_code,scan.__code__)
                values=trace.tb_frame.f_locals
                self.assertEqual(classify_stopping_view(values['tokens'],values['windows'],values['normalized']),
                    'expected-window')
            finally:del trace
        else:self.fail('original assembler/scanner did not refuse the included public fragment')
    def test_clean_original_copy_assembles_and_scans(self):
        context,encoded=self.assemble()
        self.assertEqual(len(context['allowed_files']),1)
        self.assertEqual(context['allowed_files'][0]['content'],self.original_bytes.decode('utf-8'))
        result=scan([('controller-context',encoded)],fixtures.CANARIES,[fixtures.PUBLIC])
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['scanned'],[{'artifact':'controller-context','sha256':hashlib.sha256(encoded).hexdigest()}])
    def test_plain_fragment_in_copied_worker_reaches_native_scan(self):
        self.expect_breach(('# '+fixtures.PUBLIC+'\n').encode())
    def test_normalized_fragment_in_actual_assembled_content_refuses(self):
        self.expect_breach(('# '+' '.join(fixtures.PUBLIC.upper())+'\n').encode())
    def test_encoded_fragment_in_actual_assembled_content_refuses(self):
        self.expect_breach(b'# '+base64.b64encode(fixtures.PUBLIC.encode())+b'\n')
    def test_fragment_beyond_file_limit_is_not_in_context(self):
        raw=b'# ordinary public line\n'*60+fixtures.PUBLIC.encode()
        context,encoded=self.assemble(raw,max_file_bytes=1000)
        row=context['allowed_files'][0]
        self.assertTrue(row['truncated']);self.assertEqual(row['content'],raw[:1000].decode())
        self.assertEqual(row['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertNotIn(fixtures.PUBLIC,row['content'])
        self.assertEqual(scan([('controller-context',encoded)],fixtures.CANARIES,[fixtures.PUBLIC])['status'],'passed')
    def test_context_budget_omits_whole_fragment_bearing_file(self):
        raw=(b'# ordinary public line\n'*100)+fixtures.PUBLIC.encode()
        context,encoded=self.assemble(raw,max_context_bytes=1000)
        self.assertEqual(context['allowed_files'],[]);self.assertTrue(context['truncated'])
        self.assertIn('Allowed-file context exceeded the byte budget.',context['limitations'])
        self.assertEqual(scan([('controller-context',encoded)],fixtures.CANARIES,[fixtures.PUBLIC])['status'],'passed')
    def test_missing_allowed_worker_does_not_fabricate_fragment(self):
        self.worker.unlink();context,encoded=self.assemble()
        self.assertEqual(context['allowed_files'],[])
        self.assertEqual(scan([('controller-context',encoded)],fixtures.CANARIES,[fixtures.PUBLIC])['status'],'passed')
    def test_unsupported_context_schema_is_not_a_breach(self):
        document=copy.deepcopy(self.document);document['metadata']['context_schema']='unsupported'
        order=WorkOrder.from_dict(document)
        with self.assertRaisesRegex(ContractError,'Unsupported context schema'):
            GraphContextAssembler(None,None).assemble(order,self.root)
