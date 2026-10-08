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
    @staticmethod
    def jar_bytes():
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('Nested.class',b'counted')
        return b.getvalue()

    def test_withdrawn_r11_refuses_before_authority_or_execution(self):
        from tools.ms94_b06_qualification_driver import execute_group
        from tools.ms94_b06_admission import EvidenceFailure
        with self.assertRaisesRegex(EvidenceFailure,'r11-withdrawn'):
            execute_group(None,{'content_sha256':'aa22263615aaaf143cf3eda22330fdfbba64dfc08a21dc017bd59e5b58522d9b'},
                          None,None,authority_root=None)
    def test_only_inventory_and_progress_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir()
            with zipfile.ZipFile(root/'a.jar','w') as z:z.writestr('A.class',b'class');z.writestr('lib/nested.jar',self.jar_bytes())
            r=inventory([root],Path(tmp)/'out')
            self.assertEqual(r['class_bytes_copied'],0);self.assertEqual(r['artifacts'][0]['nested_archives'],1)
            self.assertFalse((Path(tmp)/'out/blobs').exists())
            with self.assertRaises(ValueError):inventory([root,root/'missing'],Path(tmp)/'failed')
            self.assertIn('a.jar',(Path(tmp)/'failed/progress.jsonl').read_text())
            self.assertTrue((Path(tmp)/'failed/inventory.json').exists())
    def test_scoped_runtime_requires_measured_artifact_bindings(self):
        import json,base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        from lightyear_control_tower.decisions import canonical,digest
        from tools.b06_image_artifacts.runtime_producer import produce,h
        private=Ed25519PrivateKey.generate()
        key=private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        def signed(body):
            return dict(body,content_sha256=digest(body),signature=dict(algorithm='Ed25519',
                key_id=h(key),value=base64.b64encode(private.sign(canonical(body))).decode()))
        row=dict(path='/jdk/lib/modules',sha256='a'*64,bytes=99,class_entries=0,nested_archives=0,
                 expanded_class_entries=7,expanded_class_bytes=1024)
        jar=dict(path='/app/runtime.jar',sha256='b'*64,bytes=99,class_entries=1,nested_archives=0)
        tool=dict(path='/jdk/bin/jimage',sha256='c'*64,bytes=99,class_entries=0,nested_archives=0)
        java=dict(path='/jdk/bin/java',sha256='d'*64,bytes=99,class_entries=0,nested_archives=0)
        inv=dict(schema='b06-image-inventory/1',failure=None,artifacts=[row,jar,tool,java])
        config=b'osgi.bundles=reference:file:/app/runtime.jar@4:start\n'
        booter=b'surefireClassPathUrl.0=file:/app/runtime.jar\n'
        obs=dict(schema='b06-runtime-launch-observation/1',bundles=[dict(id=0,state=32,location='system'),
            dict(id=1,state=4,location='reference:file:/app/runtime.jar')],framework_url='file:/app/runtime.jar',
            java_class_path='/app/runtime.jar',java_home='/jdk')
        raw=json.dumps(obs).encode()
        expected=dict(probe_sha256='e'*64,image='sha256:'+'f'*64,java_sha256=java['sha256'],
                      plan_sha256='1'*64,tower_decision_sha256='2'*64)
        receipt=signed(dict(schema='b06-runtime-launch-receipt/1',passed=True,bindings=expected,
            outputs={'observation':h(raw),'config.ini':h(config),'surefire.properties':h(booter),
                     'inventory':h(json.dumps(inv,sort_keys=True).encode())}))
        res=produce(raw,config,booter,inv,receipt,key,expected)
        closure=assemble(inv,res,launch_key=key,expected_launch=expected)
        self.assertEqual(closure['maximum_classes'],8)
        for fault in ('signature','observation','inventory','authority','state'):
            r=copy.deepcopy(res);i=copy.deepcopy(inv)
            if fault=='signature':r['launch_receipt']['signature']['value']='invalid'
            elif fault=='observation':r['observation_utf8']=r['observation_utf8'].replace('32','2')
            elif fault=='inventory':i['artifacts'][0]['sha256']='f'*64
            elif fault=='state':r['resolved_bundle_states'][1]['state']=2
            with self.subTest(fault=fault),self.assertRaises(ValueError):
                assemble(i,r,launch_key=None if fault=='authority' else key,expected_launch=expected)
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
            with zipfile.ZipFile(jar,'w') as z:
                z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nBundle-ClassPath: jars/inner.jar\n')
                z.writestr('jars/inner.jar',nested.getvalue())
            modules=p/'modules';modules.write_bytes(b'BOUND RUNTIME IMAGE')
            tool=p/'jimage';tool.write_bytes(b'BOUND TOOL')
            closure=dict(schema='b06-runtime-closure/1',jdk_modules=str(modules),
                jimage_tool=dict(path=str(tool),sha256=digest(tool)),maximum_classes=2,
                maximum_expanded_bytes=4096,maximum_archive_bytes=4096,
                artifacts=[dict(path=str(f),sha256=digest(f),bytes=f.stat().st_size) for f in (jar,modules)])
            def run(argv,**kwargs):
                self.assertEqual(argv,[str(tool),'extract','--dir',str(p/'out/jimage'),str(p/'out/bound-modules')])
                (p/'out/jimage/Actual.class').write_bytes(b'RUNTIME')
                return subprocess.CompletedProcess(argv,0,b'',b'')
            result=extract(closure,p/'out',tool,run=run)
            self.assertEqual(result['jdk_source'],'lib/modules');self.assertEqual(len(result['classes']),2)
            self.assertIn('!/jars/inner.jar',result['classes'][0]['origin'])
            tool.write_bytes(b'CHANGED')
            with self.assertRaisesRegex(ValueError,'jimage-tool'):extract(closure,p/'changed',tool,run=run)

class FullLinkageTests(unittest.TestCase):
    def test_complete_forwarding_stub_and_actual_linkage_adversaries(self):
        from b06_synthetic_classfiles import full_lambda_fixture
        from tools.ms94_b06_forwarding_stub import validate_stub
        from tools.ms94_b06_admission import EvidenceFailure
        raw,frame,target,classes=full_lambda_fixture()
        self.assertEqual(validate_stub(raw,frame,target,classes,{})['host_class'],target['class'])
        for fault in ('direct-hidden','host','loader','next-frame','extra-logic','changed-bootstrap'):
            r,f,t,c=copy.deepcopy((raw,frame,target,classes))
            if fault=='direct-hidden':r['generation']['record']['entry_method']='java.lang.invoke.MethodHandles$Lookup.defineHiddenClass'
            elif fault=='host':r['generation']['record']['lambda_factory']['targetClass']['class']='forged.Host'
            elif fault=='loader':r['generation']['definitions']['2']['loader']='attacker'
            elif fault=='next-frame':t=None
            elif fault=='extra-logic':
                r['bytecode_hex']='00'+r['bytecode_hex'];r['method_sha256']=hashlib.sha256(bytes.fromhex(r['bytecode_hex'])).hexdigest();f['method_sha256']=r['method_sha256']
            else:r['generation']['record']['stack'][0]['code_index']=1
            with self.subTest(fault=fault),self.assertRaises((ValueError,EvidenceFailure)):
                validate_stub(r,f,t,c,{})


class FolderClosureTests(unittest.TestCase):
    def test_folder_bundle_manifest_selects_non_lib_nested_jar_and_detects_mutation(self):
        from tools.b06_image_artifacts.runtime_closure import extract
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);bundle=p/'bundle';(bundle/'META-INF').mkdir(parents=True);(bundle/'jars').mkdir()
            (bundle/'META-INF/MANIFEST.MF').write_text('Manifest-Version: 1.0\nBundle-ClassPath: jars/a.jar\n')
            with zipfile.ZipFile(bundle/'jars/a.jar','w') as z:z.writestr('A.class',b'class')
            measured=inventory([bundle],p/'inventory')
            row=next(r for r in measured['artifacts'] if r.get('kind')=='folder-bundle')
            self.assertEqual(row['expanded_class_entries'],1)
            tool=p/'jimage';tool.write_bytes(b'not invoked')
            closure=dict(schema='b06-runtime-closure/1',jdk_modules='/not-selected',jimage_tool=dict(path=str(tool),sha256=hashlib.sha256(tool.read_bytes()).hexdigest()),
                         artifacts=[row],maximum_classes=1,maximum_expanded_bytes=4096,maximum_archive_bytes=row['bytes'])
            result=extract(closure,p/'extract',tool,run=lambda *a,**k:self.fail('no JVM extraction'))
            self.assertEqual(result['classes'][0]['member'],'A.class')
            (bundle/'extra.txt').write_text('changed')
            with self.assertRaisesRegex(ValueError,'folder-changed'):extract(closure,p/'changed',tool)
