"""Owner-run public rehearsal. No production replay path or provider transport."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import multiprocessing
import math
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
if __name__=="__main__":
    if not (sys.flags.isolated and sys.dont_write_bytecode):
        raise SystemExit("v1-isolation")
    sys.path[:0]=[str(ROOT/"src"),str(ROOT)]
from lightyear_factory import public_repair_durable as durable
from lightyear_factory import public_repair_staged as staged
from lightyear_factory import public_repair_worker as worker
from lightyear_factory import public_repair_answer_key as key
from lightyear_factory import public_evaluator_adapter as adapter
from lightyear_factory import staged_run_admission as admission
from tools import launch_staged_public as launcher
from tools.v1_mac_tls import ID

T=time.monotonic_ns
sha=lambda b:hashlib.sha256(b).hexdigest()
GOOD="spec/V1-PUBLIC-PLAYBACK.java"
BAD="public class Main { invalid syntax }"
SLOW="public class Main {public static void main(String[] a)throws Exception {Thread.sleep(60000);}}"
FLOOD="public class Main {public static void main(String[] a){byte[] b=new byte[65536]; for(int i=0;i<512;i++) System.out.write(b,0,b.length);}}"


def require(ok,code):
    if not ok: raise ValueError("v1-"+code)


def observed_path(path):
    path=Path(path)
    require(".lightyear-staged-public" not in path.parts,"reserved-path")
    require(path.is_absolute() and path.resolve(strict=True)==path,"path")
    return path


def checked_bytes(path,digest,limit):
    data=staged.read_owned(path,limit)
    require(sha(data)==digest,"hash")
    return data


def session(identifier,phase):
    require(sys.platform=="darwin" and platform.machine()=="arm64" and ID.fullmatch(identifier),"host-id")
    require(phase in ("storage-worker","integration"),"phase")
    import pwd
    home=Path(pwd.getpwuid(os.getuid()).pw_dir)
    top=observed_path(home/".lightyear-v1-rehearsals")
    _,fd,_=durable.open_parent(top)
    durable.close_quiet(fd)
    root=top/identifier
    root.mkdir(mode=0o700,exist_ok=True)
    _,fd,_=durable.open_parent(root)
    durable.close_quiet(fd)
    run=root/phase
    run.mkdir(mode=0o700)
    for n in ("ledger","worker","client"):
        (run/n).mkdir(mode=0o700)
    return top,run


def host_settings(top,expected):
    raw=checked_bytes(top/"PUBLIC-HOST.json",expected,32768)
    row=key.strict(raw)
    require(set(row)=={"docker_binary","docker_endpoint","cli_sha256","disk_image","ledger_device",
            "host_min","ledger_min","backing_min","vm_min","shared_physical_store","jdk_config","jre_config"},"host-fields")
    for field in ("host_min","ledger_min","backing_min","vm_min"):
        require(type(row[field]) is int and row[field]>0,"host-minimum")
    require(type(row["shared_physical_store"]) is bool and type(row["ledger_device"]) is int,"store")
    for field in ("jdk_config","jre_config","cli_sha256"):
        require(key.digest(row[field]),"host-pin")
    observed_path(row["docker_binary"])
    require(isinstance(row["docker_endpoint"],str) and row["docker_endpoint"].startswith("unix:///"),"endpoint")
    observed_path(row["docker_endpoint"][7:])
    launcher.configuration(key.canonical(dict(schema="staged-local-worker/1",docker_binary=row["docker_binary"],
                                              docker_endpoint=row["docker_endpoint"])))
    require(sha(worker.read(observed_path(row["docker_binary"]),64*1024*1024))==row["cli_sha256"],"cli")
    require(observed_path(row["disk_image"]).is_file(),"vm-backing")
    return row


def shell(args,timeout=20):
    return subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                          env={},timeout=timeout,check=True).stdout


class Station:
    def __init__(self,run,config):
        self.root,self.config=run,config
        self.docker=[config["docker_binary"],"--config",str(run/"client"),"--host",config["docker_endpoint"]]
        require(run.stat().st_dev==config["ledger_device"],"ledger-device")
        rows = shell(["/bin/df", "-P", str(run)]).splitlines()
        fields = rows[1].split() if len(rows) == 2 else []
        require(fields and re.fullmatch(rb"/dev/disk[0-9]+(?:s[0-9]+)*", fields[0]),
                "ledger-disk-device")
        device = fields[0].decode("ascii")
        disk = plistlib.loads(shell(["/usr/sbin/diskutil", "info", "-plist", device]))
        require(str(disk.get("FilesystemType","")).lower()=="apfs","ledger-apfs")
        self.fs=disk["FilesystemType"]
        require(shell(self.docker+["info","--format","{{.OSType}}/{{.Architecture}}"]).strip()
                in (b"linux/aarch64",b"linux/arm64"),"daemon-architecture")
        for kind in ("jdk","jre"):
            ref=worker.image(kind)
            info=json.loads(shell(self.docker+["image","inspect",ref]))
            require(len(info)==1 and info[0]["Id"]=="sha256:"+config[kind+"_config"]
                    and info[0]["Architecture"]=="arm64" and info[0]["Os"]=="linux","image-identity")

    def inventory(self):
        result={}
        for key_,args in (("containers",["ps","-aq","--no-trunc"]),("volumes",["volume","ls","-q"]),
                          ("images",["images","-aq","--no-trunc"])):
            lines=sorted(shell(self.docker+args).splitlines())
            result[key_]=dict(count=len(lines),sha256=sha(b"\n".join(lines)))
        return result

    def sample(self):
        backing=Path(self.config["disk_image"])
        lines=shell(self.docker+["run","--rm","--pull=never","--platform=linux/arm64","--read-only",
                   "--network=none","--cap-drop=ALL","--security-opt=no-new-privileges","--user=65534:65534",
                   "--pids-limit=16","--memory=64m","--log-driver=none","--entrypoint=/bin/df",worker.image("jre"),"-Pk","/"]).splitlines()
        require(len(lines)==2 and lines[1].split()[-1]==b"/","vm-df")
        data=dict(host=shutil.disk_usage(Path.home()).free,ledger=shutil.disk_usage(self.root).free,
                  backing=shutil.disk_usage(backing).free,vm=int(lines[1].split()[-3])*1024)
        require(all(v>=self.config[k+"_min"] for k,v in data.items()),"headroom")
        return dict(tick=T(),unix_ns=time.time_ns(),available=data)

    @contextmanager
    def sampling(self,period=20):
        samples=[self.sample()]
        stopped=threading.Event()
        failures=[]
        def watch():
            while not stopped.wait(period):
                try:samples.append(self.sample())
                except Exception:
                    failures.append(True)
                    return
        thread=threading.Thread(target=watch,daemon=True)
        thread.start()
        try:yield samples
        finally:
            stopped.set()
            thread.join(22)
            require(not thread.is_alive() and not failures,"headroom-sampler")
            samples.append(self.sample())


def ledger_probe(run,operation,end):
    start=T()
    ledger=staged.StagedDurablePorts(run/"ledger",operation,end)
    writes=[]
    def timed(action,*args):
        at=T()
        digest=action(*args)
        writes.append(T()-at)
        return digest
    try:
        small=timed(ledger.record,"small",{"public":True})
        require(small==sha(b'{"public":true}\n'),"ledger-lf")
        timed(ledger.retain_artifact,"builder-0","source","a"*65536)
        timed(ledger.retain_jar,b"j"*staged.JAR_BYTES)
        # Exercise both the file count and total byte caps at the same time.
        files_written, bytes_written = ledger.written_usage
        remaining_count = durable.FILE_COUNT - files_written
        remaining_bytes = durable.TOTAL_BYTES - bytes_written
        overhead=len(durable.canonical({"p":""}))+1
        for i in range(remaining_count):
            size=min(durable.RECORD_BYTES,remaining_bytes-overhead*(remaining_count-i-1))
            timed(ledger.record,"fill-"+str(i),{"p":"x"*(size-overhead)})
            remaining_bytes-=size
        require(remaining_bytes==0,"ledger-fill")
    finally:ledger.close()
    folder=run/"ledger"/("public-repair-"+operation)
    leaves=list(folder.iterdir())
    require(len(leaves)==durable.FILE_COUNT and sum(x.stat().st_size for x in leaves)==durable.TOTAL_BYTES
            and all(stat.S_ISREG(x.lstat().st_mode) and x.stat().st_nlink==1 and x.stat().st_uid==os.getuid()
                    and stat.S_IMODE(x.stat().st_mode)==0o600 for x in leaves),"ledger-readback")
    try:staged.StagedDurablePorts(run/"ledger",operation,end)
    except (durable.Refused,FileExistsError):pass
    else:raise ValueError("v1-duplicate-operation")
    second=sha((operation+"duplicate-leaf").encode())
    other=staged.StagedDurablePorts(run/"ledger",second,end)
    try:
        original=other.record("same",{"v":1})
        try:other.record("same",{"v":2})
        except durable.Refused as err:duplicate=err.public_record()
        else:raise ValueError("v1-duplicate-leaf")
        path=run/"ledger"/("public-repair-"+second)/"record-same.json"
        require(sha(path.read_bytes())==original,"duplicate-readback")
    finally:other.close()
    return dict(small_sha256=small,small_bytes=len(b'{"public":true}\n'),file_count=len(leaves),
                bytes=durable.TOTAL_BYTES,duplicate_refusal=duplicate,file_sync=True,directory_sync=True,
                maximum_write_ticks=max(writes),elapsed_ticks=T()-start,write_ticks=writes,power_loss_tested=False)


class TimedWorker(worker.PublicWorker):
    def __init__(self,*args):
        super().__init__(*args)
        self.timings=[]
        self.constructed=None
    def clock(self):
        self.constructed=T()
        return self.constructed/1e9
    def run_public(self,built,inputs,timestamp,processing_date,deadline,limits):
        entry=T()
        require(self.constructed is not None and entry>=self.constructed,"timing-order")
        execution=math.floor(limits["execution_deadline"]*1e9)
        cleanup=math.floor(limits["cleanup_deadline"]*1e9)
        row=super().run_public(built,inputs,timestamp,processing_date,deadline,limits)
        self.timings.append(dict(constructed=self.constructed,construction_to_entry=entry-self.constructed,entry=entry,execution=execution,cleanup=cleanup,end=T(),remaining=execution-entry,
                            cleanup_gap=cleanup-execution,receipt=row["receipt_sha256"],
                            timed_out=row["timed_out"],output_capped=row["output_capped"]))
        return row


def engine(run,op,cfg):
    helper=ROOT/admission.HELPER
    return TimedWorker(run/"worker",op,cfg["docker_binary"],cfg["cli_sha256"],cfg["docker_endpoint"],
                       helper,sha(helper.read_bytes()))


def public_adapter(top,runtime,retain,adapter_type=key.FrozenPublicAdapter):
    archive=checked_bytes(top/"answer-key.zip","e8dd6b85a39afbb5c3901fe400e479d9798adae8b7954918db8dc87fec71f4aa",65536)
    review=key.published_key((ROOT/admission.RELEASE_BINDING).read_bytes(),launcher.TAG,archive)
    return adapter_type(runtime,top/"answers",(ROOT/admission.SUITE).parent,ROOT,review,retain,clock=runtime.clock)


def clean_receipt(row):
    removed=row.get("removed",[])
    return (row.get("cleanup") is True and sorted(x.get("kind","") for x in removed)==["container","container","volume"]
            and all(x.get("absence_confirmed") is True for x in removed))


def qualify(top,run,op,cfg,end):
    store=launcher.Storage(run/"ledger",op,end)
    runtime=engine(run,op,cfg)
    try:
        public=public_adapter(top,runtime,store.retain_evaluation)
        started=T()
        phase=min(end,time.monotonic()+600)
        built=public.build((ROOT/GOOD).read_text(encoding="ascii"),0,phase)
        require(built["status"]=="BUILT","fixture-build")
        compiled=T()
        scored=public.evaluate_public(built,public.suite,phase)
        require(scored["match"]==16 and scored["different"]==0 and len(runtime.timings)==16,"playback")
        require(sum(case["compare_output_files"] for case in public.cases)==13,"comparison-policy")
        bad=public.build(BAD,1,min(end,time.monotonic()+200))
        require(bad["status"]=="COMPILE_FAILED","bad-source")
        probes=[]
        for i,source in enumerate((SLOW,FLOOD),2):
            limit=min(end,time.monotonic()+600)
            candidate=public.build(source,i,limit)
            case=public.cases[0]
            now=runtime.clock()
            x,y=adapter.case_deadlines(now,min(limit,now+20))
            obs=runtime.run_public(candidate,case["inputs"],case["timestamp"],case["processing_date"],y,
                                   dict(execution_deadline=x,cleanup_deadline=y,output_bytes=worker.DATA))
            require(obs["timed_out"] is (i==2) and obs["output_capped"] is (i==3) and obs["cleanup"] is True,"probe")
            probes.append(obs["receipt_sha256"])
        cleanup=[]
        for path in sorted(runtime.root.glob("*/cleanup.json")):
            raw=path.read_bytes()
            row=json.loads(raw)
            require(clean_receipt(row),"cleanup-readback")
            cleanup.append(sha(raw))
        require(len(cleanup)==22,"cleanup-count")
        require(time.monotonic()<end,"deadline")
        return dict(build_ticks=compiled-started,build_receipt=built["build_receipt_sha256"],
                    jar_sha256=runtime.built[built["build_receipt_sha256"]][2],evaluation=scored["receipt_sha256"],
                    public_matches=16,file_comparisons=13,timings=runtime.timings,probes=probes,cleanup=cleanup)
    finally:store.close()


def run_b(identifier,pin):
    top,run=session(identifier,"storage-worker")
    cfg=host_settings(top,pin)
    station=Station(run,cfg)
    first=station.inventory()
    initial=station.sample()
    end=time.monotonic()+1800
    with station.sampling() as samples:
        ledger=ledger_probe(run,sha((identifier+"-volume").encode()),end)
        samples.append(station.sample())
        public=qualify(top,run,sha((identifier+"-worker").encode()),cfg,end)
    require(first==station.inventory(),"reconciliation")
    local=key.canonical(dict(schema="staged-local-worker/1",docker_binary=cfg["docker_binary"],docker_endpoint=cfg["docker_endpoint"]))
    raw=key.canonical(public)
    join=dict(schema="staged-worker-qualification-join/1",configuration_sha256=sha(local),qualification_sha256=sha(raw))
    for name,data in [("LOCAL-WORKER.json",local),("WORKER-QUALIFICATION.receipt",raw),("public_worker.receipt",key.canonical(join))]:
        worker.exclusive(run/name,data)
    return dict(schema="v1-b-public-rehearsal/1",rehearsal_id=identifier,host_config_sha256=pin,ledger=ledger,
                worker_join_sha256=sha(key.canonical(join)),public_worker=public,baseline=first,initial=initial,disk_samples=samples,ledger_fs=station.fs,
                minimum_observed={k:min(r["available"][k] for r in samples+[initial]) for k in initial["available"]},
                shared_physical_store=cfg["shared_physical_store"],ticks_per_second=10**9,
                reserve_bytes={k:cfg[k+"_min"] for k in initial["available"]},operator_qualification=False)


def isolated_action(pipe,action,identifier,pin):
    try:
        os.environ.clear()
        value=action(identifier,pin)
        pipe.send_bytes(json.dumps(value,sort_keys=True).encode())
    except durable.Refused as error:
        pipe.send_bytes(json.dumps({"refusal":error.public_record()}).encode())
    except ValueError as error:
        code = str(error)
        if not re.fullmatch(r"v1-[a-z0-9-]+", code):
            code = "v1-operation-refused"
        pipe.send_bytes(json.dumps({"refusal": code}, separators=(",", ":")).encode())
    except (Exception,KeyboardInterrupt):
        pipe.send_bytes(b'{"refusal":"v1-operation-refused"}')
    finally:
        pipe.close()


def supervise(action,identifier,pin,seconds):
    require(ID.fullmatch(identifier) and key.digest(pin),"arguments")
    require(sys.platform=="darwin" and platform.machine()=="arm64" and sys.flags.isolated and sys.dont_write_bytecode,"host")
    require(set(os.environ)<={"LC_CTYPE","__CF_USER_TEXT_ENCODING"},"environment")
    os.environ.clear()
    ctx=multiprocessing.get_context("spawn")
    recv,send=ctx.Pipe(duplex=False)
    child=ctx.Process(target=isolated_action,args=(send,action,identifier,pin))
    end=time.monotonic()+seconds
    try:
        child.start()
        send.close()
        require(recv.poll(max(0,end-time.monotonic()-5)),"watchdog")
        raw=recv.recv_bytes(2*1024*1024)
        child.join(max(0,end-time.monotonic()-3))
        require(child.exitcode==0,"exit")
        return json.loads(raw)
    finally:
        recv.close()
        send.close()
        if child.pid is not None:
            if child.is_alive():
                child.kill()
                child.join(max(0,end-time.monotonic()))
            require(not child.is_alive(),"reap")
        child.close()


def cli(action,seconds=1800):
    p=argparse.ArgumentParser()
    p.add_argument("--rehearsal-id",required=True)
    p.add_argument("--public-host-sha256",required=True)
    args=p.parse_args()
    try:
        row=supervise(action,args.rehearsal_id,args.public_host_sha256,seconds)
        print(json.dumps(row,sort_keys=True))
        return 2 if "refusal" in row else 0
    except durable.Refused as err:
        print(json.dumps(err.public_record()),file=sys.stderr)
        return 2
    except (Exception,KeyboardInterrupt):
        print("v1-public-rehearsal-refused",file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    sys.exit(cli(run_b))
