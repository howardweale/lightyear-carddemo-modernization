"""A3-only checkpoint restoration; unchanged isolated application execution."""
import json,subprocess
from lightyear_calibration.contracts import canonical,require,verify,read_json
from lightyear_calibration.journey_order import save
from lightyear_calibration.journey_runtime import docker
from lightyear_calibration.ms94_a3_checkpoint_v2 import RECIPE,audit
from lightyear_calibration.native_reconciliation import state
from tools.qualification_private_runner import PrivateRunner


def verify_restore(run,lane):
    folder=run/'checkpoint-restore'/lane
    recorded=read_json(folder/'restore.json');verify(recorded)
    actual=audit(folder/'before',folder/'after',lane)
    require(recorded['audit']==actual and recorded['recipe_sha256']==RECIPE['content_sha256']
            and recorded['exact_admitted_multisets'] and recorded['passed'],'Native restore audit differs')
    for moment,name in (('before',lane+'-admitted-entry-multisets.json'),('after',lane+'-entry-multisets.json')):
        snap=state(folder/moment,lane)
        require({k:v['row_multiset'] for k,v in snap['tables'].items()}==read_json(run/'inputs'/name),
                'Restored rows differ from pinned checkpoint')
    return recorded


class A3Runner(PrivateRunner):
    def worker(self,command,payload,timeout):
        if command=='prepare' and self.plan['a3_checkpoint_profile']=='perturbed':
            lane=payload['lane'];self.checkpoint('restore-admitted-derived-checkpoint:'+lane)
            spec={'lane':lane,'password':self.password,'recipe_sha256':RECIPE['content_sha256'],
                'output':self.inside(self.run/'checkpoint-restore'/lane),
                'base_multisets':self.inside(self.run/'inputs'/(lane+'-admitted-entry-multisets.json')),
                'derived_multisets':self.inside(self.run/'inputs'/(lane+'-entry-multisets.json'))}
            p=subprocess.Popen(['docker','exec','-i',self.runner,'python','-m','lightyear_calibration.ms94_a3_restore'],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            data=canonical(spec)
            try:
                while True:
                    try:out,err=p.communicate(input=data,timeout=1);break
                    except subprocess.TimeoutExpired:data=None;self.check_cancel()
                if p.returncode:
                    safe=(out+err).decode(errors='replace').replace(self.password,'[redacted]')
                    save(self.run/'restore-errors'/f'{lane}.json',{'diagnostic':safe[-8000:]})
                    raise RuntimeError('Native derived-checkpoint restore failed; private evidence preserved')
                verify_restore(self.run,lane)
            finally:
                if p.poll() is None:p.kill();p.communicate();docker('kill',self.runner,check_code=False)
        return super().worker(command,payload,timeout)
