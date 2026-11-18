"""CI-only public Docker plumbing; never a private or provider entry."""
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import time
from lightyear_factory.public_repair_worker import LimitsRefused, PublicWorker, DATA, c


class FixtureWorker(PublicWorker):
    def run_public(self, *args):
        elapsed = time.monotonic() - self.case_start
        self.max_call_delay_ns = max(self.max_call_delay_ns, math.ceil(elapsed * 1e9))
        try:
            return super().run_public(*args)
        except LimitsRefused as error:
            print(json.dumps(dict(**error.evidence, max_fixture_call_delay_ns=self.max_call_delay_ns)),
                  flush=True)
            raise


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise SystemExit('worker-qualification-ci-only')
    repo=Path(__file__).resolve().parents[1]
    root=Path(tempfile.mkdtemp(prefix='public-worker-',dir=os.environ['RUNNER_TEMP'])).resolve()
    root.chmod(0o700)
    binary=Path(shutil.which('docker')).resolve()
    helper=repo/'factory/cobol-runtime/src/org/lightyear/cobol/RecordNumbers.java'
    worker=FixtureWorker(root,'a'*64,binary,c.sha(binary.read_bytes()),'unix:///var/run/docker.sock',
                        helper,c.sha(helper.read_bytes()))
    start=time.monotonic();deadline=start+600
    source=(repo/'tests/fixtures/intcalc-c1/Main.java').read_text(encoding='utf-8')
    built=worker.compile(source,0,deadline)
    assert built['exit_code']==0 and built['cleanup'] is True
    identity=dict(status='BUILT',artifact_sha256=built['artifact_sha256'],build_receipt_sha256=built['receipt_sha256'])
    input_bytes={name:b'' for name in ('ACCTFILE','TCATBALF','DISCGRP','XREFFILE')}
    input_bytes['ACCTFILE']=b'PUBLIC-FIXTURE-ONLY'
    worker.max_call_delay_ns = 0
    for _ in range(16):
        now=time.monotonic();limits=dict(execution_deadline=now+15,cleanup_deadline=now+20,output_bytes=DATA)
        worker.case_start = now
        row=worker.run_public(identity,input_bytes,'2026-11-17-00.00.00.000000','2026111700',now+20,limits)
        assert row['exit']==0 and row['cleanup'] and not row['timed_out'] and not row['output_capped']
        assert row['ACCTFILE']==input_bytes['ACCTFILE'] and row['TRANSACT']==b''
        assert row['stdout']==row['stderr']==b''
    # Every phase must remove candidate, collector and tmpfs volume, with daemon
    # absence readback. Outputs above prove collection survived candidate exit.
    cleanups=list(worker.root.glob('*/cleanup.json'))
    assert len(cleanups)==17
    for path in cleanups:
        cleanup=json.loads(path.read_bytes())
        assert cleanup['cleanup'] is True and len(cleanup['removed'])==3
        assert sorted(r['kind'] for r in cleanup['removed'])==['container','container','volume']
        assert all(r['absence_confirmed'] for r in cleanup['removed'])
    assert time.monotonic()<deadline
    bad=worker.compile('public class Main { invalid syntax }',1,time.monotonic()+200)
    assert bad['exit_code']==1 and bad['diagnostic_mode']=='javac-XDrawDiagnostics' and bad['stderr']
    print(json.dumps(dict(schema='public-worker-fixture/1',public_cases=16,compile_failure=True,
        max_fixture_call_delay_ns=worker.max_call_delay_ns,
        elapsed_milliseconds=int((time.monotonic()-start)*1000),qualified=False)))


if __name__=='__main__':main()
