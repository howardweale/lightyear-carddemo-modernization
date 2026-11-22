"""H3-B1. One claimed, private operation. The evaluator is a trusted code port, never bundle-selected."""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import time

from lightyear_factory import public_repair_controller as ctl
from lightyear_factory import public_repair_durable as durable
from lightyear_factory import public_repair_staged as staged
from lightyear_factory import staged_run_admission as admission
from tools import intcalc_h3_custody as custody
from tools import intcalc_hidden_answer_receiver as rx
from tools import intcalc_native_candidate_runtime as native
from tools import intcalc_private_reference_host as h1


PINS = ("result binding closure provider_closed jar build public_eval stage1_approval host_qualification "
        "custody image_binding image_manifest image_config licences native_qualification runtime_policy "
        "route_qualification source_manifest").split()
RECEIVER_KEYS = ("operation_id stage1_sha256 jar_sha256 completion_sha256 bindings_sha256 "
                 "input_sha256 age_sha256 source_manifest_sha256 count plaintext_cap")


class Refused(ValueError):
    pass


def check(ok):
    if not ok:
        raise Refused("stage2-refused")


def ledger_row(raw):
    row=staged.strict(raw)
    check(type(row) is dict and ctl.canonical(row)+b"\n"==raw)
    return row


def approve(raw, expected, evidence, now):
    check(type(raw) is bytes and len(raw)<=65536 and ctl.hash_ok(expected) and ctl.sha(raw)==expected)
    row=rx.strict(raw,65536)
    rx.shape(row,"schema operator mode operation_id valid_from expires_at source_commit source_tree "
             "host_profile_sha256 h2_operation_id receiver pins usb_mount_id usb_device")
    check(row["schema"]=="private-stage2-approval/1" and row["operator"]=="Howard"
          and row["mode"]=="EXACT_SELECTED_JAR_ONCE" and ctl.hash_ok(row["operation_id"])
          and ctl.hash_ok(row["host_profile_sha256"]) and ctl.hash_ok(row["h2_operation_id"])
          and all(admission.oid(row[k]) for k in ("source_commit","source_tree"))
          and type(row["usb_mount_id"]) is int and row["usb_mount_id"]>0
          and type(row["usb_device"]) is str and re.fullmatch(r"[0-9]+:[0-9]+",row["usb_device"]))
    check(set(row["pins"])==set(evidence)==set(PINS))
    for name in PINS:
        data=evidence[name]
        check(type(data) is bytes and 0<len(data)<=(staged.JAR_BYTES if name=="jar" else 4194304)
              and row["pins"][name]==ctl.sha(data))
    projection=row["receiver"]
    rx.shape(projection,RECEIVER_KEYS)
    check(row["operation_id"]==projection["operation_id"] and projection["stage1_sha256"]==row["pins"]["result"]
          and projection["jar_sha256"]==row["pins"]["jar"] and projection["source_manifest_sha256"]==row["pins"]["source_manifest"]
          and all(ctl.hash_ok(v) for k,v in projection.items() if k.endswith("_sha256"))
          and type(projection["count"]) is int and 1<=projection["count"]<=64
          and type(projection["plaintext_cap"]) is int and 0<projection["plaintext_cap"]<=rx.writer.STREAM_CAP)
    start,end=map(staged.instant,(row["valid_from"],row["expires_at"]))
    check(start<=now<end)
    return row,(end-now).total_seconds()


@dataclass(frozen=True)
class PublicMaterial:
    """Only authenticated stage-1 and public runtime material. Never holds a receiver fd or private answer."""
    binding: bytes
    result: bytes
    closure: bytes
    jar: bytes
    image: object
    native_qualification: bytes
    runtime_policy: bytes
    route_qualification: bytes


def join(row, e, host):
    binding=staged.strict(e["binding"])
    result=ledger_row(e["result"])
    closure=ledger_row(e["closure"])
    original=admission.record(e["stage1_approval"])
    check(ctl.canonical(binding)==e["binding"] and binding["authority_sha256"]==ctl.sha(e["stage1_approval"])
          and original["schema"]=="staged-paid-run-approval/1" and original["operator"]=="Howard"
          and original["mode"]=="STAGED_PUBLIC" and original["graph_mode"]=="off"
          and result["mode"]==binding["mode"]=="STAGED_PUBLIC" and result["schema"]=="staged-public-result/1"
          and result["status"]=="PUBLIC_COMPLETE_HIDDEN_PENDING" and result["qualified"] is False
          and result["hidden_execution_authorized"] is False and result["binding_sha256"]==ctl.digest(binding)
          and result["public_answer_key_sha256"]==binding["public_answer_key_sha256"]==native.KEY_HASH)
    pre=binding["pre_run_commitment"]
    check(pre["commitment_sha256"]==row["receiver"]["completion_sha256"] and
          result["pre_run_commitment_sha256"]==binding["heldout_commitment_sha256"]==ctl.digest(pre)
          and staged.instant(pre["committed_at"])<staged.instant(original["approved_at"])<=staged.instant(row["valid_from"]))
    check(ledger_row(e["provider_closed"])==dict(schema="public-provider-closed/1",key_process_reaped=True,
                                                  further_sends_possible=False,memory_erasure_claimed=False)
          and closure==dict(schema="staged-model-closure/1",binding_sha256=ctl.digest(binding),
                            model_ports_closed=True,further_model_calls_allowed=False)
          and ctl.sha(e["closure"])==result["closure_record_sha256"])
    selected=result["selected"]
    check(type(selected["match"]) is int and selected["match"]==16 and type(selected["different"]) is int
          and selected["different"]==0 and selected["build_receipt_sha256"]==ctl.sha(e["build"])
          and selected["public_receipt_sha256"]==ctl.sha(e["public_eval"]))
    jar_hash=native.selected_jar(e["jar"],result["retained_jar"],selected,binding,result["closure_record_sha256"])
    check(result["hidden"]==dict(status="PENDING",reason="separate-human-verifier",selected_jar_sha256=jar_hash))
    build=staged.strict(e["build"])
    check(build["result"]["jar_sha256"]==jar_hash and build["result"]["artifact_sha256"]==selected["artifact_sha256"]
          and build["public_only"] is True and build["operation"]=="compile")
    image=native.reviewed_image(e["image_binding"],row["pins"]["image_binding"],e["image_manifest"],
                                e["image_config"],e["licences"])
    check((host.p["source_commit"],host.p["source_tree"])==(row["source_commit"],row["source_tree"])
          and h1.sha(h1.canonical(host.p))==row["host_profile_sha256"]==image.host_profile)
    admission.host_qualification(e["host_qualification"])
    check(staged.strict(e["host_qualification"])["profile_sha256"]==image.host_profile)
    observed=h1.strict(e["custody"])
    h1.custody(observed,row["operation_id"],image.host_profile,row["source_commit"],row["source_tree"])
    check(observed["public_host_qualification"]=="PASSED"
          and observed["qualification_receipt_sha256"]==row["pins"]["host_qualification"]
          and staged.instant(row["valid_from"])<=staged.instant(observed["observed_at_with_offset"])
          <=datetime.now(timezone.utc))
    q=staged.strict(e["native_qualification"])
    check(q["schema"]=="native-candidate-public-check/1" and q["host_profile_sha256"]==image.host_profile
          and q["runtime_binding_sha256"]==image.digest and q["answer_key_manifest_sha256"]==native.KEY_HASH
          and q["public_cases_matched"]==q["public_cases_with_parity"]==16 and q["adversarial_probes_passed"]==3
          and q["private_execution_authorized"] is False)
    return PublicMaterial(e["binding"],e["result"],e["closure"],e["jar"],image,e["native_qualification"],
                          e["runtime_policy"],e["route_qualification"])


def replay_key(binding):
    # The original paid-run authority is stable across changed stage-2 IDs, jar, result, and stage-2 approval.
    value=staged.strict(binding)["authority_sha256"]
    check(ctl.hash_ok(value))
    return ctl.digest(dict(schema="stage2-once-per-paid-authority/1",stage1_authority=value))


def replay_parent(host):
    import os
    import pwd
    root=h1.private_directory(Path(pwd.getpwuid(os.getuid()).pw_dir)/".lightyear-stage2-claims")
    host.filesystem(root)
    return root


def decision(value):
    check(type(value) is bool)
    return {"status":"PASS" if value else "FAIL"}


def run_once(raw, expected, evidence, host, age_binary, evaluator):
    """evaluator.preflight(material), then evaluator.compare(frames, material, end) -> exact bool."""
    try:
        return _run(raw,expected,dict(evidence),host,age_binary,custody.terminal_note,custody.terminal_removal,evaluator)
    except (Exception,KeyboardInterrupt):
        raise Refused("stage2-refused") from None


def _run(raw, expected, evidence, host, age_binary, announce, confirm, evaluator):
    base=time.monotonic()
    row,remaining=approve(raw,expected,evidence,datetime.now(timezone.utc))
    end=base+remaining
    def before():
        check(time.monotonic()<end and datetime.now(timezone.utc)<staged.instant(row["expires_at"]))
    h1.profile(host.p)
    h1.source_identity(host.commands,host.p)
    host.observe()
    material=join(row,evidence,host)
    check(evaluator.preflight(material) is True)
    before()
    root=h1.private_directory(host.p["private_root"])
    parent=replay_parent(host)
    projection=row["receiver"]
    store=None
    def claim():
        nonlocal store
        before()
        store=durable.DurablePorts(parent,replay_key(material.binding),end)
        with_set=ctl.digest(dict(schema="stage2-once-per-commitment/1",commitment=projection["completion_sha256"]))
        guard=durable.DurablePorts(parent,with_set,end)
        try:
            guard.record("consumed",{"stage1_authority":replay_key(material.binding)})
        finally:
            guard.close()
        info=dict(schema="stage2-private-claim/1",authority_sha256=expected,
                  result_sha256=projection["stage1_sha256"],commitment_sha256=projection["completion_sha256"],
                  jar_sha256=projection["jar_sha256"])
        digest=store.record("claim",info)
        check(digest==ctl.sha(ctl.canonical(info)+b"\n"))
        return digest
    broker=custody.CustodyBroker(root,"answers-"+row["h2_operation_id"],age_binary,
                                  row["usb_mount_id"],row["usb_device"],projection,row["pins"]["host_qualification"],claim,announce,confirm)
    try:
        handoff=rx.Receiver().receive(projection,rx.strict(evidence["source_manifest"],4194304),broker,end)
        before()
        def evaluate(frames, claim_hash, removal_hash):
            before()
            check(store is not None and broker.phase=="consumed" and claim_hash==broker.claim_digest
                  and ctl.hash_ok(removal_hash) and len(frames)==projection["count"])
            # Recheck the private daemon and USB absence after removal, before candidate code.
            host.observe()
            check(not custody.mounted(row["usb_device"],row["usb_mount_id"]))
            before()
            public=decision(evaluator.compare(frames,material,end))
            before()
            host.observe()
            check(not custody.mounted(row["usb_device"],row["usb_mount_id"]))
            receipt=dict(schema="stage2-private-terminal/1",claim_sha256=claim_hash,
                         removal_sha256=removal_hash,public_receipt_sha256=ctl.digest(public))
            check(store.record("terminal",receipt)==ctl.sha(ctl.canonical(receipt)+b"\n"))
            before()
            return public
        return handoff.consume(evaluate)
    finally:
        if store is not None:
            store.close()
