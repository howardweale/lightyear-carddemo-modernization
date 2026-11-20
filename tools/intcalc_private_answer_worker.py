"""Howard-only private container worker. No CLI output except framed private pipe."""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time

from tools import generate_intcalc_heldout_inputs as generator
from tools import intcalc_reference_execution as ref
from tools import intcalc_reference_provisional as provisional
from tools import intcalc_heldout_encrypted_stream as stream


def require(ok, code='answer-worker'):
    if not ok: raise stream.Refused(code)


def mount_tmpfs(text, target):
    rows=[line.split() for line in text.splitlines()]
    matches=[r for r in rows if len(r)>6 and r[4]==target and '-' in r]
    require(len(matches)==1 and matches[0][matches[0].index('-')+1]=='tmpfs')


def emit(row):
    raw=stream.canonical(row)
    require(len(raw)<=stream.CASE_CAP)
    sys.stdout.buffer.write(len(raw).to_bytes(8,'big')+raw);sys.stdout.buffer.flush()


def private_inventory(destination):
    version, _ = ref.checked(["dpkg-query", "-W", "-f=${Version}", "gnucobol3"], ref.ROOT, time.monotonic()+30)
    require(version.decode()=="3.1.2-5.1ubuntu1")
    deadline = time.monotonic() + 120
    compiler, _ = ref.checked(["cobc", "-V"], ref.ROOT, deadline)
    runtime, _ = ref.checked(["cobcrun", "-V"], ref.ROOT, deadline)
    packages, _ = ref.checked(["dpkg-query", "-W",
                          "-f=${Package}\t${Version}\t${Architecture}\n"], ref.ROOT, deadline)
    licences = {}
    for p in sorted(Path("/usr/share/doc").glob("*/copyright")):
        if p.is_file() and not p.is_symlink():
            licences[p.relative_to("/usr/share/doc").as_posix()] = ref.sha(ref.bounded(p))
    libraries = {}
    for p in sorted(Path("/usr/lib/x86_64-linux-gnu").glob("libcob.so*")):
        resolved = p.resolve()
        if resolved.name in libraries:
            continue
        dependencies, _ = ref.checked(["ldd", str(resolved)], ref.ROOT, deadline)
        libraries[resolved.name] = {"sha256": ref.sha(ref.bounded(resolved)),
                                   "dynamic_dependencies": dependencies.decode("utf-8")}
    ref.exclusive(destination, ref.canonical({"schema": "reference-inventory/1",
        "compiler": compiler.decode("utf-8"), "runtime": runtime.decode("utf-8"),
        "packages": packages.decode("utf-8"), "copyright_files": licences,
        "libcob_inventory": libraries,
        "isam_backend_review": "PENDING", "licence_review": "PENDING",
        "qualified": False, "limit": ref.LIMIT}) + b"\n")

def answer(case, sequence, layouts, compiled, work, deadline):
    require(set(case['inputs'])==set(generator.COPYBOOKS))
    converted={dd:ref.bridge(raw,*ref.DDS[dd],layout=layouts[dd],
                 order_observable=dd in ('ACCTFILE','TCATBALF')) for dd,raw in case['inputs'].items()}
    env=ref.clock_env(case['timestamp'],case['processing_date'])
    for dd,raw in converted.items():
        ref.exclusive(work/(dd+'.flat'),raw)
        ref.checked([str(compiled/dd),'load',str(work/(dd+'.flat')),str(work/dd)],work,deadline)
        env['DD_'+dd]=str(work/dd)
    ref.exclusive(work/'TRANSACT',b'');env['DD_TRANSACT']=str(work/'TRANSACT')
    code,out,err=ref.run([str(compiled/'program')],work,deadline,env)
    require(code in (0,12))
    err,diagnostics=ref.split_runtime_diagnostics(err)
    # Runtime diagnostics are not model output; never written persistently.
    del diagnostics
    outputs=dict(ACCTFILE=b'',TRANSACT=b'',stdout=out,stderr=err)
    if code==0:
        ref.checked([str(compiled/'ACCTFILE'),'dump',str(work/'ACCTFILE.after'),str(work/'ACCTFILE')],work,deadline)
        outputs['ACCTFILE']=ref.decode_output(ref.bounded(work/'ACCTFILE.after'),300)
        outputs['TRANSACT']=ref.decode_output(ref.bounded(work/'TRANSACT'),350)
    row=dict(sequence=sequence,inputs={k:v.hex() for k,v in case['inputs'].items()},
        processing_date=case['processing_date'],timestamp=case['timestamp'],
        outputs={k:v.hex() for k,v in outputs.items()},exit=code,compare_output_files=code==0)
    stream.checked_case(row,sequence)
    return row


def worker():
    require(os.name=='posix' and platform.system()=='Linux' and platform.machine()=='x86_64')
    require(not os.environ.get('GITHUB_ACTIONS'))
    mounts=Path('/proc/self/mountinfo').read_text()
    for path in ('/work','/tmp'):mount_tmpfs(mounts,path)
    tempfile.tempdir='/tmp'
    policy=ref.strict(ref.bounded(Path('/answer-policy.json')))
    require(policy['schema']=='heldout-answer-policy/1')
    for path,digest in policy['source_hashes'].items():
        require(not Path(path).is_absolute() and '..' not in Path(path).parts)
        require(stream.sha(ref.bounded(ref.ROOT/path))==digest)
    require(stream.sha(Path(__file__).read_bytes())==policy['worker_sha256'])
    source=policy['generator_sources'];layouts=generator.load_sources(ref.ROOT,source)
    work=Path('/work');inventory=work/'inventory.json'
    private_inventory(inventory)
    require(provisional.inventory_digest(ref.strict(ref.bounded(inventory)))==policy['package_library_sha256'])
    binding=ref.strict(ref.bounded(ref.ROOT/policy['reference_binding']['path']))
    require(stream.sha(ref.bounded(ref.ROOT/policy['reference_binding']['path']))==policy['reference_binding']['sha256'])
    require(type(policy['count']) is int and 1<=policy['count']<=64)
    deadline=time.monotonic()+2400
    compiled=work/'compiled';compiled.mkdir(mode=0o700)
    ref.compile_reference(compiled,min(deadline,time.monotonic()+300),binding['compile_sources'])
    seed=sys.stdin.buffer.read(33);require(len(seed)==32)
    cases=generator.generate_inputs(seed,policy['count'],layouts)
    payload=generator.private_payload(cases,source)
    input_hash=hashlib.sha256(payload).hexdigest()
    del seed,payload
    emit(dict(schema='heldout-input-commitment/1',sha256=input_hash,count=len(cases)))
    for sequence,case in enumerate(cases):
        folder=work/('case-'+str(sequence));folder.mkdir(mode=0o700)
        try: emit(answer(case,sequence,layouts,compiled,folder,min(deadline,time.monotonic()+30)))
        finally: shutil.rmtree(folder)  # Only this operation's tmpfs case folder.
    emit(dict(schema='heldout-answer-end/1',count=len(cases),complete=True))
    del cases
    return 0


if __name__=='__main__':
    try: raise SystemExit(worker())
    except Exception:
        # Private exception strings and traceback never enter Docker logs/terminal.
        sys.stderr.write('answer-worker\n');raise SystemExit(2) from None
