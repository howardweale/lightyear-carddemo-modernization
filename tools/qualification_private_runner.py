"""Separate generated application execution from trusted capture and judge mounts."""
import json
import subprocess
import time
from pathlib import Path
from lightyear_calibration.contracts import canonical,require,seal
from lightyear_calibration.journey_order import save,file_hash
from lightyear_calibration.journey_runtime import LocalRunner,docker,inspect,JourneyAbort


class PrivateRunner(LocalRunner):
    def trusted_identity(self,lane):
        # Only the trusted collection container sees verifier code and captures.
        program='''import json,sys
from lightyear_calibration.journey_worker import clock,connect,query
s=json.load(sys.stdin);lane=s['lane'];password=s['password'];name=None
if lane=='oracle':
 with connect(lane,password) as c:
  name=query(c,"SELECT LOWER(SYS_CONTEXT('USERENV','CURRENT_USER') || '.' || SYS_CONTEXT('USERENV','DB_NAME') || '.' || SYS_CONTEXT('USERENV','DB_DOMAIN')) value FROM dual")[0]['value']
print(json.dumps({'clock':clock(lane,password),'name':name}))
'''
        p=docker('exec','-i',self.runner,'python','-c',program,input=canonical({'lane':lane,'password':self.password}),timeout=30)
        return json.loads(p.stdout)

    def worker(self,command,payload,timeout):
        if command!='execute':return super().worker(command,payload,timeout)
        lane=payload['lane'];require(lane in ('oracle','postgresql'),'Unknown application lane')
        require(payload['test']=='LightyearOperationsTest','Unknown application class')
        relative=Path(payload['output'].removeprefix('/output/'))
        out=(self.run/relative).resolve();require(out.is_relative_to(self.run.resolve()),'Output escaped run')
        source=self.run/'inputs/operations.java'
        require(file_hash(source)==payload['harness_sha256'],'Candidate changed')
        staging=self.run/'application-output'/lane;staging.mkdir(parents=True,exist_ok=False)
        app=self.owner+'-application-'+lane
        worker=self.root/'tools/qualification_application_worker.py'
        docker('create','--name',app,'--label',self.label,'--network',self.network,'--memory','8g','--cpus','4',
               '--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/secrets:rw,noexec,nosuid,size=268435456',
               '--mount',f'type=bind,src={source},dst=/candidate/LightyearOperationsTest.java,readonly',
               '--mount',f'type=bind,src={worker},dst=/runtime/worker.py,readonly',
               '--mount',f'type=bind,src={staging},dst=/results',self.plan['local']['runner_image'])
        self.remember('container',app);docker('start',app)
        mounts=inspect('container',app)['Mounts']
        require({m['Destination'] for m in mounts if m['Type']=='bind'}==
                {'/candidate/LightyearOperationsTest.java','/runtime/worker.py','/results'},'Unexpected application mount')
        require(all(not m['RW'] for m in mounts if m['Destination'] in
                    ('/candidate/LightyearOperationsTest.java','/runtime/worker.py')),'Writable application input')
        before=self.trusted_identity(lane);started=time.monotonic()
        process=subprocess.Popen(['docker','exec','-i',app,'python','/runtime/worker.py'],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        data=canonical({'lane':lane,'password':self.password,'timeout_seconds':payload['timeout_seconds']})
        try:
            while True:
                try:stdout,stderr=process.communicate(input=data,timeout=1);break
                except subprocess.TimeoutExpired:
                    data=None;self.check_cancel()
                    if time.monotonic()-started>timeout:raise JourneyAbort('application-timeout')
            require(process.returncode==0,'Separate application worker failed')
            code=json.loads(stdout)['exit_code']
        finally:
            if process.poll() is None:process.kill();process.communicate()
            docker('stop','--time','2',app,check_code=False)
        after=self.trusted_identity(lane);out.mkdir(parents=True,exist_ok=False)
        # Copy only the declared untrusted observations after the application has
        # stopped. It cannot write the trusted execution envelope or captures.
        for name in ('journey.xml','maven.log'):
            path=staging/name
            require(not path.is_symlink(),'Symbolic application output')
            if path.exists():
                data=path.read_bytes().replace(self.password.encode(),b'[redacted]')
                (out/name).write_bytes(data)
        (out/'harness.java').write_bytes(source.read_bytes())
        facts={'native_database_instance':before['name'],'expected_database_address':
            'jdbc:oracle:thin:@//oracle:1521/freepdb1' if lane=='oracle' else
            'jdbc:postgresql://postgresql:5432/idempiere?encoding=unicode&applicationname=idempiere&stringtype=unspecified&tcpkeepalive=true'}
        value=seal({'lane':lane,'runtime_facts':facts,'exit_code':code,'elapsed_seconds':round(time.monotonic()-started,1),
            'native_clock_before':before['clock'],'native_clock_after':after['clock'],
            'harness_sha256':payload['harness_sha256'],'application_source_commit':payload['source_commit'],
            'journey_output_exists':(out/'journey.xml').exists(),'offline_maven':True,
            'private_judge_mount':False,'trusted_execution_envelope_written_by':'host-controller',
            'application_mounts':[{'destination':m['Destination'],'writable':m['RW']} for m in mounts if m['Type']=='bind']})
        save(out/'execution.json',value);return value
