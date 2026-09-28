"""Independent observer containers for native qualification and future campaigns."""
from pathlib import Path
import secrets
import shutil
import subprocess
import time

from .contracts import canonical, read_json, require
from .journey_runtime import docker, JourneyAbort
from .qualification_observer import verify_capture


class Observer:
    def __init__(self, runner, lane):
        self.runner=runner;self.lane=lane;self.process=None
        self.password=secrets.token_hex(24)
        self.private=runner.root/'work/ms93/observer-private'/runner.owner/lane
        self.private.mkdir(parents=True,exist_ok=False)
        self.container=runner.owner+'-observer-'+lane

    def provision(self):
        runner=self.runner;lane=self.lane
        if lane=='oracle':
            sql=("whenever sqlerror exit failure\nconnect / as sysdba\nalter session set container=FREEPDB1;\n"
                 f'CREATE USER LY_OBSERVER IDENTIFIED BY "{self.password}";\nGRANT CREATE SESSION TO LY_OBSERVER;\n')
            for view in ('V_$SESSION','V_$TRANSACTION','V_$LOCK','V_$SESSTAT','V_$STATNAME','DBA_OBJECTS'):
                sql+='GRANT SELECT ON SYS.'+view+' TO LY_OBSERVER;\n'
            sql+='exit\n'
            docker('exec','-i','--user','oracle',runner.names[lane],'sqlplus','-s','/nolog',input=sql.encode())
        else:
            sql=(f"CREATE ROLE ly_observer LOGIN PASSWORD '{self.password}';\n"
                 "GRANT pg_monitor TO ly_observer;\n")
            docker('exec','-i',runner.names[lane],'psql','-X','-v','ON_ERROR_STOP=1','-U','adempiere','-d','idempiere',input=sql.encode())

    def start(self):
        runner=self.runner
        self.provision()
        docker('create','--name',self.container,'--label',runner.label,'--network',runner.network,
               '--memory','512m','--cpus','1','--cap-drop','ALL','--security-opt','no-new-privileges',
               '--mount',f'type=bind,src={runner.root/"src"},dst=/verifier/src,readonly',
               '--mount',f'type=bind,src={self.private},dst=/observations',runner.plan['local']['runner_image'])
        runner.remember('container',self.container);docker('start',self.container)
        self.process=subprocess.Popen(['docker','exec','-i',self.container,'python','-m',
                                       'lightyear_calibration.qualification_observer'],
                                      stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.process.stdin.write(canonical({'lane':self.lane,'password':self.password,
                                            'output':'/observations/capture','stop_file':'/observations/stop'}))
        self.process.stdin.close();self.process.stdin=None
        deadline=time.monotonic()+30
        while not (self.private/'capture/ready.json').exists():
            runner.check_cancel()
            if self.process.poll() is not None:raise JourneyAbort('observer-start-failed')
            require(time.monotonic()<deadline,'Observer readiness timeout')
            time.sleep(.05)
        return self

    def stop(self):
        require(self.process is not None,'Observer was not started')
        (self.private/'stop').write_bytes(b'stop\n')
        try:
            out,err=self.process.communicate(timeout=15)
            require(self.process.returncode==0,'Observer failed: '+(out+err).decode(errors='replace').replace(self.password,'[redacted]')[-1000:])
            return verify_capture(self.private/'capture')
        finally:
            if self.process.poll() is None:
                self.process.kill();self.process.communicate()
            docker('stop','--time','2',self.container,check_code=False)
            self.password=None

    def publish_after_application_stopped(self, destination):
        info=docker('inspect','--format','{{.State.Running}}',self.runner.runner,check_code=False)
        require(info.returncode!=0 or info.stdout.strip()==b'false','Application container can still write evidence')
        require((self.private/'capture/receipt.json').exists(),'Observer receipt missing')
        shutil.copytree(self.private/'capture',destination)
        return verify_capture(destination)
