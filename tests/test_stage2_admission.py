"""Synthetic contract tests. No private data, mounted device, decryption or candidate."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import intcalc_h3_custody as broker
from tools import intcalc_h3_usb_channel as bridge
from tools import intcalc_stage2_admission as b


def approval(now):
    evidence={name:name.encode() for name in b.PINS}
    pins={k:b.ctl.sha(v) for k,v in evidence.items()}
    projection={k:"a"*64 for k in b.RECEIVER_KEYS.split()}
    projection.update(stage1_sha256=pins["result"],jar_sha256=pins["jar"],source_manifest_sha256=pins["source_manifest"],
                      count=1,plaintext_cap=4096)
    row=dict(schema="private-stage2-approval/1",operator="Howard",mode="EXACT_SELECTED_JAR_ONCE",
             operation_id=projection["operation_id"],valid_from=(now-timedelta(seconds=2)).isoformat(),
             expires_at=(now+timedelta(minutes=5)).isoformat(),source_commit="f"*40,source_tree="e"*40,
             host_profile_sha256="b"*64,h2_operation_id="c"*64,receiver=projection,pins=pins,
             usb_mount_id=23,usb_device="8:17")
    return row,evidence


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.row,self.evidence=approval(self.now)

    def admit(self):
        raw=b.rx.writer.canonical(self.row)
        return b.approve(raw,b.ctl.sha(raw),self.evidence,self.now)

    def test_authority_exact_bytes_and_digest(self):
        row,seconds=self.admit()
        self.assertEqual(row,self.row)
        self.assertGreater(seconds,0)
        with self.assertRaises(ValueError):
            b.approve(b"altered","0"*64,self.evidence,self.now)

    def test_every_evidence_pin_is_enforced(self):
        for k,v in list(self.evidence.items()):
            with self.subTest(k=k),self.assertRaises(ValueError):
                self.evidence[k]=v+b"x"
                self.admit()
            self.evidence[k]=v

    def test_deadline_equality_refuses(self):
        self.row["expires_at"]=self.now.isoformat()
        with self.assertRaises(ValueError):
            self.admit()

    def test_changed_projection_cannot_change_retained_jar(self):
        self.row["receiver"]["jar_sha256"]="0"*64
        with self.assertRaises(ValueError):
            self.admit()

    def test_unknown_authority_fields_refuse(self):
        self.row["resume"]=True
        with self.assertRaises(ValueError):
            self.admit()

    def test_zero_case_or_boolean_count_refuses(self):
        for v in (0,65,True):
            self.row["receiver"]["count"]=v
            with self.assertRaises(ValueError):
                self.admit()

    def test_replay_key_is_independent_of_candidate_and_new_request(self):
        def key(other):
            return b.replay_key(b.ctl.canonical(dict(authority_sha256="a"*64,other=other)))
        self.assertEqual(key("first"),key("second"))

    def test_result_is_closed_and_boolean_only(self):
        self.assertEqual(b.decision(False),{"status":"FAIL"})
        self.assertEqual(b.decision(True),{"status":"PASS"})
        for v in (0,1,None,{"status":"PASS"}):
            with self.assertRaises(ValueError):
                b.decision(v)

    def test_public_entry_redacts_exception_and_has_no_case_receipt(self):
        with patch.object(b,"_run",side_effect=OSError("PRIVATE CANARY")):
            with self.assertRaisesRegex(b.Refused,"^stage2-refused$"):
                b.run_once(b"", "", {}, None, None, None)

    def test_exact_b2_interface_order_and_durable_claims(self):
        event=[]
        def mark(name,ret=None):
            def fn(*args,**kwargs):
                event.append(name)
                return ret
            return fn
        host=Mock()
        host.p={"private_root":"/private"}
        material=SimpleNamespace(binding=b.ctl.canonical({"authority_sha256":"a"*64}))
        h=b.ctl.sha(b"receipt")
        row=self.row
        raw=b.rx.writer.canonical(row)
        stores=[]
        def storage(*args,**kwargs):
            store=Mock()
            store.record.side_effect=lambda name,fields:(event.append(name) or b.ctl.sha(b.ctl.canonical(fields)+b"\n"))
            stores.append(store)
            return store
        class Receiver:
            def receive(self,projection,manifest,port,end):
                assert port.root == Path("/private") / ("answers-" + row["h2_operation_id"])
                assert port.vault == "encrypted"
                claim=port.claim(projection,end)
                event.append("private-read")
                port.phase="consumed"
                return b.rx.PrivateHandoff([b"synthetic"],claim,h)
        class Eval:
            def preflight(self,m):
                self.material=m
                return mark("preflight",True)()
            def compare(self,frames,m,end):
                assert m is self.material and frames==[b"synthetic"]
                return mark("compare",True)()
        self.evidence["source_manifest"]=b"{}"
        replacements=((b,"approve",(row,300)),(b,"join",material),(b,"replay_parent",Path("/claims")),
                      (b.h1,"profile",None),(b.h1,"source_identity",None),(b.h1,"private_directory",Path("/private")),
                      (b.custody,"mounted",False))
        for obj,name,value in replacements:
            self.enterContext(patch.object(obj,name,return_value=value))
        self.enterContext(patch.object(b.rx,"Receiver",Receiver))
        self.enterContext(patch.object(b.durable,"DurablePorts",side_effect=storage))
        out=b.run_once(raw,b.ctl.sha(raw),self.evidence,host,None,Eval())
        self.assertEqual(out,{"status":"PASS"})
        self.assertEqual(event,["preflight","consumed","claim","private-read","compare","terminal"])
        self.assertTrue(all(s.close.called for s in stores))

    def test_malformed_material_stops_before_claim(self):
        with self.assertRaises(b.Refused),patch.object(b.durable,"DurablePorts",side_effect=AssertionError):
            b.run_once(b"{}","0"*64,{},None,None,None)


class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.proj={"operation_id":"f"*64}
        self.port=broker.CustodyBroker(Path("/private")/("answers-"+"c"*64),"encrypted",None,5,"8:17",
                    self.proj,"e"*64,lambda:"a"*64,Mock(),Mock(return_value=True))

    def test_claim_is_consumed_even_when_storage_fails(self):
        self.port.storage=Mock(side_effect=OSError())
        with self.assertRaises(OSError):
            self.port.claim(self.proj,float("inf"))
        with self.assertRaises(ValueError):
            self.port.claim(self.proj,float("inf"))

    def test_no_private_read_without_live_claim(self):
        with self.assertRaises(ValueError):
            self.port.read_completion("0"*64,float("inf"))

    def test_physical_confirmation_and_mount_absence_both_required(self):
        for confirm,present in ((False,False),(True,True),(True,False)):
            self.port.phase="closed"
            self.port.claim_digest="a"*64
            self.port.confirm.return_value=confirm
            with patch.object(broker,"mounted",return_value=present):
                if confirm and not present:
                    receipt=self.port.removal_receipt("a"*64,float("inf"))
                    self.assertEqual(receipt["operation_id"],self.proj["operation_id"])
                    self.assertTrue(receipt["handles_closed"])
                else:
                    with self.assertRaises(ValueError):
                        self.port.removal_receipt("a"*64,float("inf"))

    def test_usb_address_contains_only_claim_and_child_identity(self):
        x=bridge.address("a"*64,123)
        self.assertTrue(x.startswith("\0") and "/" not in x)
        with self.assertRaises(ValueError):
            bridge.address("unreviewed",123)

    def test_handoff_consumed_even_when_evaluator_refuses(self):
        rows=[b"PRIVATE CANARY"]
        handoff=b.rx.PrivateHandoff(rows,"a"*64,"b"*64)
        with self.assertRaises(OSError):
            handoff.consume(Mock(side_effect=OSError()))
        self.assertEqual(rows,[])
        with self.assertRaises(ValueError):
            handoff.consume(Mock())
