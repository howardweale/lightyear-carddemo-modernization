"""Prospective integrity tests; host fixtures never count as native qualification."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from lightyear_calibration.contracts import canonical, seal
from tools.ms94_b06_admission import EvidenceFailure
from tools.ms94_b06_observer_v2 import Replay, commitments, load_manifest, POLICY, AMENDMENT, POOL_APPROVAL
from tools.ms94_b06_bytecode_policy import validate_jvm, JDWP
from tools.ms94_b06_runtime_files_probe import measure
from tools.ms94_b06_posting_replay import replay_stream
from test_ms94_b06_classfile import fixture
from tools.ms94_b06_classfile import inspect_class


def minimal():
    raw,pool=fixture(); info=inspect_class(raw)
    d={'class':'test.Fixture','class_object_id':7,'loader':'bootstrap','module':'java.base',
       'module_id':8,'module_loader':'bootstrap','loader_class':None,
       'modifiers':33,'signature':'Ltest/Fixture;','constant_pool_count':6,
       'constant_pool_hex':pool.hex(),'constant_pool_sha256':hashlib.sha256(pool).hexdigest(),
       'fields':[],'methods':[{'name':'f','signature':'()V','modifiers':9,
        'bytecode_hex':'b1','sha256':hashlib.sha256(b'\xb1').hexdigest()}]}
    row={'class':'test.Fixture','kind':'jdk','module':'java.base','origin':'/jdk/lib/modules',
         'bytes':raw,'sha256':hashlib.sha256(raw).hexdigest(),'methods':info['methods']}
    f={'class':d['class'],'class_object_id':7,'method':'f','signature':'()V','loader':'bootstrap',
       'constant_pool_sha256':d['constant_pool_sha256'],'method_sha256':d['methods'][0]['sha256']}
    return row,d,f


class ClosedPolicyTests(unittest.TestCase):
    def test_all_frames_need_individual_origin_and_method_binding(self):
        row,d,f=minimal();r=Replay([row]);r.event({'kind':'class-definition-v2','definition':d})
        self.assertEqual(r.frames([f]),[f]);self.assertEqual(r.finish()['frames_verified'],1)
        for key,value in [('loader','candidate'),('class','java.lang.Forged'),('method_sha256','f'*64)]:
            bad=dict(f);bad[key]=value
            with self.subTest(key=key),self.assertRaises((ValueError,KeyError)):r.frames([bad])

    def test_jdk_name_or_loader_id_alone_is_insufficient(self):
        for change in ('module','loader','module-id','member-code'):
            row,d,f=minimal()
            if change=='module':d['module']='unapproved'
            elif change=='loader':d['loader']=f['loader']='17';d['module_loader']='17';d['loader_class']='fake.PlatformClassLoader'
            elif change=='module-id':d.pop('module_id')
            else:row['methods']={'f()V':'0'*64}
            r=Replay([row]);r.event({'kind':'class-definition-v2','definition':d})
            with self.subTest(change=change),self.assertRaises(ValueError):r.frames([f])

    def test_native_and_abstract_access_flags_are_not_unavailable_strings(self):
        row,d,f=minimal();d['methods'][0]['modifiers']=0x400;d['methods'][0].pop('bytecode_hex');d['methods'][0].pop('sha256');f['method_sha256']='unavailable'
        r=Replay([row]);r.event({'kind':'class-definition-v2','definition':d})
        with self.assertRaisesRegex(ValueError,'flags|abstract'):r.frames([f])

    def test_generation_lifecycle_and_identity_are_not_signed_assertions(self):
        r=Replay([]);record={'thread_id':2,'entry_depth':3,'entry_method':'test.method()V'}
        r.event({'kind':'generation-entry','record':record})
        with self.assertRaisesRegex(ValueError,'open-generation'):r.finish()
        with self.assertRaisesRegex(ValueError,'return-binding'):
            r.event({'kind':'generation-return','record':{**record,'entry_depth':4}})

    def test_complete_chain_requires_v2_collector_and_receipt_commitments(self):
        row,d,f=minimal()
        events=[{'kind':'ready','binding_version':2,'checkpoint':False},
                {'kind':'class-definition-v2','definition':d,'checkpoint':False},
                {'kind':'exception','checkpoint':True,'thread':1,'frames':[f],
                 'exception_class':'java.lang.Throwable','exception_ancestry':['java.lang.Throwable','java.lang.Object'],
                 'unwound_calls':[],'catch_location':None},
                {'kind':'vm-death','checkpoint':False}]
        records=[];prev=None
        for n,e in enumerate(events,1):
            record=seal({'event':{**e,'sequence':n},'previous_sha256':prev,'readback_sha256':None});prev=record['content_sha256'];records.append(record)
        data=b''.join(canonical(r)+b'\n' for r in records)
        receipt={'event_file_sha256':hashlib.sha256(data).hexdigest(),'event_count':4,'last_event_sha256':prev,'v2_records':commitments(records)}
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'events.jsonl').write_bytes(data)
            result=replay_stream(folder,receipt,{},'oracle',binding_v2=Replay([row]))
            self.assertEqual(result['observer_v2']['frames_verified'],1)
            receipt['v2_records']=[]
            with self.assertRaisesRegex(ValueError,'commitments'):replay_stream(folder,receipt,{},'oracle',binding_v2=Replay([row]))

    def test_patches_and_native_injection_fail_even_in_declared_argv(self):
        for injection in ('--patch-module=java.base=evil','-Xbootclasspath/a:evil','--upgrade-module-path=evil',
                          '-Djava.library.path=evil','-Djava.system.class.loader=evil','-agentpath:evil'):
            args=['java',JDWP,injection,'-jar','launcher.jar']
            spec={'bytecode_policy':'untransformed-classes-jdwp-only-v1','java_binary_sha256':'a'*64,
                  'observer_binding_v2':{},'expected_jvm_arguments':args}
            owner={'java_binary_sha256':'a'*64,'arguments':args,'jvm_option_environment_present':[]}
            with self.subTest(injection=injection),self.assertRaises(ValueError):validate_jvm(owner,spec)

    def test_runtime_probe_requires_actual_bytes_and_absent_files_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'public';p.write_bytes(b'public');files={str(p):hashlib.sha256(b'public').hexdigest()}
            self.assertEqual(measure(files),files);p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'differ'):measure(files)
            p.unlink()
            with self.assertRaisesRegex(ValueError,'missing'):measure(files)

    def test_manifest_binds_policy_image_runtime_and_each_entry(self):
        raw,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'Fixture.class').write_bytes(raw)
            manifest={'schema':'b06-observer-bindings/2','amendment_sha256':AMENDMENT,'pool_approval_sha256':POOL_APPROVAL,
                'image':'sha256:'+'a'*64,'runtime_files':{'/jdk/bin/java':'b'*64,'/jdk/lib/modules':'c'*64,'/jdk/release':'d'*64,'/jdk/lib/libjava.so':'e'*64,'/jdk/lib/server/libjvm.so':'f'*64},
                'jdk':{'java':'/jdk/bin/java','modules':'/jdk/lib/modules','release':'/jdk/release','native_providers':['/jdk/lib/libjava.so','/jdk/lib/server/libjvm.so']},
                'classes':[{'path':'Fixture.class','sha256':hashlib.sha256(raw).hexdigest(),'class':'test.Fixture',
                    'kind':'jdk','module':'java.base','origin':'/jdk/lib/modules','members':['java.base/test/Fixture.class']}]}
            def call(value):
                body=json.dumps(value).encode();(root/'manifest.json').write_bytes(body)
                spec={'java_binary_sha256':'b'*64,'expected_jvm_arguments':['java',JDWP], 'observer_binding_v2':{'policy':POLICY,'path':'manifest.json','sha256':hashlib.sha256(body).hexdigest()}}
                return load_manifest(root,spec,'sha256:'+'a'*64)
            self.assertEqual(len(call(manifest)[1]),1)
            for mutate in ('policy','image','entry','release'):
                bad=copy.deepcopy(manifest)
                if mutate=='policy':bad['amendment_sha256']='f'*64
                elif mutate=='image':bad['image']='sha256:'+'f'*64
                elif mutate=='entry':bad['classes'][0]['members']=['other.class']
                else:bad['runtime_files'].pop('/jdk/release')
                with self.subTest(mutate=mutate),self.assertRaises(ValueError):call(bad)


CAPTURE=os.environ.get('B06_OBSERVER_V2_CAPTURE')
@unittest.skipUnless(CAPTURE,'actual host collector evidence explicitly selected')
class ActualCollectorAdversarialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.b06_host_probe.replay_native_observer_host import inputs
        cls.events=[json.loads(l) for l in Path(CAPTURE).read_text().splitlines()]
        cls.rows,_=inputs(cls.events,os.environ['B06_OBSERVER_V2_CLASSES'],os.environ['B06_HOST_JDK'],os.environ['B06_OBSERVER_V2_MODULES'])

    def call(self, events):
        from tools.b06_host_probe.replay_native_observer_host import replay
        return replay(events, self.rows)

    def test_actual_external_capture_and_both_method_handle_paths(self):
        result=self.call(self.events)
        self.assertEqual(result['checkpoints_replayed'],10)
        self.assertEqual({p['kind'] for p in result['generated_proofs']},{'lambda','lambda-form'})
        self.assertEqual({p['host'] for p in result['generated_proofs'] if p['kind']=='lambda'},
            {'org.idempiere.test.LightyearOperationsTest','org.idempiere.test.JourneySupport','org.idempiere.test.B06OutsideControl'})
        self.assertFalse(result['native_qualification'])

    def test_missing_younger_target_is_not_replaced_by_deeper_candidate(self):
        events=copy.deepcopy(self.events)
        e=next(e for e in events if e['kind']=='method-entry')
        i=next(i for i,f in enumerate(e['frames']) if '/' in f['class']);del e['frames'][i-1]
        with self.assertRaises(ValueError):self.call(events)

    def test_wrong_host_loader_or_returned_class_fails(self):
        for field in ('host','loader','returned-class'):
            events=copy.deepcopy(self.events)
            for e in events:
                if e['kind'] in ('generation-entry','generation-return') and 'lambda_factory' in e['record']:
                    r=e['record']
                    if field=='host':r['lambda_factory']['targetClass']['class']='wrong.Host'
                    elif field=='loader':r['lambda_factory']['targetClass']['loader']='wrong-loader'
                    elif 'returned_class' in r:r['returned_class']['class_object_id']=-1
            with self.subTest(field=field),self.assertRaises((ValueError,KeyError)):self.call(events)

    def test_extra_lambda_logic_even_with_recomputed_hash_fails(self):
        events=copy.deepcopy(self.events)
        d=next(e['definition'] for e in events if e['kind']=='class-definition-v2' and '$$Lambda/' in e['definition']['class'])
        method=next(m for m in d['methods'] if m['name']!='<init>')
        method['bytecode_hex']='00'+method['bytecode_hex'];method['sha256']=hashlib.sha256(bytes.fromhex(method['bytecode_hex'])).hexdigest()
        for e in events:
            for f in e.get('frames',[]):
                if f['class_object_id']==d['class_object_id'] and f['method']==method['name']:f['method_sha256']=method['sha256']
        with self.assertRaises(ValueError):self.call(events)

    def test_missing_use_graph_and_opaque_target_fail(self):
        for change in ('missing','opaque'):
            events=copy.deepcopy(self.events)
            for e in events:
                for f in e.get('frames',[]):
                    if '/0x' not in f['class'] or not f['class'].startswith('java.lang.invoke.LambdaForm'):continue
                    if change=='missing':f['handle_uses']=[]
                    else:
                        for u in f.get('handle_uses',[]):u['handle_graph']={'root':'opaque','nodes':{'opaque':{'class':'unknown','opaque':True}}}
            with self.subTest(change=change),self.assertRaises(ValueError):self.call(events)

    def test_wrong_class_source_and_loader_do_not_bind(self):
        events=copy.deepcopy(self.events)
        for e in events:
            if e['kind'] in ('generation-entry','generation-return') and e['record'].get('kind')=='ordinary-definition':
                e['record']['code_source']['file']='/wrong/source/'
        with self.assertRaisesRegex(ValueError,'origin'):self.call(events)

    def test_captured_storage_field_does_not_admit_its_methods(self):
        r=Replay(self.rows)
        for e in self.events:
            if r.event(e):continue
            if e.get('frames'):r.frames(e['frames'])
        self.assertTrue(r.captured_fields)
        identity=next(iter(r.captured_fields))[0]
        with self.assertRaises(ValueError):r.ordinary_binding(identity)
        klass={'class_object_id':int(identity),'loader':r.definitions[identity]['loader']}
        owner=r.definitions[identity]['class']
        for kind in (2,3,4,5,6,7,8,9):
            with self.subTest(kind=kind),self.assertRaises(ValueError):r.captured_field(klass,(kind,owner,'argI1','I'))

    def test_reviewed_pool_rule_is_used_by_native_ordinary_binding(self):
        from tools.b06_host_probe.generation_replay import declared_definition
        area=os.environ.get('B06_REVIEWED_POOL_EVIDENCE')
        if not area:self.skipTest('retained reviewed pool evidence not selected')
        area=Path(area)
        source=(area/'pool-probe-inputs/surefire59/org/junit/platform/engine/support/hierarchical/HierarchicalTestEngine.class').read_bytes()
        interface=(area/'pool-probe-inputs/surefire59/org/junit/platform/engine/TestEngine.class').read_bytes()
        for path in ('surefire59-baseline/observations.json','platform191-none-experiment/observations/observations.json'):
            d=json.loads((area/path).read_text())['samples'][0]['definition']
            self.assertEqual(declared_definition(source,d,test_engine=interface)['name'],
                             'org/junit/platform/engine/support/hierarchical/HierarchicalTestEngine')
            bad=copy.deepcopy(d);bad['constant_pool_hex']='00'+bad['constant_pool_hex'][2:]
            bad['constant_pool_sha256']=hashlib.sha256(bytes.fromhex(bad['constant_pool_hex'])).hexdigest()
            with self.assertRaises(ValueError):declared_definition(source,bad,test_engine=interface)
        r=Replay(self.rows)
        for e in self.events:
            if e['kind']=='class-definition-v2':r.event(e)
        ordinary=next(e['record'] for e in self.events if e['kind']=='generation-return' and e['record'].get('kind')=='ordinary-definition')
        record=copy.deepcopy(ordinary);runtime=copy.deepcopy(d)
        identity=999999;runtime.update(class_object_id=identity,loader=ordinary['defining_loader'],
            module=None,module_loader=ordinary['defining_loader'],loader_class='jdk.internal.loader.ClassLoaders$AppClassLoader',
            loader_class_object_id=next(int(k) for k,v in r.definitions.items() if v['class']=='jdk.internal.loader.ClassLoaders$AppClassLoader'))
        name=runtime['class'];record.update(definition_input_hex=source.hex(),definition_input_sha256=hashlib.sha256(source).hexdigest(),
            requested_name=name,returned_class={'class_object_id':identity,'class':name,'loader':runtime['loader']},
            code_source={'protocol':'file','host':'','port':'-1','file':'/bound/surefire.jar'})
        info=inspect_class(source)
        r.entries.extend([{'class':name,'kind':'ordinary','origin':'/bound/surefire.jar','code_source':'/bound/surefire.jar',
            'loader_class':runtime['loader_class'],'bytes':source,'sha256':hashlib.sha256(source).hexdigest(),'methods':info['methods']},
            {'class':'org.junit.platform.engine.TestEngine','bytes':interface}])
        r.definitions[str(identity)]=runtime;r.ordinary[str(identity)]=record
        self.assertEqual(r.ordinary_binding(identity)['class_sha256'],hashlib.sha256(source).hexdigest())

    def test_definition_refresh_cannot_reuse_an_earlier_generated_proof(self):
        r=Replay(self.rows)
        checkpoint=None
        for e in self.events:
            if r.event(e):continue
            if e.get('frames'):
                r.frames(e['frames'])
                if any('/' in f['class'] and f['class'].startswith('java.lang.invoke.LambdaForm') for f in e['frames']):
                    checkpoint=e;break
        self.assertTrue(r.dispatch_definitions)
        identity=next(iter(r.dispatch_definitions));bad=copy.deepcopy(r.definitions[identity])
        method=next(m for m in bad['methods'] if m['name']!='<clinit>')
        method['bytecode_hex']='00'+method['bytecode_hex'];method['sha256']=hashlib.sha256(bytes.fromhex(method['bytecode_hex'])).hexdigest()
        r.event({'kind':'class-definition-v2','definition':bad})
        self.assertFalse(r.dispatch_definitions)
        with self.assertRaises(ValueError):r.frames(checkpoint['frames'])

    def test_wrong_or_mutated_field_layout_fails(self):
        events=copy.deepcopy(self.events)
        for e in events:
            if e['kind']=='class-definition-v2' and e['definition']['class'].endswith('BoundMethodHandle$Species_LI'):
                e['definition']['fields'][0]['modifiers']=0
        with self.assertRaises(ValueError):self.call(events)


if __name__=='__main__':unittest.main()
