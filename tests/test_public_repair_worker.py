"""Synthetic contract tests: no Docker, compile, provider or private input."""
import io
import json
from pathlib import Path
import tarfile
import unittest
from unittest.mock import Mock, patch

from lightyear_factory import public_repair_worker as w
from lightyear_factory import public_evaluator_adapter as a


def archive(name,data=b'public',kind=tarfile.REGTYPE):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w') as target:
        row=tarfile.TarInfo(name);row.type=kind;row.size=len(data)
        target.addfile(row,io.BytesIO(data))
    return out.getvalue()


def state(mounts=None):
    return dict(Config=dict(Image=w.image('jre'),User='65534:65534'),
        HostConfig=dict(NetworkMode='none',ReadonlyRootfs=True,PidsLimit=64,Memory=512*1024*1024,
            NanoCpus=1000000000,CapDrop=['ALL'],SecurityOpt=['no-new-privileges'],
            LogConfig={'Type':'none'},Privileged=False,Devices=[],Binds=[]),
        Mounts=mounts or [])


class WorkerTests(unittest.TestCase):
    def test_container_closed_boundaries(self):
        w.boundary(state(),w.image('jre'),{})
        for key,value in [('NetworkMode','host'),('ReadonlyRootfs',False),('Privileged',True),
                          ('Devices',[{}]),('Binds',['/host:/host']),('LogConfig',{'Type':'json-file'}),
                          ('Memory',0),('PidsLimit',-1),('CapDrop',[])]:
            row=state();row['HostConfig'][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(w.Refused,'worker-boundary'):
                w.boundary(row,w.image('jre'),{})

    def test_mount_source_type_and_readonly_are_joined(self):
        mounts={'/candidate.jar':('/reviewed/candidate.jar',False,'bind')}
        row=state([dict(Destination='/candidate.jar',Source='/reviewed/candidate.jar',Type='bind',RW=False)])
        w.boundary(row,w.image('jre'),mounts)
        for key,value in [('Source','/wrong'),('RW',True),('Type','volume')]:
            bad=json.loads(json.dumps(row));bad['Mounts'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(w.Refused,'worker-boundary'):
                w.boundary(bad,w.image('jre'),mounts)

    def test_archive_exact_regular_member(self):
        self.assertEqual(w.member(archive('candidate.jar'), 'candidate.jar',1024),b'public')
        for name,kind in [('../candidate.jar',tarfile.REGTYPE),('wrong',tarfile.REGTYPE),
                          ('candidate.jar',tarfile.SYMTYPE),('candidate.jar',tarfile.DIRTYPE)]:
            with self.subTest(name=name,kind=kind),self.assertRaises(w.Refused):
                w.member(archive(name,kind=kind),'candidate.jar',1024)

    def test_archive_size_and_malformed(self):
        for raw in (b'invalid',archive('candidate.jar',b'x'*2000)):
            with self.subTest(size=len(raw)),self.assertRaises(w.Refused):
                w.member(raw,'candidate.jar',1024)

    def docker(self):
        obj=w.Docker(['/docker','--config','/config','--host','unix:///socket'],'/resources',10,15)
        obj.call=Mock(return_value=dict(rc=0,stdout=b'',stderr=b'',timed_out=False,output_capped=False))
        return obj

    def test_prefix_copy_reports_output_cap(self):
        docker=self.docker();docker.call.return_value.update(stdout=archive('TRANSACT.bin',b'x'*100))
        raw,capped=docker.prefix_copy('name','/output/TRANSACT.bin',10)
        self.assertEqual(raw,b'x'*10);self.assertTrue(capped)

    def test_compile_diagnostic_prefix_preserves_slash_literals(self):
        text=b'Main.java:1:2: compiler.err: String p = dir + "/" + name;\nMain.java:2:3: compiler.err: char c = \'/\'; a/b; // ratio </b>\n'
        docker=self.docker();docker.call.return_value.update(stdout=archive('javac.stderr',text))
        raw,capped=docker.prefix_copy('name','/build/javac.stderr',65537)
        self.assertEqual(raw,text);self.assertFalse(capped)
        rows,_=a.compiler_rows(raw)
        self.assertEqual(len(rows),2)

    def test_prefix_copy_missing_is_empty_only_for_exact_missing_error(self):
        docker=self.docker();docker.call.return_value.update(rc=1,stderr=b'Could not find the file /output/ACCTFILE.bin in container')
        self.assertEqual(docker.prefix_copy('name','/output/ACCTFILE.bin',10,missing=True),(b'',False))
        docker.call.return_value['stderr']=b'daemon unavailable'
        with self.assertRaisesRegex(w.Refused,'worker-copy'):
            docker.prefix_copy('name','/output/ACCTFILE.bin',10,missing=True)

    def test_copy_timeout_is_not_candidate_timeout(self):
        docker=self.docker();docker.call.return_value['timed_out']=True
        with self.assertRaisesRegex(w.Refused,'worker-deadline'):
            docker.prefix_copy('name','/output/ACCTFILE.bin',10,missing=True)

    def test_preflight_architecture_and_manifest(self):
        docker=self.docker()
        docker.ok=Mock(side_effect=[b'{"os":"linux","architecture":"aarch64"}',
            json.dumps([dict(Os='linux',Architecture='arm64',RepoDigests=['eclipse-temurin@sha256:'+w.JRE])]).encode()])
        docker.preflight('jre')
        docker.ok=Mock(return_value=b'{"os":"linux","architecture":"amd64"}')
        with self.assertRaisesRegex(w.Refused,'worker-platform'):docker.preflight('jre')

    def test_create_has_no_pull_network_or_credential_mount(self):
        docker=self.docker();docker.record=Mock();docker.ok=Mock();docker.inspect=Mock(return_value=state())
        docker.create('prw-'+'a'*32,'jre',{},'/java',['-version'])
        args=docker.ok.call_args.args[0]
        for flag in w.COMMON:self.assertIn(flag,args)
        self.assertIn('--pull=never',args);self.assertNotIn('--privileged',args)
        docker.record.assert_called_once_with('container','prw-'+'a'*32)

    def test_compile_command_is_fixed_and_disables_processors(self):
        self.assertIn('-XDrawDiagnostics -proc:none --release 21',w.COMPILE_SCRIPT)
        self.assertIn('/source/Main.java /helper/RecordNumbers.java',w.COMPILE_SCRIPT)
        self.assertIn('javac.exit',w.COMPILE_SCRIPT)
        self.assertNotIn('curl',w.COMPILE_SCRIPT)

    def test_javac_only_one_is_compile_failure(self):
        for exit_raw in (b'2\n',b'3\n',b'4\n',b'125\n'):
            docker=self.docker();docker.preflight=Mock();docker.volume=Mock();docker.create=Mock()
            docker.inspect=Mock(return_value={'State':{'Running':False,'Error':'','ExitCode':0}})
            docker.call.return_value['stdout']=(w.JAVAC+'  /opt/java/openjdk/bin/javac\n'+w.JAR+'  /opt/java/openjdk/bin/jar\n').encode()
            docker.copy=Mock(return_value=exit_raw)
            with patch.object(w,'read',return_value=b'public'),self.subTest(exit=exit_raw):
                req=dict(root='/root',source_sha256=w.c.sha(b'public'),helper_sha256=w.c.sha(b'public'))
                with self.assertRaisesRegex(w.Refused,'worker-javac-fault'):w.compile_worker(req,docker)

    def test_docker_failure_never_becomes_compiler_feedback(self):
        docker=self.docker();docker.preflight=Mock(side_effect=w.Refused('worker-docker'))
        with self.assertRaisesRegex(w.Refused,'worker-docker'):
            w.compile_worker({'root':'/root'},docker)

    def test_completed_javac_one_returns_diagnostics(self):
        docker=self.docker();docker.preflight=Mock();docker.volume=Mock();docker.create=Mock()
        docker.inspect=Mock(return_value={'State':{'Running':False,'Error':'','ExitCode':0}})
        docker.call.return_value['stdout']=(w.JAVAC+'  /opt/java/openjdk/bin/javac\n'+w.JAR+'  /opt/java/openjdk/bin/jar\n').encode()
        docker.copy=Mock(return_value=b'1\n');docker.prefix_copy=Mock(return_value=(b'Main.java:1:1: compiler.err\n',False))
        req=dict(root='/root',source_sha256=w.c.sha(b'public'),helper_sha256=w.c.sha(b'public'))
        with patch.object(w,'read',return_value=b'public'),patch.object(w,'exclusive'):
            row=w.compile_worker(req,docker)
        self.assertEqual(row['exit_code'],1);self.assertIsNone(row['jar_sha256'])
        self.assertEqual(row['diagnostic_mode'],'javac-XDrawDiagnostics')

    def test_runtime_timeout_and_output_cap_are_returned_as_candidate_limits(self):
        for flag in ('timed_out','output_capped'):
            docker=self.docker();docker.preflight=Mock();docker.volume=Mock();docker.create=Mock()
            started=dict(rc=-9,stdout=b'bounded',stderr=b'',timed_out=False,output_capped=False)
            started[flag]=True
            docker.call=Mock(side_effect=[started,dict(rc=0,stderr=b'')])
            docker.inspect=Mock(return_value={'State':{'Running':False,'Error':'','ExitCode':137,
                                                       'StartedAt':'2026-11-17T00:00:00Z'}})
            docker.prefix_copy=Mock(return_value=(b'',False))
            req=dict(root='/root',artifact='/jar',jar_sha256=w.c.sha(b'public'),inputs={},
                timestamp='2026-11-17-00.00.00.000000',processing_date='2026111700',
                source_sha256='1'*64,build_receipt_sha256='2'*64)
            with self.subTest(flag=flag),patch.object(w,'read',return_value=b'public'),patch.object(w,'exclusive'):
                row=w.public_worker(req,docker)
            self.assertTrue(row[flag]);self.assertEqual(row['exit'],137)
            self.assertEqual(docker.call.call_args.args[0][0],'kill')

    def test_docker_config_must_stay_empty(self):
        docker=w.Docker(['/docker','--config','/config','--host','unix:///socket'],'/resources',10,15)
        with patch.object(Path,'iterdir',return_value=iter([Path('config.json')])):
            with self.assertRaisesRegex(w.Refused,'worker-docker-config'):docker.call(['info'])

    def test_child_fault_keeps_parent_cleanup(self):
        worker=object.__new__(w.PublicWorker);worker.failed=False
        worker.prefix=['/docker','--config','/config','--host','unix:///socket'];worker.docker_sha256='1'*64
        worker.helper_sha256='2'*64
        with patch.object(w.time,'monotonic',return_value=0),patch.object(w,'exclusive'),patch.object(Path,'mkdir'),\
             patch.object(w,'capture',return_value={'rc':2,'stderr':b'worker-image\n'}),patch.object(w,'Docker') as ctor:
            ctor.return_value.cleanup.return_value=[]
            with self.assertRaisesRegex(w.Refused,'worker-image'):
                worker._invoke(Path('/root'),{'operation':'compile'},200,30)
            ctor.return_value.cleanup.assert_called_once()

    def test_unknown_child_text_is_not_public_diagnostic(self):
        worker=object.__new__(w.PublicWorker);worker.failed=False
        worker.prefix=[];worker.docker_sha256='1'*64;worker.helper_sha256='2'*64
        with patch.object(w.time,'monotonic',return_value=0),patch.object(w,'exclusive'),patch.object(Path,'mkdir'),\
             patch.object(w,'capture',return_value={'rc':2,'stderr':b'/private/path secret details'}),patch.object(w,'Docker') as ctor:
            ctor.return_value.cleanup.return_value=[]
            with self.assertRaisesRegex(w.Refused,'^worker-child$'):
                worker._invoke(Path('/root'),{'operation':'compile'},200,30)

    def test_limits_refuse_more_than_fifteen_seconds(self):
        worker=object.__new__(w.PublicWorker);worker.failed=False
        worker.built={'1'*64:('2'*64,Path('/jar'),'3'*64)}
        built=dict(build_receipt_sha256='1'*64,artifact_sha256='2'*64,status='BUILT')
        with patch.object(w.time,'monotonic',return_value=0):
            with self.assertRaisesRegex(w.Refused,'worker-limits'):
                worker.run_public(built,{},'','',40,dict(execution_deadline=30,cleanup_deadline=35,output_bytes=w.DATA))
        self.assertTrue(worker.failed)

    def test_public_never_accepts_unknown_build(self):
        worker=object.__new__(w.PublicWorker);worker.failed=False;worker.built={}
        with self.assertRaisesRegex(w.Refused,'worker-build-join'):
            worker.run_public({'build_receipt_sha256':'1'*64},{},'','',40,{})

    def test_cleanup_proves_absence(self):
        docker=self.docker();name='prw-'+'a'*32
        row=dict(kind='container',name=name)
        docker.call.side_effect=[dict(rc=0,stderr=b''),dict(rc=1,stderr=b'No such container')]
        with patch.object(Path,'glob',return_value=[Path('container-'+name+'.json')]),\
             patch.object(w,'read',return_value=json.dumps(row).encode()),patch.object(w,'exclusive') as write:
            result=docker.cleanup()
        self.assertTrue(result[0]['absence_confirmed']);write.assert_called_once()

    def test_cleanup_inspect_success_refuses(self):
        docker=self.docker();name='prw-'+'a'*32
        docker.call.return_value=dict(rc=0,stderr=b'')
        with patch.object(Path,'glob',return_value=[Path('container-'+name+'.json')]),\
             patch.object(w,'read',return_value=json.dumps(dict(kind='container',name=name)).encode()):
            with self.assertRaisesRegex(w.Refused,'worker-absence'):docker.cleanup()


if __name__=='__main__':unittest.main()
