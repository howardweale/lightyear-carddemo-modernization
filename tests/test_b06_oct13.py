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
