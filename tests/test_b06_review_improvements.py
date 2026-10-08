import copy
import tempfile
from pathlib import Path
import unittest
import zipfile
import hashlib
import io
import subprocess
from unittest.mock import patch
from b06_synthetic_classfiles import abstract_class,extended
from tools.b06_host_probe.pool_proposal_v2 import compare
from tools.b06_host_probe.pool_analysis import compare_extension
from tools.b06_image_artifacts.inventory import inventory
from tools.b06_image_artifacts.runtime_closure import assemble
from b06_synthetic_classfiles import lambda_form_fixture
from tools.b06_host_probe.lambda_form_replay import emission_definition_binding,replay_body

class ApprovedPoolAlgorithmCITests(unittest.TestCase):
    def test_exact_algorithm_positive_and_adversaries(self):
        from b06_synthetic_classfiles import reviewed_shape_pool
        source,runtime=reviewed_shape_pool()
        # Substitute only the authored fixture's identity, never production
        # counts, extension semantics or prefix/method checks.
        with self.assertRaisesRegex(ValueError,'reviewed-class'):compare_extension(source,runtime,159)
        with patch('tools.b06_host_probe.pool_analysis.CLASS_SHA',hashlib.sha256(source).hexdigest()):
            self.assertFalse(compare_extension(source,runtime,159)['production_admission'])
            for raw,count in [(bytes.fromhex(runtime).replace(b'AbstractMethodError',b'AbstractMethodErroX'),159),
                              (bytes.fromhex(runtime)+b'\x01\x00\x01x',159),
                              (bytes.fromhex(runtime),158)]:
                with self.subTest(count=count,raw=raw[-10:]),self.assertRaises(ValueError):compare_extension(source,raw.hex(),count)
            raw=bytearray.fromhex(runtime);raw[4]^=1
            with self.assertRaisesRegex(ValueError,'prefix'):compare_extension(source,raw.hex(),159)

class LambdaFormCITests(unittest.TestCase):
    def test_emission_binding_without_local_jdi_files(self):
        e,d,r,g=lambda_form_fixture()
        self.assertTrue(emission_definition_binding(e,d,r)['emission_definition_bound'])
        self.assertFalse(emission_definition_binding(e,d,r)['native_admission'])
    def test_expression_identity(self):
        e,d,r,g=lambda_form_fixture()
        self.assertTrue(replay_body(r,g,'identity')['expression_effects_match'])
        self.assertFalse(replay_body(r,g,'identity')['adapter_body_verified'])
    def test_forged_emitter_array_loader_and_graph(self):
        for fault in ('emitter','array','loader','graph'):
            e,d,r,g=lambda_form_fixture();e=copy.deepcopy(e)
            if fault=='emitter':e['entry_method']='forged'
            if fault=='array':e['returned_bytes_object_id']=4
            if fault=='loader':r['loader']='candidate'
            if fault=='graph':e['lambda_form_graph']['nodes']['f']['fields']['java.lang.invoke.LambdaForm.result']='-1'
            with self.subTest(fault=fault),self.assertRaises(ValueError):emission_definition_binding(e,d,r)
    def test_method_extra_logic_even_with_fresh_hash(self):
        import hashlib
        e,d,r,g=lambda_form_fixture();r['methods'][0].update(bytecode_hex='002ab0',sha256=hashlib.sha256(bytes.fromhex('002ab0')).hexdigest())
        with self.assertRaises(ValueError):emission_definition_binding(e,d,r)
        with self.assertRaisesRegex(ValueError,'opcode'):replay_body(r,g,'identity')
    def test_runtime_pool_changed(self):
        e,d,r,g=lambda_form_fixture();r['constant_pool_hex']+='00'
        with self.assertRaises(ValueError):emission_definition_binding(e,d,r)
    def test_direct_hidden_class_has_no_lambda_factory_provenance(self):
        from test_ms94_b06_forwarding_stub import fixture
        from tools.ms94_b06_forwarding_stub import validate_stub
        from tools.ms94_b06_admission import EvidenceFailure
        raw,f,t,c=fixture()
        with self.assertRaisesRegex(EvidenceFailure,'provenance-missing'):validate_stub(raw,f,t,c,{})
        raw['generation']={'record':{'entry_method':'java.lang.invoke.MethodHandles$Lookup.defineHiddenClass'},'definitions':{}}
        with self.assertRaisesRegex(EvidenceFailure,'not-lambda-factory'):validate_stub(raw,f,t,c,{})
    def test_application_prefix_does_not_exempt_jar_binding(self):
        from test_ms94_b06_forwarding_stub import fixture
        from tools.ms94_b06_forwarding_stub import validate_stub_body
        from tools.ms94_b06_admission import EvidenceFailure
        raw,f,t,c=fixture('org.compiere.Forged')
        with self.assertRaisesRegex(EvidenceFailure,'jar-entry'):validate_stub_body(raw,f,t,c,{})

class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.source=abstract_class()
        self.closure={'java/lang/Object':abstract_class('java/lang/Object'),
                      'fixture/Contract':abstract_class('fixture/Contract',True)}
        self.hex,self.count=extended(self.source)
    def test_derived_extension_is_proposal_not_admission(self):
        r=compare(self.source,self.closure,self.hex,self.count,[])
        self.assertFalse(r['production_admission']);self.assertEqual(r['derived_methods'],[('run','()V')])
    def test_approved_single_class_rule_is_not_widened(self):
        with self.assertRaisesRegex(ValueError,'reviewed-class'):compare_extension(self.source,self.hex,self.count)
    def test_changed_prefix(self):
        raw=bytearray.fromhex(self.hex);raw[4]^=1
        with self.assertRaisesRegex(ValueError,'prefix'):compare(self.source,self.closure,raw.hex(),self.count,[])
    def test_wrong_exception_target(self):
        raw=bytes.fromhex(self.hex).replace(b'AbstractMethodError',b'AbstractMethodErroX')
        with self.assertRaises(ValueError):compare(self.source,self.closure,raw.hex(),self.count,[])
    def test_missing_interface(self):
        self.closure.pop('fixture/Contract')
        with self.assertRaisesRegex(ValueError,'missing-bound'):compare(self.source,self.closure,self.hex,self.count,[])
    def test_count_and_methods(self):
        with self.assertRaises(ValueError):compare(self.source,self.closure,self.hex,self.count+1,[])
        with self.assertRaisesRegex(ValueError,'methods'):compare(self.source,self.closure,self.hex,self.count,[dict(name='forged',signature='()V',sha256='a'*64)])

class InventoryTests(unittest.TestCase):
    def test_withdrawn_r11_refuses_before_authority_or_execution(self):
        from tools.ms94_b06_qualification_driver import execute_group
        from tools.ms94_b06_admission import EvidenceFailure
        with self.assertRaisesRegex(EvidenceFailure,'r11-withdrawn'):
            execute_group(None,{'content_sha256':'aa22263615aaaf143cf3eda22330fdfbba64dfc08a21dc017bd59e5b58522d9b'},
                          None,None,authority_root=None)
    def test_only_inventory_and_progress_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir()
            with zipfile.ZipFile(root/'a.jar','w') as z:z.writestr('A.class',b'class');z.writestr('lib/nested.jar',b'not-read')
            r=inventory([root],Path(tmp)/'out')
            self.assertEqual(r['class_bytes_copied'],0);self.assertEqual(r['artifacts'][0]['nested_archives'],1)
            self.assertFalse((Path(tmp)/'out/blobs').exists())
            with self.assertRaises(ValueError):inventory([root,root/'missing'],Path(tmp)/'failed')
            self.assertIn('a.jar',(Path(tmp)/'failed/progress.jsonl').read_text())
            self.assertTrue((Path(tmp)/'failed/inventory.json').exists())
    def test_scoped_runtime_requires_measured_artifact_bindings(self):
        from tools.b06_image_artifacts.resolved_runtime import read
        row=dict(path='/jdk/lib/modules',sha256='a'*64,bytes=99,class_entries=0,nested_archives=0)
        jar=dict(path='/app/runtime.jar',sha256='b'*64,bytes=99,class_entries=1,nested_archives=0)
        tool=dict(path='/jdk/bin/jimage',sha256='c'*64,bytes=99,class_entries=0,nested_archives=0)
        inv=dict(schema='b06-image-inventory/1',failure=None,artifacts=[row,jar,tool])
        config=b'osgi.bundles=reference:file:/app/runtime.jar@4:start\n'
        booter=b'classPathUrl.0=file:/app/runtime.jar\n'
        res=dict(schema='b06-resolved-runtime/1',resolved=True,**read(config,booter),
            configuration_utf8={'config.ini':config.decode(),'surefire.properties':booter.decode()},
            jdk_modules=row['path'],artifact_sha256={r['path']:r['sha256'] for r in (row,jar)},
            jdk_class_entries=7,expanded_byte_limit=1024,jimage_tool={'path':tool['path'],'sha256':tool['sha256']})
        self.assertEqual(assemble(inv,res)['maximum_classes'],8)
        res['artifact_sha256'][row['path']]='b'*64
        with self.assertRaises(ValueError):assemble(inv,res)
    def test_resolved_configuration_refuses_indirection_gaps_and_forged_paths(self):
        from tools.b06_image_artifacts.resolved_runtime import read
        good=b'osgi.bundles=reference:file:/app/runtime.jar@4:start'
        for config,booter in [(b'osgi.bundles=runtime.jar',b'classPathUrl.0=file:/app/runtime.jar'),
                              (good,b'classPathUrl.1=file:/app/runtime.jar'),
                              (good,b'classPathUrl.0=file:/app/../secret.jar')]:
            with self.subTest(config=config,booter=booter),self.assertRaises(ValueError):read(config,booter)
    def test_scoped_nested_jar_and_runtime_image_not_jmods(self):
        from tools.b06_image_artifacts.runtime_closure import extract
        from tools.b06_image_artifacts.inventory import digest
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);nested=io.BytesIO()
            with zipfile.ZipFile(nested,'w') as z:z.writestr('Hidden.class',b'NESTED')
            jar=p/'bundle.jar'
            with zipfile.ZipFile(jar,'w') as z:z.writestr('lib/inner.jar',nested.getvalue())
            modules=p/'modules';modules.write_bytes(b'BOUND RUNTIME IMAGE')
            tool=p/'jimage';tool.write_bytes(b'BOUND TOOL')
            closure=dict(schema='b06-runtime-closure/1',jdk_modules=str(modules),
                jimage_tool=dict(path=str(tool),sha256=digest(tool)),maximum_classes=2,
                maximum_expanded_bytes=4096,maximum_archive_bytes=4096,
                artifacts=[dict(path=str(f),sha256=digest(f),bytes=f.stat().st_size) for f in (jar,modules)])
            def run(argv,**kwargs):
                self.assertEqual(argv,[str(tool),'extract','--dir',str(p/'out/jimage'),str(modules)])
                (p/'out/jimage/Actual.class').write_bytes(b'RUNTIME')
                return subprocess.CompletedProcess(argv,0,b'',b'')
            result=extract(closure,p/'out',tool,run=run)
            self.assertEqual(result['jdk_source'],'lib/modules');self.assertEqual(len(result['classes']),2)
            self.assertIn('!/lib/inner.jar',result['classes'][0]['origin'])
            tool.write_bytes(b'CHANGED')
            with self.assertRaisesRegex(ValueError,'jimage-tool'):extract(closure,p/'changed',tool,run=run)
