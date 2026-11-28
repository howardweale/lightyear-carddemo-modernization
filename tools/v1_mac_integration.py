"""V1-C public graph-off rehearsal. The only provider backend is a bounded in-memory fixture child."""
from datetime import datetime, timedelta, timezone
from functools import partial
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if __name__=="__main__":
    if not (sys.flags.isolated and sys.dont_write_bytecode):raise SystemExit("v1-isolation")
    sys.path[:0]=[str(ROOT/"src"),str(ROOT)]
from tools import v1_mac_worker as b
from tools import launch_staged_public as launcher
from lightyear_factory import public_repair_controller as c
from lightyear_factory import public_repair_provider as p4
from lightyear_factory import public_repair_staged as s
from lightyear_factory import public_repair_worker as p5

SCENARIOS=("early-perfect","five-repairs","public-fail","uncertain-send","cleanup-refusal","closure-refusal")
INJECTED={"uncertain-send","cleanup-refusal","closure-refusal"}
KEY="fb51317ab1f5bba9677e543133364b34e893babcac279519b6f743d9568f3b37"
COPY="tests/fixtures/intcalc-c1/Main.java"
MODULES="34bb2ab91ace364bb0580d37a91a0c415282c4af943d82afbaa124383219be0d"


def expect(ok,why):
    b.require(ok,why)


def sheet(top):
    previous=b"".join((ROOT/("spec/V1-"+k+"-SHA256SUMS")).read_bytes() for k in "ABC")
    complete=(ROOT/"spec/MAC-REHEARSAL-SHA256SUMS").read_bytes()
    expect(previous==complete,"sheet-composition")
    seen=set()
    for row in complete.decode("ascii").splitlines():
        h,path=row.split("  ",1)
        expect(path not in seen and ".." not in path.split("/") and not Path(path).is_absolute(),"sheet-path")
        seen.add(path)
        origin=top/path[7:] if path.startswith("public/") else ROOT/path
        expect(origin==origin.resolve(strict=True) and origin.is_file() and origin.stat().st_size<=2*1024*1024,"sheet-file")
        expect(b.sha(origin.read_bytes())==h,"sheet-pin")
    return b.sha(complete)


def envelope_bytes(role,context,plan,source,analysis,history,feedback):
    row=s.ValueStagedController.project(role,context,plan,source,analysis,history,feedback)
    counted,generated,token_bound,_=p4.requests(row)
    components={k:len(c.canonical(row[k])) for k in ("public_context","plan","source","analysis","score_history","feedback") if k in row}
    raw=c.canonical(row)
    # Both bodies contain exactly one string for each nested JSON component. Keep
    # all real context-member framing, replacing only those two encoded strings.
    largest_body = max(len(counted), len(generated))
    wire_ceiling = largest_body
    nested_feedback_bytes = 0
    if "feedback" in row:
        nested_feedback_bytes = len(c.canonical(c.canonical(row["feedback"]).decode("ascii")))
        nested_history_bytes = len(c.canonical(c.canonical(row["score_history"]).decode("ascii")))
        # Canonical JSON is printable ASCII. At most two wire bytes per byte,
        # plus the two delimiters, even for all quotes and backslashes.
        wire_ceiling += 2 * s.values.CAP + 2 - nested_feedback_bytes
        wire_ceiling += 2 * 1024 + 2 - nested_history_bytes
    expect(wire_ceiling <= c.CAPS[role], "worst-bound")
    return dict(role=role,parts=components,framing=len(raw)-sum(components.values()),projection_sha256=c.sha(raw),
                count_bytes=len(counted),count_sha256=c.sha(counted),generation_bytes=len(generated),
                generation_sha256=c.sha(generated),reserve=4096,token_upper_bound=token_bound,
                feedback_string_bytes=nested_feedback_bytes,bound=wire_ceiling,slack=c.CAPS[role]-wire_ceiling)


def maximal_text(raw_cap,encoded_cap):
    # Reach both byte limits using two-byte UTF-8 characters encoded as six JSON bytes.
    difference=encoded_cap-raw_cap-2
    n,quotes=divmod(difference,4)
    text="\u0085"*n+'" '*quotes+"x"*(raw_cap-2*n-2*quotes)
    expect(len(text.encode())==raw_cap and len(c.canonical(text))==encoded_cap,"unicode-bound")
    return text


def full_value_feedback(source, suite):
    """Measure the real wire encoders with all 32 rows and exactly 8,192 canonical bytes."""
    failed = ("PC-06", "PC-09", "PC-11", "PC-12")
    feedback = dict(schema=s.values.SCHEMA, kind="PUBLIC_DIVERGENCE",
                    candidate_sha256=c.sha(source.encode()), public_suite_sha256=suite,
                    answer_manifest_sha256=s.values.KEY,
                    outcomes="".join("D" if case in failed else "M" for case in s.values.IDS),
                    exits={case: [12 if case in s.values.ABENDS else 0, 1] for case in failed},
                    samples=[], omitted=dict.fromkeys(s.values.CHANNELS, 0), truncated=True)
    feedback["omitted"]["stderr"] = 1
    # Unexpected public stderr. Quotes exercise JSON re-encoding in the provider bodies.
    prefix = b'"' * 32 + b"x" * 68
    for line in range(1, 8):
        for case in failed:
            feedback["samples"].append(dict(case=case, channel="stderr", index=line, expected=None,
                                            actual=s.values.value(prefix, True, True)))
    # Distribute the remaining printable bytes over the existing samples. Their lengths
    # stay three-digit numbers and fit the real 256-byte prefix, without a padding field.
    rows = feedback["samples"]
    extra, remainder = divmod(s.values.CAP - len(c.canonical(feedback)), len(rows))
    expect(extra >= 0 and len(prefix) + extra + bool(remainder) <= s.values.LINE_BYTES, "feedback-size")
    for index, row in enumerate(rows):
        data = prefix + b"x" * (extra + (index < remainder))
        row["actual"] = s.values.value(data, True, True)
    expect(len(rows) + len(failed) == s.values.ROWS and len(c.canonical(feedback)) == s.values.CAP,
           "feedback-size")
    return s.values.validate(feedback, c.sha(source.encode()), suite, "PUBLIC_DIVERGENCE")


def bounds(context,suite):
    plan=maximal_text(8192,16384)
    source=maximal_text(65536,73728)
    feedback = full_value_feedback(source, suite)
    hist=[dict(round=i,candidate="f"*16,match=0,different=16) for i in range(6)]
    rows=[]
    for index,role in enumerate(p4.SEQUENCE):
        rows.append(envelope_bytes(role,context,plan,source,plan,hist[:index//2],feedback))
    # Separately test the full retained history and account for all unused feedback/history capacity.
    maxima = {role: envelope_bytes(role, context, plan, source, plan, hist, feedback)
              for role in ("analysis", "repair")}
    worst = maxima["repair"]
    padded = min(row["slack"] for row in [*rows, *maxima.values()])
    expect(padded>=0 and len(rows)==12 and sum(c.HOLDS[r] for r in p4.SEQUENCE)==37664000,"worst-bound")
    try:c.projection("builder",context,plan+"x",source,plan,[],feedback)
    except c.Refused:pass
    else:raise ValueError("v1-oversize-accepted")
    return dict(slots=rows,maximum_history=worst,maximum_history_by_role=maxima,slack_after_full_envelopes=padded,
                synthetic_oversize_refused_before_count=True,holds=c.MAX_RESERVATION,ceiling=c.CEILING)


def fake_json(artifact):
    return c.canonical(dict(status="completed",model=c.MODEL,service_tier="flex",output=[dict(type="message",
            status="completed",role="assistant",content=[dict(type="output_text",text=c.canonical(artifact).decode())])],
            usage=dict(input_tokens=50,output_tokens=50,total_tokens=100,output_tokens_details=dict(reasoning_tokens=0))))


def scripted_child(pipe,scenario):
    """The spawn target has no key, socket, terminal or alternate transport."""
    os.environ.clear()
    try:
        expect(scenario in SCENARIOS,"scenario")
        pipe.send_bytes(b"READY")
        for i,role in enumerate(p4.SEQUENCE):
            for path in (p4.COUNT,p4.GENERATE):
                request=json.loads(pipe.recv_bytes(2*1024*1024))
                expect(set(request)=={"path","body","timeout_ms"} and request["path"]==path
                       and 0<request["timeout_ms"]<=1080000 and len(request["body"].encode())<=c.CAPS[role],"fake-bound")
                if scenario=="uncertain-send":
                    pipe.send_bytes(b"FAULT")
                    return
                if path==p4.COUNT:
                    reply=c.canonical({"object":"response.input_tokens","input_tokens":50})
                elif role in ("builder","repair"):
                    match=scenario in ("early-perfect","closure-refusal","cleanup-refusal") or (scenario=="five-repairs" and i==11)
                    fixture=(ROOT/(b.GOOD if match else COPY)).read_text(encoding="ascii")
                    reply=fake_json({"source":fixture+"\n// public rehearsal slot "+str(i)+"\n"})
                else:
                    reply=fake_json({"text":"Public fixture. Slot "+str(i)})
                pipe.send_bytes((200).to_bytes(2,"big")+reply)
    except (EOFError,BrokenPipeError):
        pass
    finally:pipe.close()


def bind(identifier,context,cfg,suite):
    now=datetime.now(timezone.utc)
    public_id=lambda label:c.sha(("V1 PUBLIC REHEARSAL "+identifier+" "+label).encode())
    commit=dict(schema="heldout-pre-run-commitment/1",committed_at=(now-timedelta(seconds=1)).isoformat(),
                commitment_sha256=public_id("synthetic commitment"),publication_receipt_sha256=public_id("synthetic receipt"))
    return dict(schema="staged-public-binding/1",mode="STAGED_PUBLIC",graph_mode="off",max_repairs=5,
                window_seconds=c.WINDOW,cap_microdollars=c.CEILING,model=c.MODEL,service_tier="flex",output_cap=32000,
                retries=0,authority_sha256=public_id("no authority"),implementation_sha256=MODULES,
                public_context_sha256=c.digest(context),public_suite_sha256=suite,heldout_commitment_sha256=c.digest(commit),
                runtime_profile_sha256=public_id("public profile"),feedback_contract_sha256=s.values.HASH,
                role_instructions_sha256=c.ROLE_HASH,public_case_count=16,pre_run_commitment=commit,
                approval_timestamp=now.isoformat(),public_answer_key_sha256=KEY,staged_policy_sha256=s.POLICY_HASH,
                worker_source_sha256=b.sha(Path(p5.__file__).read_bytes()),build_profile=dict(cli_sha256=cfg["cli_sha256"],
                helper_sha256=b.sha((ROOT/b.admission.HELPER).read_bytes()),jdk_sha256=p5.JDK,jre_sha256=p5.JRE))


class PublicGate:
    def __init__(self,binding,root):
        self.expected=c.canonical(binding)
        self.leaf=root/"rehearsal-claim"
    def admit(self,raw,deadline):
        expect(raw==self.expected and time.monotonic()<deadline,"synthetic-binding")
        p5.exclusive(self.leaf,c.sha(raw).encode())
        return dict(binding_sha256=c.sha(raw),receipt_sha256=b.sha(self.leaf.read_bytes()))


class Meter:
    def __init__(self):
        self.rows=[]
    def call(self,label,fn,*args,end=None):
        start=b.T()
        cutoff=None if end is None else int(end*1e9)
        try:return fn(*args)
        finally:
            finished=b.T()
            self.rows.append(dict(stage=label,start=start,end=finished,deadline=cutoff,
                             slack=None if cutoff is None else cutoff-finished,simulated_delay_ticks=0))


class CaseTiming:
    def __init__(self,worker,meter):
        self.worker,self.meter=worker,meter
        self.cases=[]
    def clock(self):
        self.constructed=b.T()
        return self.constructed/1e9
    def compile(self,source,index,end):
        return self.meter.call("compile",self.worker.compile,source,index,end,end=end)
    def run_public(self,built,inputs,stamp,date,end,limits):
        entered=b.T()
        obs=self.worker.run_public(built,inputs,stamp,date,end,limits)
        finish=b.T()
        execution=int(limits["execution_deadline"]*1e9)
        cleanup=int(limits["cleanup_deadline"]*1e9)
        self.cases.append(dict(constructed=self.constructed,entry=entered,end=finish,execution=execution,
                               cleanup=cleanup,construction_to_entry=entered-self.constructed,remaining=execution-entered,
                               cleanup_gap=cleanup-execution,receipt=obs["receipt_sha256"]))
        return obs


class PublicPorts(launcher.Ports):
    """Override only the owner factory/count path and recording of rehearsal timings or injected faults."""
    def __init__(self,gate,assemble,end,scenario,meter):
        super().__init__(gate,assemble,end)
        self.scenario,self.meter=scenario,meter
        self.wires=[]
        self.injected=False
    def record(self,name,row):
        return self.meter.call("record-"+name,super().record,name,row,end=self.deadline)
    def count(self,request,deadline):
        expect(self.storage is not None and not self.closed,"count-state")
        deadline=min(deadline,self.deadline)
        if self.models is None:
            owner=self.start_fake(deadline)
            try:self.models=p4.ProviderPorts(owner,self.storage,self.deadline)
            except BaseException:
                owner.close(deadline)
                raise
        counted,generated,bound,_=p4.requests(request)
        self.wires.append(dict(role=request["role"],count=len(counted),count_sha256=c.sha(counted),
                               generate=len(generated),generation_sha256=c.sha(generated),bound=bound))
        try:return self.meter.call("offline-count",self.models.count,request,deadline,end=deadline)
        except p4.Refused as err:
            self.injected=self.scenario=="uncertain-send" and str(err)=="provider-uncertain"
            raise

    def start_fake(self,deadline):
        make=partial(p4.KeyOwner,deadline,target=partial(scripted_child,scenario=self.scenario))
        return self.meter.call("fake-owner-start",make,end=deadline)

    def generate(self,request,deadline):
        return self.meter.call("offline-generate",super().generate,request,deadline,end=deadline)
    def close_models(self):
        was_closed=self.closed
        self.meter.call("close-reap",super().close_models,end=self.deadline)
        if self.scenario=="closure-refusal" and not was_closed:
            self.injected=True
            raise ValueError("synthetic-closure-refusal")
    def evaluate_public(self,built,suite,deadline):
        score=self.meter.call("public-evaluation",super().evaluate_public,built,suite,deadline,end=deadline)
        if self.scenario=="cleanup-refusal":
            self.injected=True
            raise ValueError("synthetic-cleanup-refusal")
        return score
    def retain_selected_jar(self,selected,binding,closure,deadline):
        return self.meter.call("retain-readback",super().retain_selected_jar,selected,binding,closure,deadline,end=deadline)


def run_scenario(name,identifier,top,root,cfg,context,suite,end,station):
    operation=c.sha((identifier+"-offline-"+name).encode())
    child=root/name
    child.mkdir(mode=0o700)
    meter=Meter()
    storage=launcher.Storage(root/"ledger",operation,end)
    ledger_dir=root/"ledger"/("public-repair-"+operation)
    binding=bind(identifier+"-"+name,context,cfg,suite)
    gate=PublicGate(binding,child)
    engine=p5.PublicWorker(root/"worker",operation,cfg["docker_binary"],cfg["cli_sha256"],cfg["docker_endpoint"],
                           ROOT/b.admission.HELPER,binding["build_profile"]["helper_sha256"])
    traced=CaseTiming(engine,meter)
    def assemble():
        adapter=b.public_adapter(top,traced,storage.retain_evaluation,b.key.ValuePublicAdapter)
        return storage,adapter,s.P5SelectedJarRetainer(engine,storage)
    ports=PublicPorts(gate,assemble,end,name,meter)
    # Preserve the original global deadline for every production port and the outer watchdog.
    controller=s.ValueStagedController(ports,binding,context)
    started=b.T()
    try:
        try:
            result=controller.run()
        except Exception:
            if name not in INJECTED or not ports.injected:raise
            expect((ledger_dir/"record-stopped.json").is_file() and not (ledger_dir/"record-result.json").exists(),"fault-result")
            expect(not (ledger_dir/s.LEAF).exists(),"fault-retained")
            outcome="EXPECTED_PUBLIC_FIXTURE_REFUSAL"
            manifest={"stopped":b.sha((ledger_dir/"record-stopped.json").read_bytes())}
        else:
            wanted="PUBLIC_FAIL" if name=="public-fail" else "PUBLIC_COMPLETE_HIDDEN_PENDING"
            expect(name not in INJECTED and result["status"]==wanted,"outcome")
            expect(len(ports.wires)==(2 if name=="early-perfect" else 12),"slots")
            expect(len(traced.cases)==(16 if name=="early-perfect" else 96),"cases")
            if name!="early-perfect":expect(result["reserved_microdollars"]==c.MAX_RESERVATION,"holds")
            expect(all(r["slack"] is None or r["slack"]>=0 for r in meter.rows),"deadline-slack")
            selected=result["selected"]
            manifest=dict(build=selected["build_receipt_sha256"],evaluation=selected["public_receipt_sha256"],
                          closure=b.sha((ledger_dir/"record-models-closed.json").read_bytes()),
                          result=b.sha((ledger_dir/"record-result.json").read_bytes()))
            expect(manifest["result"]==c.sha(c.canonical(result)+b"\n") and
                   manifest["closure"]==result["closure_record_sha256"],"result-readback")
            if wanted=="PUBLIC_COMPLETE_HIDDEN_PENDING":
                descriptor=result["retained_jar"]
                source=next(path for path in ledger_dir.glob("artifact-*-source.txt")
                            if b.sha(path.read_bytes())==descriptor["source_sha256"])
                manifest.update(source=b.sha(source.read_bytes()),jar=b.sha((ledger_dir/s.LEAF).read_bytes()))
                expect(manifest["jar"]==descriptor["readback_sha256"]==descriptor["jar_sha256"] and
                       result["hidden"]["status"]=="PENDING","jar-readback")
            outcome=wanted
        require_closed=ports.closed and ports.models is not None and ports.models.owner.closed
        expect(require_closed and not (ledger_dir/"record-hidden-invocation.json").exists(),"closure")
        try:gate.admit(c.canonical(binding),end)
        except (FileExistsError,p5.Refused):pass
        else:raise ValueError("v1-replay")
        clean=[]
        for path in sorted(engine.root.glob("*/cleanup.json")):
            data=path.read_bytes()
            expect(b.clean_receipt(json.loads(data)),"cleanup-record")
            clean.append(b.sha(data))
        expect(len(clean)==len(list(engine.root.glob("build-*")))+len(traced.cases),"cleanup-count")
        return dict(scenario=name,outcome=outcome,receipts=manifest,elapsed=b.T()-started,stages=meter.rows,
                    requests=ports.wires,cases=traced.cases,cleanup=clean,inventory=station.inventory(),
                    provider_sends=0,hidden_invocations=0,replayed=False,claim_sha256=b.sha(gate.leaf.read_bytes()))
    finally:
        try:ports.close_models()
        finally:storage.close()


def stalled_public_child(pipe):
    try:
        pipe.send_bytes(b"READY")
        time.sleep(30)
    finally:pipe.close()


def watchdogs():
    start=b.T()
    owner=p4.KeyOwner(time.monotonic()+8,target=stalled_public_child)
    try:
        wait_start=time.monotonic()
        try:owner.exchange(b"fixture",wait_start+6)
        except (p4.Refused,EOFError,OSError):
            expect(time.monotonic()-wait_start>=0.9,"owner-watchdog-early")
        else:raise ValueError("v1-child-watchdog")
    finally:owner.close(time.monotonic()+3)
    expect(owner.closed,"watchdog-reap")
    # Block a synthetic storage child before its first write; never stall a real APFS operation.
    ctx=b.multiprocessing.get_context("spawn")
    recv,send=ctx.Pipe(duplex=False)
    child=ctx.Process(target=stalled_public_child,args=(send,))
    at=b.T()
    try:
        child.start()
        send.close()
        expect(recv.poll(5) and recv.recv_bytes(16)==b"READY","storage-watchdog-start")
        child.join(.1)
        expect(child.is_alive(),"storage-watchdog-fixture")
    finally:
        recv.close()
        send.close()
        if child.pid is not None:
            if child.is_alive():child.kill()
            child.join(3)
            expect(not child.is_alive(),"storage-watchdog-reap")
        child.close()
    return dict(stalled_owner_ticks=at-start,stalled_storage_ticks=b.T()-at,child_reaped=True,
                storage_stall="synthetic before write; kernel I/O recovery unmeasured")


class SerialStation(b.Station):
    # The df observer owns a transient container. Take inventory between complete samples.
    def __init__(self,root,cfg):
        super().__init__(root,cfg)
        self.lock=b.threading.Lock()
    def inventory(self):
        with self.lock:return super().inventory()
    def sample(self):
        with self.lock:return super().sample()


def run_c(identifier,pin):
    try:
        return rehearse(identifier,pin)
    except p4.Refused as error:
        return {"refusal": p4.code(error)}


def rehearse(identifier,pin):
    top,root=b.session(identifier,"integration")
    cfg=b.host_settings(top,pin)
    source=b.admission.checkout(ROOT)
    expect(c.digest(source["modules"])==MODULES,"module-map")
    reviewed_sheet=sheet(top)
    context_raw=b.checked_bytes(top/"CURRENT-CONTEXT.json",launcher.CONTEXT,98304)
    context=s.strict(context_raw)
    expect(len(context_raw)==70765 and "NOTICE" in context and "LICENSE" not in context,"context")
    bdir=root.parent/"storage-worker"
    config=(bdir/"LOCAL-WORKER.json").read_bytes()
    qual=(bdir/"WORKER-QUALIFICATION.receipt").read_bytes()
    join=json.loads((bdir/"public_worker.receipt").read_bytes())
    expect(join==dict(schema="staged-worker-qualification-join/1",configuration_sha256=b.sha(config),
                      qualification_sha256=b.sha(qual)) and launcher.configuration(config)["docker_endpoint"]==cfg["docker_endpoint"]
           and json.loads(qual)["public_matches"]==16,"public-worker-join")
    expect(launcher.configuration(config)["docker_binary"]==cfg["docker_binary"],"worker-cli-join")
    tls= json.loads(b.staged.read_owned(root.parent/"MAC-TLS-1.receipt",8192))
    expect(tls.get("schema")=="mac-tls-1-public/1" and tls.get("rehearsal_id")==identifier and
           tls.get("child_reaped") is True and tls.get("verified") is True and
           tls.get("http_requests")==tls.get("application_bytes")==tls.get("credentials")==0 and
           tls.get("child_python_sha256")==tls.get("python_sha256")==b.sha(Path(sys.executable).resolve().read_bytes()),"tls-join")
    station=SerialStation(root,cfg)
    baseline=station.inventory()
    suite=b.adapter.PUBLIC_SUITE
    budget=bounds(context,suite)
    end=time.monotonic()+c.WINDOW
    observations=[]
    with station.sampling() as disk:
        for name in SCENARIOS:
            row=run_scenario(name,identifier,top,root,cfg,context,suite,end,station)
            expect(row["inventory"]==baseline and time.monotonic()<end,"final-inventory")
            observations.append(row)
            disk.append(station.sample())
        watchdog=watchdogs()
    expect(station.inventory()==baseline and time.monotonic()<end,"final-readback")
    expect(b.admission.checkout(ROOT)==source,"source-moved")
    ticks=[call["slack"] for obs in observations for call in obs["stages"] if call["slack"] is not None]
    expect(ticks and min(ticks)>=0,"slack")
    return dict(schema="v1-c-offline-public-rehearsal/1",minimum_stage_slack_ticks=min(ticks),
                tls_receipt_sha256=b.sha((root.parent/"MAC-TLS-1.receipt").read_bytes()),
                source_tree=source["tree"],rehearsal_id=identifier,host_config_sha256=pin,
                source_commit=source["commit"],
                complete_sheet_sha256=reviewed_sheet,public_worker_join_sha256=c.digest(join),
                bounds=budget,observations=observations,watchdogs=watchdog,samples=disk,
                ticks_per_second=10**9,time_origin="monotonic, local epoch",simulated_delays_ticks=0,
                live_network_sends=0,actual_provider_cost_microdollars=0,operator_qualification=False)


if __name__=="__main__":
    sys.exit(b.cli(run_c,c.WINDOW))
