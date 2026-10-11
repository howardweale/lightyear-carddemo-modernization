import base64
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lightyear_calibration.contracts import seal, digest
from tools import ms94_b06_engineering as e
from tools import ms94_b06_oct13_authorization as gate
from tools import ms94_b06_observer_diagnostics as d
from tools.ms94_b06_generation_inputs import validate as inputs
from tools.b06_host_probe.alternatives_partition import classify


def reseal(value,**changes):return seal({**{k:v for k,v in value.items() if k!='content_sha256'},**changes})

def request(root):
    value=e.instrumented_proposal(*gate.WINDOW,[],[str(root/'evidence')],root/'b06-engineering',
        implementation_commit='a'*40,native_template_sha256='b'*64,observer_source_sha256='c'*64,
        observer_class_files_sha256={('PostingObserver.class' if i==0 else 'PostingObserver$'+str(i)+'.class'):'d'*64 for i in range(14)},full_plan_delivered_at_utc='2026-10-12T23:00:00Z')
    memory=dict(observer_source_sha256='c'*64,compiled_observer_sha256=value['observer_class_files_sha256'],
        accepted=True,completed=True,host_only=True,heap_bytes=192*1024**2,generation_entries=40000,
        growth_fit=dict(significantly_positive=False,warmup_events=50000,sample_count=50,slope_95_percent=[-.1,.1]),
        input_witnesses=dict(missing=0,validated_generation_entries=40000))
    return reseal(value,memory_gate=True,host_memory_validation=memory,artifact_type=gate.SCHEMA,attempt_limits=[e.attempt_limits(1),e.attempt_limits(2)],
        cause_identified_criteria=gate.CAUSE_CRITERIA,class_input_witness_policy='generation-inputs-v1',
        automatic_second_attempt=False,stop_after_two=True,
        asset_index_sha256='e'*64,asset_index_file_sha256='f'*64,cap_projection_sha256='1'*64,host_witness_validation_sha256=digest(memory),mirror_adapter_source_sha256='3'*64,
        source_change_reason='B3.4 genuine generation-input witnesses and attempt2 metadata caps; baseline observer preserved',
        observer_source_baseline_sha256='02b2f7fd4080bfbcd821ef51147c455d7f57620eac797b809d406d73f935c64b')

class Oct13GateTests(unittest.TestCase):
    def test_exact_go_clean_implementation_and_context_expiry(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);value=request(root);path=root/'request.json';e.write_new(path,value)
            with patch('tools.ms94_b06_engineering_run.source_commit',return_value='a'*40):
                with self.assertRaisesRegex(ValueError,'exact-howard-go'): 
                    with gate.authorized(path,e.sha(path),'approve'):pass
                with self.assertRaisesRegex(ValueError,'file-changed'):
                    with gate.authorized(path,'f'*64,gate.expected_go(value)):pass
                with gate.authorized(path,e.sha(path),gate.expected_go(value)):
                    e.require_execution_ready(value);e.approve_check(value,e.sha(path),path)
                    with self.assertRaisesRegex(ValueError,'request-mismatch'):gate.require_active(reseal(value,extra=True))
                with self.assertRaisesRegex(ValueError,'on-hold'):e.require_execution_ready(value)
            with patch('tools.ms94_b06_engineering_run.source_commit',return_value='e'*40):
                with self.assertRaisesRegex(ValueError,'implementation-commit'):
                    with gate.authorized(path,e.sha(path),gate.expected_go(value)):pass

    def test_native_relative_class_paths_match_host_compilation_basenames(self):
        with tempfile.TemporaryDirectory() as temp:
            value=request(Path(temp))
            value=reseal(value,observer_class_files_sha256={'lightyear/observer/'+n:h for n,h in value['observer_class_files_sha256'].items()})
            gate.validate_request(value)

    def test_failed_memory_stays_blocked_even_with_exact_go(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);value=request(root);memory=copy.deepcopy(value['host_memory_validation'])
            memory.update(accepted=False);memory['growth_fit'].update(significantly_positive=True,slope_95_percent=[.03,.32])
            blocked=reseal(value,memory_gate=False,host_memory_validation=memory,host_witness_validation_sha256=digest(memory))
            gate.validate_request(blocked)
            path=root/'blocked.json';e.write_new(path,blocked)
            with self.assertRaisesRegex(ValueError,'memory-gate-unmet'):
                with gate.authorized(path,e.sha(path),gate.expected_go(blocked)):pass
            with self.assertRaisesRegex(ValueError,'memory-gate-evidence'):gate.validate_request(reseal(blocked,memory_gate=True))
            changed=copy.deepcopy(value['host_memory_validation']);changed['observer_source_sha256']='f'*64
            with self.assertRaisesRegex(ValueError,'implementation-binding'):
                gate.validate_request(reseal(value,host_memory_validation=changed,host_witness_validation_sha256=digest(changed)))

    def test_entire_asset_index_is_checked_before_template_use(self):
        from tools.ms94_b06_engineering_run import template
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);assets=root/'assets';assets.mkdir();(assets/'templates').mkdir()
            source=assets/'templates/plan.json';base=seal({'fixture':True});e.write_new(source,base)
            helper=assets/'factory/idempiere/b06-observer/BoundedJdiMirrors.java';helper.parent.mkdir(parents=True);helper.write_text('public fixture')
            inherited=assets/'runtime.jar';inherited.write_bytes(b'original')
            index=seal(dict(implementation_commit='a'*40,native_template_sha256='b'*64,
                observer_class_files_sha256={},mirror_adapter_source_sha256=e.sha(helper),
                files_sha256={p.relative_to(assets).as_posix():e.sha(p) for p in (source,helper,inherited)}))
            index_path=assets/'engineering-assets-index.json';e.write_new(index_path,index)
            req=dict(artifact_type=gate.SCHEMA,asset_index_sha256=index['content_sha256'],asset_index_file_sha256=e.sha(index_path),
                implementation_commit='a'*40,native_template_sha256='b'*64,observer_class_files_sha256={},mirror_adapter_source_sha256=e.sha(helper))
            inherited.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'bound-file-changed'):
                template(assets,source,req)
            inherited.write_bytes(b'original');(assets/'unlisted.py').write_text('bad')
            with self.assertRaisesRegex(ValueError,'asset-inventory'):
                template(assets,source,req)

    def test_report_template_never_claims_native_outcome(self):
        from tools.ms94_b06_oct13_report import template
        with tempfile.TemporaryDirectory() as temp:
            r=template(request(Path(temp)))
            self.assertFalse(r['cause_identified']);self.assertFalse(r['native_run_authorized'])
            self.assertEqual([a['status'] for a in r['attempts']],['not-run','not-run'])
            self.assertTrue(all(a['generation_entries'] is None for a in r['attempts']))

    def test_window_delivery_caps_and_criteria_are_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            value=request(Path(temp));gate.validate_request(value)
            for change in ({'deadline_utc':'2026-10-13T19:01:00Z'},
                           {'full_plan_delivered_at_utc':'2026-10-13T00:00:01Z'},
                           {'attempt_limits':[e.attempt_limits(2)]*2},
                           {'cause_identified_criteria':{}},{'approved':True},
                           {'automatic_second_attempt':True},{'run_cap':3}):
                with self.subTest(change=change),self.assertRaises(ValueError):gate.validate_request(reseal(value,**change))

    def test_application_boundary_binds_reserved_attempt_before_docker(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from tools.ms94_b06_observed_runner import ObservedRunner
        class BeforeCreate(Exception):pass
        for number in (1,2):
            with self.subTest(number=number),tempfile.TemporaryDirectory() as t:
                root=Path(t);approval=request(root);runs=Path(approval['output_root'])/approval['content_sha256']/'runs'
                for i in range(1,number+1):(runs/('journey-'+str(i)*32)).mkdir(parents=True)
                run=runs/('journey-'+str(number)*32);mode=approval['attempt_modes'][number-1]
                e.write_new(run/'engineering.json',seal(dict(**e.LABEL,run_number=number,owner=run.name,
                    approval_sha256=approval['content_sha256'],source_commit=approval['implementation_commit'],
                    runtime_source_commit=approval['observer_source'],engineering_key_sha256=approval['engineering_key_sha256'],mode=mode)))
                plan=seal(dict(**e.LABEL,engineering_approval_sha256=approval['content_sha256'],
                    engineering_key_sha256=approval['engineering_key_sha256'],engineering_template_sha256=approval['native_template_sha256'],
                    engineering_limits=e.attempt_limits(number),posting_observer=dict(native_diagnostics=d.configuration(mode),
                    class_files_sha256=approval['observer_class_files_sha256']),local=dict(runner_image='fixture-image')))
                source=run/'inputs/operations.java';source.parent.mkdir();source.write_bytes(b'fixture')
                runner=SimpleNamespace(run=run,root=root,owner=run.name,plan=plan,approval=approval,
                    label='fixture-label',network='fixture-network',remember=Mock())
                payload=dict(lane='oracle',test='LightyearOperationsTest',output='/output/results',harness_sha256=e.sha(source))
                # Altered caps, CPU, memory and mode all refuse before staging/create.
                bads=[reseal(plan,engineering_limits={**plan['engineering_limits'],name:value})
                      for name,value in (('audit_records',1500001),('application_cpus',5),('application_memory_mib',8193))]
                bads.append(reseal(plan,engineering_limits=e.attempt_limits(3-number)))
                wrong=copy.deepcopy(plan['posting_observer']);wrong['native_diagnostics']=d.configuration(approval['attempt_modes'][2-number])
                bads.append(reseal(plan,posting_observer=wrong))
                for bad in bads:
                    runner.plan=bad
                    with patch('tools.ms94_b06_observed_runner.docker') as docker,self.assertRaises(ValueError):
                        ObservedRunner.worker(runner,'execute',payload,1800)
                    docker.assert_not_called();self.assertFalse((run/'application-output').exists())
                runner.plan=plan
                with patch('tools.ms94_b06_observed_runner.docker',side_effect=BeforeCreate) as docker:
                    with self.assertRaises(BeforeCreate):ObservedRunner.worker(runner,'execute',payload,1800)
                args=docker.call_args.args
                self.assertEqual(args[0],'create');self.assertEqual(args[args.index('--memory')+1],'8192m')
                self.assertEqual(args[args.index('--cpus')+1],'4')

    def test_expanded_caps_only_diagnostic_and_exact_java_values(self):
        def plan(mode,limits):return dict(run_class='engineering',qualification_credit=False,measurement_credit=False,
            engineering_limits=limits,posting_observer={'native_diagnostics':d.configuration(mode)})
        strict=plan('strict',e.attempt_limits(1));diagnostic=plan('diagnostic-unmatched-return',e.attempt_limits(2))
        self.assertEqual(d.validate(strict)['mode'],'strict')
        self.assertIn('-Db06.observer.audit_records=1500000',d.java_options(diagnostic))
        self.assertIn('-Db06.observer.audit_bytes=402653184',d.java_options(diagnostic))
        self.assertFalse(any('audit_records' in x for x in d.java_options(strict)))
        with self.assertRaises(ValueError):d.validate(plan('strict',e.attempt_limits(2)))
        with self.assertRaises(ValueError):d.validate(plan('diagnostic-unmatched-return',{**e.attempt_limits(2),'audit_records':1500001}))
        from tools.ms94_b06_observer_audit import Audit
        a=Audit(diagnostic);self.assertEqual((a.max_events,a.max_bytes),(1500000,402653184))
        self.assertEqual(Audit().max_events,500000)

class EngineeringEvidenceTests(unittest.TestCase):
    def setUp(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        from lightyear_workflow.campaign_engine import Signer
        from tools import ms94_b06_engineering_key as key
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        signer=Signer.__new__(Signer);signer.key=Ed25519PrivateKey.generate()
        self.public=signer.public=signer.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        self.signer=e.EngineeringSigner(signer)
        pin=patch.object(key,'ENGINEERING_KEY_SHA256',hashlib.sha256(self.public).hexdigest());pin.start();self.addCleanup(pin.stop)
        self.approval=request(self.root);self.assets=self.root/'assets'
        self.ledger=e.Ledger(Path(self.approval['output_root']),self.approval,self.public)
        self.guard=patch.object(e,'guard');self.guard.start();self.addCleanup(self.guard.stop)
        self.run=self.ledger.reserve('a'*40)
        self.base=seal(dict(posting_observer=dict(class_files_sha256=self.approval['observer_class_files_sha256']),
            inputs_sha256={},declaration=dict(environment=dict(engines=dict(oracle=dict(image_digest='approved-oracle')))),
            local=dict(runner_image='approved-carrier')))
        from tools.ms94_b06_engineering_run import derived_plan
        self.plan=derived_plan(self.base,self.run,self.approval);e.write_new(self.run/'plan.json',self.plan)
        self.handoff()

    def handoff(self):
        from tools.ms94_b06_engineering_evidence import binding
        value=self.signer.sign(dict(**binding(self.run,self.approval),artifact_type='b06-engineering-handoff/1',
            assets_root=str(self.assets.resolve()),template_path='templates/j1/plan.json',
            asset_index_sha256=self.approval['asset_index_sha256'],native_template_sha256=self.approval['native_template_sha256']))
        (self.run/'supervisor-handoff.json').write_bytes(e.canonical(value)+b'\n')

    def finish(self):
        from tools.ms94_b06_engineering_evidence import binding
        bound=binding(self.run,self.approval)
        e.write_new(self.run/'cleanup.json',self.signer.sign(dict(**bound,complete=True,actual_absence_verified=True)))
        e.write_new(self.run/'terminal.json',self.signer.sign(dict(**bound,cleanup_verified=True,outcome='refused',
            cleanup_record='cleanup.json',cleanup_record_sha256=e.sha(self.run/'cleanup.json'))))
        e.seal_artifacts(self.run,self.signer,self.approval)

    def test_complete_plan_not_just_selected_fields_and_handoff(self):
        from tools.ms94_b06_engineering_run import verify_prepared_run
        with patch('tools.ms94_b06_engineering_run.template',return_value=self.base) as template:
            self.assertEqual(verify_prepared_run(self.assets,self.run,self.approval,self.public),self.plan)
            template.assert_called_once()
            for field in ('oracle','carrier'):
                changed=copy.deepcopy(self.plan)
                if field=='oracle':changed['declaration']['environment']['engines']['oracle']['image_digest']='changed'
                else:changed['local']['runner_image']='changed'
                changed=reseal(changed);(self.run/'plan.json').write_bytes(e.canonical(changed))
                with self.assertRaisesRegex(ValueError,'receipt-binding'):
                    verify_prepared_run(self.assets,self.run,self.approval,self.public)
                # Even a freshly signed handoff cannot make a different derived
                # plan agree with the exact approved template.
                self.handoff()
                with self.assertRaisesRegex(ValueError,'complete-prepared-plan'):
                    verify_prepared_run(self.assets,self.run,self.approval,self.public)
                (self.run/'plan.json').write_bytes(e.canonical(self.plan));self.handoff()

    def test_worker_rejects_changed_plan_before_private_signer_or_native(self):
        from types import SimpleNamespace
        from tools import ms94_b06_engineering_worker as w
        args=SimpleNamespace(run=str(self.run),assets=str(self.assets),authority='test-only',approval=str(self.root/'request.json'),approved_sha256='f'*64)
        e.write_new(args.approval,self.approval);(Path(self.approval['output_root'])/'active.lock').write_text(self.approval['content_sha256'])
        changed=copy.deepcopy(self.plan);changed['local']['runner_image']='changed';(self.run/'plan.json').write_bytes(e.canonical(reseal(changed)))
        with patch.object(e,'require_execution_ready'),patch('argparse.ArgumentParser.parse_args',return_value=args),patch.object(w,'approve_check'),patch.object(w,'guard'), \
                patch('tools.ms94_b06_engineering_run.source_commit',return_value='a'*40), \
                patch('tools.ms94_b06_engineering_key.read_public',return_value=self.public), \
                patch('tools.ms94_b06_engineering_key.DedicatedEngineeringSigner') as signer, \
                patch('tools.ms94_b06_engineering_native.execute') as native:
            with self.assertRaisesRegex(ValueError,'receipt-binding'):w.main()
            signer.assert_not_called();native.assert_not_called()

    def test_authenticated_failed_attempt_consumed_and_tampering_blocks_next(self):
        from tools.ms94_b06_engineering_evidence import verify_prior
        self.finish();verify_prior(self.run,self.approval,self.public)
        saved={p.name:p.read_bytes() for p in self.run.iterdir() if p.is_file()}
        cases=[('terminal.json','cleanup_verified',False),('terminal.json','mode','diagnostic-unmatched-return'),
               ('cleanup.json','actual_absence_verified',False),('artifacts.json','owner','journey-'+'0'*32),
               ('engineering.json','run_number',2),('plan.json','extra','changed')]
        for name,key,value in cases:
            with self.subTest(name=name,key=key):
                data=e.read_json(self.run/name);data[key]=value;(self.run/name).write_bytes(e.canonical(data))
                with self.assertRaises(ValueError):self.ledger.reserve('a'*40)
                self.assertEqual(len(list((self.ledger.session/'runs').glob('journey-*'))),1)
                (self.run/name).write_bytes(saved[name])
        extra=self.run/'unlisted';extra.write_bytes(b'new')
        with self.assertRaisesRegex(ValueError,'artifact-inventory'):self.ledger.reserve('a'*40)
        extra.unlink()
        second=self.ledger.reserve('a'*40)
        self.assertEqual(e.read_json(second/'engineering.json')['run_number'],2)
        with self.assertRaisesRegex(ValueError,'run-cap-exhausted'):self.ledger.reserve('a'*40)

    def test_forged_cleanup_even_with_resealed_artifact_inventory_refused(self):
        self.finish()
        cleanup=e.read_json(self.run/'cleanup.json');cleanup['actual_absence_verified']=False
        (self.run/'cleanup.json').write_bytes(e.canonical(cleanup))
        # An attacker can recompute hashes/self-seals, but cannot authenticate
        # either changed cleanup or the aggregate with the approved public key.
        art=e.read_json(self.run/'artifacts.json')
        for row in art['artifacts']:
            if row['path']=='cleanup.json':row.update(sha256=e.sha(self.run/'cleanup.json'),bytes=(self.run/'cleanup.json').stat().st_size)
        (self.run/'artifacts.json').write_bytes(e.canonical(reseal(art)))
        with self.assertRaisesRegex(ValueError,'receipt-signature'):self.ledger.reserve('a'*40)

class GenerationInputTests(unittest.TestCase):
    def test_real_input_paths_classify_without_stack(self):
        ref=dict(class_object_id=2,**{'class':'example.Customer','loader':'17','signature':'Lexample/Customer;'})
        row={'entry_method':'java.lang.invoke.InvokerBytecodeGenerator.generateCustomizedCodeBytes()[B',
             'class_input_witness':dict(policy='generation-inputs-v1',kind='class-objects',
                inputs={'receiver.invokerType.rtype':ref,'receiver.invokerType.ptypes':[]})}
        self.assertEqual(inputs(row),[ref]);self.assertEqual(classify(row),('application-derived-input',1))
        bad=copy.deepcopy(row);bad['class_input_witness']['inputs']={'stack.caller':ref}
        with self.assertRaisesRegex(ValueError,'field-paths'):inputs(bad)
        noinput={'entry_method':row['entry_method'],'stack':[ref]}
        self.assertEqual(classify(noinput),('unresolved-no-class-input-witness',0))

    def test_bytecode_witness_is_not_class_identity_and_binds_exact_bytes(self):
        raw=b'class fixture';digest=hashlib.sha256(raw).hexdigest()
        row=dict(entry_method='java.lang.ClassLoader.defineClass(...)',definition_input_base64=base64.b64encode(raw).decode(),
            definition_input_sha256=digest,defining_loader='33',class_input_witness=dict(policy='generation-inputs-v1',
                kind='classfile-bytes',sha256=digest,bytes=len(raw),defining_loader='33',classification='unresolved-bytecode-input-only'))
        self.assertEqual(inputs(row),[]);self.assertEqual(classify(row),('unresolved-bytecode-input-only',0))
        for change in ({'sha256':'0'*64},{'bytes':len(raw)+1},{'defining_loader':'34'},
                       {'classification':'application-derived-input'}):
            bad=copy.deepcopy(row);bad['class_input_witness'].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):inputs(bad)

class HostWitnessReportTests(unittest.TestCase):
    def test_missing_input_is_not_hidden_by_existing_stack(self):
        import json
        from tools.b06_host_probe.oct13_host_validation import witness_counts
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'events.jsonl'
            p.write_text(json.dumps(dict(kind='generation-entry',entry_method='unknown',stack=[{'class':'example.Customer'}]))+'\n')
            with self.assertRaises(ValueError):witness_counts(p)

    def test_host_envelope_uses_nested_generation_record(self):
        import json
        from tools.b06_host_probe.oct13_host_validation import witness_counts
        ref=dict(class_object_id=2,**{'class':'example.Customer','loader':'17','signature':'Lexample/Customer;'})
        record=dict(entry_method='java.lang.invoke.InvokerBytecodeGenerator.generateCustomizedCodeBytes()[B',
                    class_input_witness=dict(policy='generation-inputs-v1',kind='class-objects',
                         inputs={'receiver.invokerType.rtype':ref,'receiver.invokerType.ptypes':[]}))
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'events.jsonl';p.write_text(json.dumps(dict(kind='generation-entry',record=record))+'\n')
            result=witness_counts(p)
            self.assertEqual(result['validated_generation_entries'],1)
            self.assertEqual(result['counts'],{'application-derived-input':1})

class ProjectionTests(unittest.TestCase):
    def test_native_and_host_allowances_and_distinct_attempt_caps(self):
        from tools.b06_host_probe.oct13_projection import project
        native={'generation_entries':100,'counts':{'generation-entry':100,'generation-return':100,'observer-audit':1500},
                'raw_bytes':1000000,'all_old_audit_rows_compressed_bytes':100000,'observed_max_pending_entries':1}
        host={'generation_entries':100,'event_counts':{'generation-entry':100,'generation-return':100,'class-definition-v3':100,'observer-audit':1000},
              'diagnostic_records':1000,'diagnostic_bytes':100000,'last_sample':{'pending':1},'observer_source_sha256':'a'*64}
        r=project(native,host)
        self.assertEqual(r['rates_per_generation']['ordinary_records'],3)
        self.assertEqual(r['rates_per_generation']['metadata_records'],25)
        self.assertEqual(r['rates_per_generation']['metadata_bytes'],2000)
        host['maximum_pending_entries']=5
        self.assertEqual(project(native,host)['rates_per_generation']['pending_entries'],.05)
        self.assertFalse(r['attempts'][0]['projected_reaches_target'])
        self.assertTrue(r['attempts'][1]['projected_reaches_target'])
        self.assertFalse(r['statistical_upper_confidence_bound'])
        self.assertFalse(r['native_run_authorized'])

import os
import subprocess
@unittest.skipUnless(os.environ.get('B06_HOST_JDK'),'explicit host JDK')
class JavaQuotaTests(unittest.TestCase):
    def test_actual_java_rejects_strict_or_mixed_expanded_quota(self):
        from tools.b06_host_probe.jdk import executable
        jdk=Path(os.environ['B06_HOST_JDK'])
        code="""import java.lang.reflect.*;
public class LimitsProbe {
 public static void main(String[] args)throws Exception {
  Class<?> c=Class.forName("lightyear.observer.PostingObserver");
  Constructor<?> constructor=c.getDeclaredConstructor();constructor.setAccessible(true);
  Object o=constructor.newInstance();Field mode=c.getDeclaredField("diagnosticUnmatchedReturn");mode.setAccessible(true);
  mode.setBoolean(o,Boolean.parseBoolean(args[0]));Method m=c.getDeclaredMethod("configureDiagnosticLimits");m.setAccessible(true);
  try {m.invoke(o);System.out.print("accepted");}catch(InvocationTargetException e){System.out.print("refused");}
 }
}"""
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);(out/'LimitsProbe.java').write_text(code)
            source=Path(__file__).resolve().parents[1]/'factory/idempiere/b06-observer/PostingObserver.java'
            subprocess.run([str(executable(jdk,'javac')),'--add-modules','jdk.jdi','-d',str(out),str(source),str(out/'LimitsProbe.java')],check=True,capture_output=True,timeout=45)
            for mode,records,bytecap,expected in ((False,500000,134217728,'accepted'),(True,1500000,402653184,'accepted'),
                (False,1500000,402653184,'refused'),(True,1500000,134217728,'refused'),(True,1500001,402653184,'refused')):
                with self.subTest(mode=mode,records=records,bytecap=bytecap):
                    result=subprocess.run([str(executable(jdk,'java')),'-Db06.observer.audit_records='+str(records),
                        '-Db06.observer.audit_bytes='+str(bytecap),'-cp',str(out),'LimitsProbe',str(mode).lower()],capture_output=True,text=True,check=True,timeout=20)
                    self.assertEqual(result.stdout,expected)

    def test_input_descriptor_does_not_materialize_definitions_or_extra_class_objects(self):
        from tools.b06_host_probe.jdk import executable
        jdk=Path(os.environ['B06_HOST_JDK'])
        code="""import java.lang.reflect.*;import java.util.*;import com.sun.jdi.*;
public class InputProbe {
 static <T>T proxy(Class<T> type,Map<String,Object> allowed) {
  return type.cast(Proxy.newProxyInstance(type.getClassLoader(),new Class<?>[]{type},(p,m,a)->{
   if(!allowed.containsKey(m.getName()))throw new AssertionError("forbidden side effect: "+m.getName());return allowed.get(m.getName());
  }));
 }
 public static void main(String[] args)throws Exception {
  ClassLoaderReference loader=proxy(ClassLoaderReference.class,Map.of("uniqueID",19L));
  ReferenceType type=proxy(ReferenceType.class,Map.of("name","example.Input","signature","Lexample/Input;","classLoader",loader));
  ClassObjectReference c=proxy(ClassObjectReference.class,Map.of("uniqueID",123L,"reflectedType",type));
  ArrayReference array=proxy(ArrayReference.class,Map.of("length",2,"getValues",List.of(c,c)));
  Class<?> g=Class.forName("lightyear.observer.PostingObserver$Generation");
  java.lang.reflect.Method m=g.getDeclaredMethod("inputValue",Value.class);m.setAccessible(true);
  Map<?,?> expected=Map.of("class_object_id",123L,"class","example.Input","loader","19","signature","Lexample/Input;");
  if(!m.invoke(null,c).equals(expected) || !m.invoke(null,array).equals(List.of(expected,expected)))throw new AssertionError("identity changed");
  // No classObject(), constantPool(), methods(), fields() or target invocation is allowed by the proxies.
  System.out.print("same genuine identity; no catalogue side effects");
 }
}"""
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);(out/'InputProbe.java').write_text(code)
            source=Path(__file__).resolve().parents[1]/'factory/idempiere/b06-observer/PostingObserver.java'
            subprocess.run([str(executable(jdk,'javac')),'--add-modules','jdk.jdi','-d',str(out),str(source),str(out/'InputProbe.java')],check=True,capture_output=True,timeout=45)
            result=subprocess.run([str(executable(jdk,'java')),'--add-modules','jdk.jdi','-cp',str(out),'InputProbe'],capture_output=True,text=True,check=True,timeout=20)
            self.assertEqual(result.stdout,'same genuine identity; no catalogue side effects')
