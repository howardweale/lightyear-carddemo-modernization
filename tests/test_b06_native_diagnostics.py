"""Offline engineering diagnostics, authority separation and signed-stop tests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from lightyear_calibration.contracts import canonical, seal
from tools import ms94_b06_engineering as engineering
from tools import ms94_b06_engineering_key as keys
from tools import ms94_b06_observer_diagnostics as diagnostics
from tools.ms94_b06_engineering_boundary import refuse_engineering, refuse_engineering_key


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.plan=dict(run_class='engineering',qualification_credit=False,measurement_credit=False,
            content_sha256='a'*64,engineering_limits=dict(engineering.LIMITS),
            posting_observer=dict(native_diagnostics=diagnostics.configuration('strict')))

    def test_limits_reach_actual_container_and_java_arguments(self):
        args=diagnostics.container_args(self.plan,self.root)
        self.assertEqual(args[:4],['--memory','2048m','--cpus','1'])
        self.assertIn('dst=/observer-private',args[-1])
        self.assertEqual(diagnostics.java_options(self.plan),['-Xmx1536m',
            '-XX:SoftRefLRUPolicyMSPerMB=0','-Db06.observer.state_dir=/observer-private',
            '-XX:+HeapDumpOnOutOfMemoryError','-XX:HeapDumpPath=/observer-private/heap.hprof'])
        self.assertEqual(diagnostics.observer_args(self.plan),['bounded-observer-v1','native-diagnostics-v1','strict',
            'unmatched-return-cap=10','heap-guard-percent=85','heap-telemetry-interval=1000','pending-cap=256'])
        self.plan['posting_observer']['native_diagnostics']=diagnostics.configuration('diagnostic-unmatched-return')
        self.assertIn('diagnostic-unmatched-return',diagnostics.observer_args(self.plan))

    def test_real_broker_create_and_java_command_use_diagnostic_args(self):
        from tools.ms94_b06_posting_broker import PostingBroker
        from tools import ms94_b06_posting_broker as module
        classes=self.root/'classes';classes.mkdir()
        self.plan['posting_observer'].update(classes_directory='classes',class_files_sha256={})
        self.plan.update(local={'runner_image':'pinned-image'},
                         implementation_sha256={'tools/ms94_b06_posting_listener.py':'b'*64})
        runner=SimpleNamespace(root=self.root,run=self.root,owner='journey-fixture',label='owned=fixture',
            plan=self.plan,network='internal',remember=Mock(),assert_real_runtime=Mock(),check_cancel=Mock())
        info=dict(Id='application-id',Image='pinned-image',NetworkSettings={'Networks':{'internal':{}}},
                  HostConfig={'PortBindings':None},Mounts=[])
        broker=PostingBroker(runner,'oracle','application',Mock())
        with patch.object(module,'inspect',return_value=info),patch.object(module,'docker') as docker, \
                patch.object(module.threading,'Thread'):
            broker.start()
        create=docker.call_args_list[0].args
        self.assertEqual(create[create.index('--memory')+1],'2048m')
        self.assertIn('dst=/observer-private', ' '.join(create))
        with patch.object(module,'bound_file',return_value=Path(__file__)), \
                patch.object(module,'docker',return_value=SimpleNamespace(stdout='[{"executable":"java"}]')), \
                patch.object(module,'validate_jvm'), patch.object(module,'sign_once'), \
                patch.object(module.subprocess,'Popen',side_effect=RuntimeError('test stop before launch')) as launch:
            broker._collect()
        command=launch.call_args.args[0]
        self.assertIn('-Xmx1536m',command)
        self.assertIn('-XX:HeapDumpPath=/observer-private/heap.hprof',command)
        self.assertIn('bounded-observer-v1',command)
        self.assertIn('strict',command)

    def test_configuration_cannot_cross_qualification_or_expand_limits(self):
        for change in (dict(run_class='qualification'),dict(qualification_credit=True),
                       dict(engineering_limits={**engineering.LIMITS,'observer_heap_mib':9999})):
            with self.subTest(change=change),self.assertRaises(ValueError):
                diagnostics.java_options({**self.plan,**change})
        changed=deepcopy(self.plan);changed['posting_observer']['native_diagnostics']['unmatched_return_cap']=11
        with self.assertRaises(ValueError):diagnostics.observer_args(changed)
        self.assertEqual(diagnostics.java_options({}),[])
        self.assertEqual(diagnostics.container_args({},self.root),['--memory','768m','--cpus','1'])

    def test_disk_spool_retains_only_last_event_and_reiterates_original_bytes(self):
        path=self.root/'events.jsonl';records=diagnostics.DiskRecords(path)
        with path.open('wb') as out:
            for i in range(2000):
                item=seal(dict(event=dict(kind='generation-entry',sequence=i,payload='x'*2048)))
                out.write(canonical(item)+b'\n');records.append(item)
        self.assertEqual(len(records),2000);self.assertEqual(records[-1]['event']['sequence'],1999)
        self.assertEqual(list(vars(records)),['path','count','last'])
        self.assertEqual(sum(1 for _ in records),2000)
        self.assertEqual(sum(1 for _ in records),2000)
        with self.assertRaises(IndexError):_=records[0]

    def test_guard_histogram_bound_to_signed_stop(self):
        broker=SimpleNamespace(private=self.root,name='owned-observer',lane='oracle',
            runner=SimpleNamespace(plan=self.plan),generation_entries=12400,signer=Mock())
        event=dict(kind='observer-resource-limit',checkpoint=True,observer_pid=27,reason='heap-85-percent')
        def run(args,**kwargs):
            self.assertEqual(args,['docker','exec','owned-observer','jcmd','27','GC.class_histogram'])
            kwargs['stdout'].write(b'histogram fixture\n')
            return SimpleNamespace(returncode=0)
        with patch.object(diagnostics.subprocess,'run',side_effect=run), \
             patch.object(diagnostics,'sign_once',side_effect=lambda p,v,s:v):
            result=diagnostics.guard_stop(broker,event,'b'*64)
        self.assertTrue(result['histogram_complete']);self.assertEqual(result['event_sha256'],'b'*64)
        self.assertEqual(result['histogram_sha256'],hashlib.sha256(b'histogram fixture\n').hexdigest())
        self.assertEqual(result['generation_entry_count'],12400)

    def test_histogram_failure_is_explicit_in_stop_record(self):
        broker=SimpleNamespace(private=self.root,name='owned-observer',lane='oracle',
            runner=SimpleNamespace(plan=self.plan),generation_entries=1,signer=Mock())
        with patch.object(diagnostics.subprocess,'run',side_effect=TimeoutError()), \
             patch.object(diagnostics,'sign_once',side_effect=lambda p,v,s:v):
            result=diagnostics.guard_stop(broker,dict(kind='observer-resource-limit',checkpoint=True,observer_pid=2),'b'*64)
        self.assertFalse(result['histogram_complete']);self.assertEqual(result['histogram_error_type'],'TimeoutError')

    def test_phase_marker_uses_existing_application_stage_and_observed_count(self):
        from tools.ms94_b06_posting_broker import PostingBroker
        runner=SimpleNamespace(plan=self.plan,run=self.root,owner='journey-fixture')
        broker=PostingBroker(runner,'oracle','app',Mock(sign=lambda v:seal(v)))
        broker.generation_entries=12400;broker.previous='b'*64
        broker.phase_marker('application-worker-started')
        record=json.loads((broker.private/'application-phases.jsonl').read_text())
        self.assertEqual(record['generation_entry_count'],12400)
        self.assertEqual(record['phase'],'application-worker-started')
        self.assertEqual(record['last_event_sha256'],'b'*64)
        with self.assertRaises(ValueError):broker.phase_marker('invented-business-pass')

    def test_new_authority_creation_is_exclusive_and_only_public_is_returned(self):
        folder=self.root/'b06-engineering-authority'
        record=keys.generate_once(folder)
        self.assertEqual(record['public_key_sha256'],hashlib.sha256((folder/keys.PUBLIC_NAME).read_bytes()).hexdigest())
        self.assertTrue((folder/keys.PRIVATE_NAME).is_file())
        self.assertNotIn('PRIVATE KEY',json.dumps(record))
        with self.assertRaises(FileExistsError):keys.generate_once(folder)

    def test_wrong_authority_refused_before_private_read(self):
        folder=self.root/'b06-engineering-authority';folder.mkdir()
        (folder/keys.PUBLIC_NAME).write_bytes(b'wrong public key')
        # No private file: fingerprint refusal must precede private-file access.
        with self.assertRaisesRegex(ValueError,'fingerprint'):
            keys.DedicatedEngineeringSigner(folder,keys.ENGINEERING_KEY_SHA256)

    def test_engineering_signature_identity_rejected_after_relabelling_and_relocation(self):
        public=Path('docs/calibration/idempiere-ms94/stage-b-06/preparation/engineering.public.pem').read_bytes()
        self.assertEqual(hashlib.sha256(public).hexdigest(),keys.ENGINEERING_KEY_SHA256)
        value={'artifact_type':'qualification-pass','qualification_credit':True,
               'signature':{'key_id':keys.ENGINEERING_KEY_SHA256}}
        with self.assertRaisesRegex(ValueError,'signing-key-not-admissible'):refuse_engineering(value,self.root/'renamed.json')
        with self.assertRaisesRegex(ValueError,'signing-key-not-admissible'):refuse_engineering_key(public)
        from tools.ms94_b06_admission import replay_entry,replay_clocks
        from tools.ms94_b06_j1_bridge import evaluate
        for call in (replay_entry,replay_clocks,evaluate):
            with self.assertRaisesRegex(ValueError,'signing-key-not-admissible'):call(self.root,public)

    def test_two_attempt_request_exact_fingerprint_and_review_lead(self):
        kwargs=dict(implementation_commit='a'*40,native_template_sha256='b'*64,observer_source_sha256='c'*64,
            observer_class_files_sha256={'PostingObserver.class':'d'*64},
            full_plan_delivered_at_utc='2026-10-12T12:00:00Z')
        value=engineering.instrumented_proposal('2026-10-12T16:00:00Z','2026-10-12T19:00:00Z',[],
                [str(self.root/'sealed-evidence')],self.root/'b06-engineering',**kwargs)
        self.assertEqual(value['run_cap'],2)
        self.assertEqual(value['attempt_modes'],['strict','diagnostic-unmatched-return'])
        self.assertEqual(value['engineering_key_sha256'],keys.ENGINEERING_KEY_SHA256)
        self.assertFalse(value['approved'])
        kwargs['full_plan_delivered_at_utc']='2026-10-12T12:00:01Z'
        with self.assertRaisesRegex(ValueError,'four-hour-plan-review'):
            engineering.instrumented_proposal('2026-10-12T16:00:00Z','2026-10-12T19:00:00Z',[],
                [str(self.root/'sealed-evidence')],self.root/'b06-engineering',**kwargs)


if __name__=='__main__':unittest.main()
