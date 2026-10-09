import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from tools import ms94_b06_built_worker as w
from tools.ms94_b06_bytecode_policy import validate_jvm, POLICY


def reseal(d, **updates):return w.seal({**{k:v for k,v in d.items() if k!='content_sha256'}, **updates})


def fixture(root):
    def resolve(p):return root/p.lstrip('/')
    def put(p, raw):
        target=resolve(p);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);return w.descriptor(target)
    props=w.TEST+'/target/surefire.properties'
    raw=b'#fixed timestamp\r\n__provider.tc.0=org.idempiere.test.B06RuntimeCatalogTest\r\ntestpluginname=org.idempiere.test\r\n'
    oldprops=put(props,raw)
    launcher='/root/.m2/launcher.jar';launchdesc=put(launcher,b'bound launcher')
    put(w.TEST+'/META-INF/MANIFEST.MF',b'Manifest-Version: 1.0\n')
    put(w.TEST+'/resource.txt',b'unchanged')
    base=w.bundle_content_view(resolve(w.TEST),kind='folder')['entries']
    config=w.TEST+'/target/work/configuration'
    configdesc=put(config+'/config.ini',b'bound config')
    overlays={}
    for name in ('LightyearOperationsTest','JourneySupport'):
        key='target/classes/org/idempiere/test/'+name+'.class'
        overlays[key]=put(w.TEST+'/'+key,('test class fixture '+name).encode())
    fork=['/opt/java/openjdk/bin/java','-Duser.timezone=UTC','-Djunit.jupiter.execution.parallel.enabled=false',*w.AGENTS,
          '-jar',launcher,'-testproperties',props]
    manifest=w.seal(dict(fork=fork,artifacts={launcher:launchdesc},source_files={},sealed_files={props:oldprops},
        testproperties_path=props,config_path=config,base_config_sha256=configdesc['sha256'],
        base_applications={'org.idempiere.test':dict(path=w.TEST,kind='folder-archive',entries=base,jar_sha256=None)}))
    put(props,w.properties(raw))
    spec=w.seal(dict(schema='b06-built-native-launch/1',manifest_sha256=manifest['content_sha256'],
        argv=w.arguments(manifest),image='sha256:'+'1'*64,overlays=overlays,testproperties=w.descriptor(resolve(props)),model_calls=0,rebuild=False))
    put(w.LAYER+'/manifest.json',w.canonical(manifest));put('/runtime/launch.json',w.canonical(spec))
    resolve('/results').mkdir();resolve('/secrets').mkdir()
    return manifest,spec,resolve


class BuiltNativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.m,self.s,self.resolve=fixture(Path(self.temp.name))

    def test_direct_command_and_external_jdi_match(self):
        argv=w.arguments(self.m)
        self.assertFalse(any('mvn'==x or 'javac' in x or x.startswith('-javaagent') for x in argv))
        owner=dict(arguments=argv,java_binary_sha256='0'*64,jvm_option_environment_present=[])
        policy=dict(bytecode_policy=POLICY,java_binary_sha256='0'*64,expected_jvm_arguments=argv)
        self.assertTrue(validate_jvm(owner,policy))
        with self.assertRaisesRegex(ValueError,'built-command-differs'):
            validate_jvm({**owner,'arguments':argv+['unbound']},policy)
        for extra in ('-javaagent:/extra.jar','-DPropertyFile=/wrong','@args'):
            bad=reseal(self.m,fork=self.m['fork'][:1]+[extra]+self.m['fork'][1:])
            with self.assertRaises(ValueError):w.arguments(bad)

    def test_properties_only_changes_exact_selector(self):
        raw=b'#time\r\n__provider.tc.0=org.idempiere.test.B06RuntimeCatalogTest\r\ntestpluginname=org.idempiere.test\r\n'
        self.assertEqual(w.properties(raw),raw.replace(b'B06RuntimeCatalogTest',b'LightyearOperationsTest'))
        for bad in (raw.replace(b'B06RuntimeCatalogTest',b'Wrong'),raw+b'__provider.tc.1=extra\n'):
            with self.assertRaises(ValueError):w.properties(bad)

    def test_live_exact_content_and_extra_entry_refuse(self):
        self.assertTrue(w.verify_live(self.m,self.s,self.resolve)['verified'])
        for relative in ('resource.txt','target/classes/org/idempiere/test/Unexpected.class'):
            p=self.resolve(w.TEST+'/'+relative);existed=p.exists();raw=p.read_bytes() if existed else None
            p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'application-changed'):w.verify_live(self.m,self.s,self.resolve)
            if existed:p.write_bytes(raw)
            else:p.unlink()

    def test_compiled_candidate_tamper_refuses(self):
        p=self.resolve(w.TEST+'/'+next(iter(self.s['overlays'])));p.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'application-changed'):w.verify_live(self.m,self.s,self.resolve)

    def test_property_and_active_configuration_tamper_refuse(self):
        for path in (self.m['testproperties_path'],self.m['config_path']+'/config.ini'):
            p=self.resolve(path);raw=p.read_bytes();p.write_bytes(b'bad')
            with self.assertRaises(ValueError):w.verify_live(self.m,self.s,self.resolve)
            p.write_bytes(raw)

    def test_overlay_cannot_widen_to_other_class(self):
        bad=reseal(self.s,overlays={**self.s['overlays'],'target/classes/org/evil/Other.class':{'bytes':1,'sha256':'1'*64}})
        with self.assertRaisesRegex(ValueError,'overlay-path'):w.validate_spec(self.m,bad)

    def test_timeout_records_postcheck_and_removes_secret_without_build(self):
        seen=[]
        def execute(argv,**kw):
            seen.append(argv);self.assertTrue(self.resolve('/secrets/application.properties').exists())
            self.assertNotIn('JAVA_TOOL_OPTIONS',kw['env'])
            raise subprocess.TimeoutExpired(argv,1)
        with patch.dict('os.environ',{'JAVA_TOOL_OPTIONS':'-javaagent:bad'}):
            result=w.run(dict(lane='oracle',password='public-fixture',scenario_date='2026-10-01',timeout_seconds=1),resolve=self.resolve,execute=execute)
        self.assertEqual(result['exit_code'],124);self.assertEqual(seen,[self.s['argv']])
        self.assertFalse(self.resolve('/secrets/application.properties').exists())
        self.assertEqual(self.resolve('/results/built-before.json').read_bytes(),self.resolve('/results/built-after.json').read_bytes())

    def test_failed_precheck_never_starts_process(self):
        self.resolve(w.TEST+'/resource.txt').write_bytes(b'bad')
        with self.assertRaises(ValueError):
            w.run(dict(lane='postgresql',password='public-fixture',scenario_date='2026-10-01',timeout_seconds=1),resolve=self.resolve,execute=lambda *_a,**_k:self.fail('must not execute'))
        self.assertFalse(self.resolve('/secrets/application.properties').exists())
class BuiltHostTests(unittest.TestCase):
    def test_host_staging_has_no_writable_alias_for_launch_inputs_and_replays(self):
        from tools import ms94_b06_built_runtime as host
        from tests.test_ms94_b06_catalog import empty_class
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);m,s,resolve=fixture(root/'vm')
            def keep(name, raw):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                return dict(path=name,sha256=hashlib.sha256(raw).hexdigest())
            classes={};catalog={};rows=[]
            for name in ('LightyearOperationsTest','JourneySupport'):
                raw=empty_class('org.idempiere.test.'+name);item=keep('private/'+name+'.class',raw)
                entry='target/classes/org/idempiere/test/'+name+'.class';classes[entry]=item;catalog[item['path']]=item['sha256'];rows.append(dict(sha256=item['sha256']))
            rawprops=b'__provider.tc.0=org.idempiere.test.B06RuntimeCatalogTest\ntestpluginname=org.idempiere.test\n'
            props=keep('private/surefire.properties',rawprops)
            config=keep('private/config.ini',b'bound config')
            m=reseal(m,data_path=w.TEST+'/target/work/data',sealed_files={m['testproperties_path']:dict(bytes=len(rawprops),sha256=props['sha256']),
                w.LAYER+'/configuration-seed/config.ini':dict(bytes=12,sha256=config['sha256'])})
            manifest=keep('private/manifest.json',w.canonical(m))
            compiled=keep('private/compilation.json',json.dumps(dict(sha256='a'*64,exit_code=0,tests_run=0,model_calls=0,native_pairs=0,classes=rows)).encode())
            runtime=w.seal(dict(schema='b06-built-native-inputs/1',image='sha256:'+'b'*64,source_sha256='a'*64,manifest_sha256=m['content_sha256'],
                manifest=manifest,properties=props,configuration={'config.ini':config},classes=classes,compilation=compiled))
            plan=dict(built_runtime=runtime,harness_sha256='a'*64,local={'runner_image':'base'},
                posting_observer=dict(target_class_files_sha256=catalog,expected_jvm_arguments=w.arguments(m)))
            out=root/'run/application-output/oracle';out.mkdir(parents=True)
            args,mounts,launch=host.prepare(root,root/'run',plan,out)
            self.assertIn('--read-only',args)
            for i,a in enumerate(args):
                if a=='--mount' and args[i+1].endswith(',readonly'):
                    src=args[i+1].split('src=',1)[1].split(',dst=',1)[0]
                    self.assertFalse(Path(src).is_relative_to(out))
            for entry,row in classes.items():resolve(w.TEST+'/'+entry).write_bytes((root/row['path']).read_bytes())
            # Filesystem check is performed on the new exact props/overlay, not a bool fixture.
            resolve(m['testproperties_path']).write_bytes(w.properties(rawprops))
            seed=resolve(w.LAYER+'/configuration-seed/config.ini');seed.parent.mkdir(parents=True);seed.write_bytes(b'bound config')
            value=w.verify_live(m,launch,resolve)
            for n in ('built-before.json','built-after.json'):(out/n).write_bytes(w.canonical(value))
            ex=dict(launch_sha256=launch['content_sha256'],offline_maven=False,runtime_image=launch['image'],application_readonly=True,
                built_runtime_checks_sha256={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ('built-before.json','built-after.json')})
            self.assertTrue(host.replay(root,plan,ex,out)['built_runtime_replayed'])
            with self.assertRaisesRegex(ValueError,'execution-binding'):host.replay(root,plan,{**ex,'offline_maven':True},out)
            wrong=copy.deepcopy(plan);wrong['built_runtime']=reseal(runtime,source_sha256='c'*64)
            with self.assertRaisesRegex(ValueError,'source-binding'):host.contract(root,wrong)
class ObservedCarrierTests(unittest.TestCase):
    def test_actual_runner_overrides_inherited_builder_entrypoint(self):
        self.run_observed()

    def test_slow_observer_preparation_does_not_consume_candidate_watchdog(self):
        self.run_observed('slow-preparation')

    def test_candidate_watchdog_still_expires_and_cleans_up(self):
        self.run_observed('timeout')

    def test_observer_failure_remains_equipment_failure(self):
        self.run_observed('observer-failure')

    def test_window_cancel_after_preparation_prevents_worker_launch(self):
        self.run_observed('cancel')

    def test_failed_stop_diagnostic_cannot_prevent_cleanup(self):
        self.run_observed('stop-record-failure')

    def run_observed(self, mode='normal'):
        from unittest.mock import Mock
        from tools.ms94_b06_observed_runner import ObservedRunner
        from tools.ms94_b06_candidate_result import CandidateTimeout
        from lightyear_calibration.contracts import CalibrationError
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'run';(run/'inputs').mkdir(parents=True)
            source=run/'inputs/operations.java';source.write_bytes(b'public candidate fixture')
            runner=object.__new__(ObservedRunner);runner.root=root;runner.run=run;runner.owner='owned';runner.label='owned=1';runner.network='internal';runner.password='fixture';runner.signer=Mock()
            runner.plan=dict(built_runtime={},local={'runner_image':'base'},calendar={'scenario_date':'2026-10-01'})
            for name in ('remember','record_guard','assert_real_runtime','before_candidate','emit','check_cancel'):setattr(runner,name,Mock())
            runner.trusted_identity=Mock(return_value={'name':'db','clock':{'value':'real clock fixture'}})
            image='sha256:'+'d'*64;launch={'image':image,'content_sha256':'a'*64}
            expected=[dict(destination='/runtime/worker.py',writable=False),dict(destination='/results',writable=True)]
            info=dict(Image=image,HostConfig={'ReadonlyRootfs':True},Mounts=[dict(Destination=m['destination'],RW=m['writable'],Type='bind') for m in expected])
            broker=Mock(failure=None);broker.done.wait.return_value=True
            clock=[0.0]
            broker.start.side_effect=lambda: clock.__setitem__(0,1200.0)
            if mode=='cancel':runner.check_cancel.side_effect=RuntimeError('window closed')
            if mode=='stop-record-failure':
                def emit(kind,payload):
                    if kind=='application-stop-requested':raise RuntimeError('diagnostic disk failure')
                runner.emit.side_effect=emit
            child=Mock(returncode=None)
            child.poll.side_effect=lambda:child.returncode
            child.kill.side_effect=lambda:setattr(child,'returncode',-9)
            calls=[0]
            def communicate(**kwargs):
                calls[0]+=1
                if calls[0]==1 and mode in ('slow-preparation','timeout','observer-failure'):
                    clock[0]+=1831 if mode=='timeout' else 800
                    if mode=='observer-failure':broker.failure='fixture observer failure'
                    raise subprocess.TimeoutExpired('fixture',1)
                child.returncode=0
                return (json.dumps(dict(exit_code=0,launch_sha256='a'*64,offline_maven=False)).encode(),b'')
            child.communicate.side_effect=communicate
            def process(*args,**kwargs):
                for n in ('built-before.json','built-after.json'):(run/'application-output/oracle'/n).write_bytes(b'{}')
                return child
            with patch('tools.ms94_b06_built_runtime.prepare',return_value=(['--read-only'],expected,launch)), \
                 patch('tools.ms94_b06_built_runtime.replay') as replay, \
                 patch('tools.ms94_b06_observed_runner.docker') as docker, \
                 patch('tools.ms94_b06_observed_runner.inspect',return_value=info), \
                 patch('tools.ms94_b06_observed_runner.PostingBroker',return_value=broker), \
                 patch('tools.ms94_b06_observed_runner.time.monotonic',side_effect=lambda:clock[0]), \
                 patch('tools.ms94_b06_observed_runner.subprocess.Popen',side_effect=process) as popen:
                payload=dict(lane='oracle',test='LightyearOperationsTest',output='/output/execution/oracle',
                    harness_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),timeout_seconds=1800,source_commit='c'*40)
                if mode in ('timeout','observer-failure','cancel','stop-record-failure'):
                    expected_error={'timeout':CandidateTimeout,'observer-failure':CalibrationError,'cancel':RuntimeError,'stop-record-failure':RuntimeError}[mode]
                    with self.assertRaises(expected_error):runner.worker('execute',payload,1830)
                    if mode=='cancel':popen.assert_not_called()
                    replay.assert_not_called()
                else:value=runner.worker('execute',payload,1830)
            create=docker.call_args_list[0].args
            self.assertEqual(create[-5:],('--entrypoint','/bin/sh',image,'-c','exec sleep infinity'))
            broker.cancel.assert_called_once()
            self.assertTrue(any(c.args[:1]==('stop',) for c in docker.call_args_list))
            events=[c.args[0] for c in runner.emit.call_args_list]
            self.assertEqual('application-watchdog-expired' in events,mode=='timeout')
            if mode in ('timeout','observer-failure'):child.kill.assert_called_once()
            else:child.kill.assert_not_called()
            if mode in ('timeout','observer-failure','cancel','stop-record-failure'):return
            self.assertFalse(value['offline_maven']);self.assertTrue(value['application_readonly']);replay.assert_called_once()
