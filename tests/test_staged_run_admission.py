import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from lightyear_factory import staged_run_admission as a


def raw(row):
    return a.ctl.canonical(row)


def h(value):
    return a.ctl.sha(value.encode())


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat("2030-02-04T08:01:00+00:00")
        self.issued = "2030-02-04T08:00:00+00:00"
        earlier = "2030-02-04T07:55:00+00:00"
        self.end = "2030-02-04T08:05:00+00:00"
        self.ctx = {"public.cbl": "IDENTIFICATION DIVISION."}
        self.modules = {name: h(name) for name in a.SOURCES}
        self.modules[a.RELEASE_BINDING] = a.key.RELEASE_BINDING_SHA256
        self.modules[a.SUITE] = a.key.QUALIFICATION["public_suite_sha256"]
        self.source = dict(commit="c"*40, tree="d"*40, modules=self.modules)
        self.loc = dict(repository=a.REPOSITORY, release_id=1, asset_id=2, tag="synthetic")
        self.asset = raw(dict(schema="heldout-public-commitment/1", commitment_sha256=h("hidden")))
        self.pub = dict(self.loc, published_at=earlier, asset_created_at=earlier,
                        asset_updated_at=earlier, draft=False, public=True, asset_sha256=a.ctl.sha(self.asset))
        self.commitment = dict(schema="heldout-pre-run-commitment/1", committed_at=earlier,
                               commitment_sha256=h("hidden"), publication_receipt_sha256=a.ctl.digest(self.pub))
        profile = dict(cli_sha256=h("cli"), helper_sha256=self.modules[a.HELPER],
                       jdk_sha256=a.worker.JDK, jre_sha256=a.worker.JRE)
        self.binding = dict(schema="staged-public-binding/1", graph_mode="off", mode="STAGED_PUBLIC",
                            max_repairs=5, window_seconds=a.ctl.WINDOW, cap_microdollars=a.ctl.CEILING,
                            model=a.ctl.MODEL, service_tier="flex", output_cap=32000, retries=0,
                            implementation_sha256=a.ctl.digest(self.modules), public_context_sha256=a.ctl.digest(self.ctx),
                            public_suite_sha256=self.modules[a.SUITE], public_case_count=16,
                            heldout_commitment_sha256=a.ctl.digest(self.commitment),
                            role_instructions_sha256=a.ctl.ROLE_HASH, feedback_contract_sha256=a.ctl.FEEDBACK_HASH,
                            staged_policy_sha256=a.staged.POLICY_HASH, worker_source_sha256=self.modules[a.WORKER],
                            pre_run_commitment=self.commitment, approval_timestamp=self.issued,
                            public_answer_key_sha256=h("key-manifest"), build_profile=profile,
                            runtime_profile_sha256=a.ctl.digest(profile))
        self.host = dict(schema="ha-public-host-qualification/1", status="CRITERION_MET", operation_id=h("Q"),
                         source_commit="e"*40, source_tree="f"*40, profile_sha256=h("profile"),
                         custody_sha256=h("custody"), postflight_custody_sha256=h("post"), report_sha256=h("report"),
                         inventory_sha256=h("inventory"), comparison_criterion_met=True, cases=16, probes=9,
                         all_probes_match=False, cleanup=True, public_only=True, host_resources={},
                         local_image_id="sha256:"+h("image"), image_digest_bound=False,
                         private_use_authorized=False, limits=["synthetic"], package_library_sha256=a.PACKAGE,
                         public_suite_sha256=self.modules[a.SUITE],
                         qualification_source_commit=a.key.QUALIFICATION["qualification_commit"],
                         qualification_source_tree=a.key.QUALIFICATION["qualification_tree"],
                         reviewed_qualification_sha256=a.key.QUALIFICATION["qualification_sha256"])
        self.proofs = {}
        for name in a.PROOFS:
            subject = {"public_worker": self.binding["runtime_profile_sha256"],
                       "measured_bounds_and_deadlines": self.binding["public_context_sha256"]}.get(
                           name, self.binding["implementation_sha256"])
            attachment = name.encode()
            row = dict(schema="staged-prerequisite-observation/1", kind=name, passed=True,
                       observed_at=earlier, valid_until=self.end, source_commit=self.source["commit"],
                       source_tree=self.source["tree"], subject_sha256=subject, receipt_sha256=a.ctl.sha(attachment))
            self.proofs[name] = (raw(row), attachment)
        self.intent = dict(schema="graph-off-admission-intent/1", source_commit=self.source["commit"],
                           source_tree=self.source["tree"], modules_sha256=a.ctl.digest(self.modules),
                           binding_intent_sha256=a.ctl.digest(self.binding), host_qualification_sha256=a.ctl.sha(raw(self.host)),
                           key_release_sha256=a.key.RELEASE_BINDING_SHA256, publication=self.loc,
                           proofs={k:a.ctl.sha(v[0]) for k,v in self.proofs.items()},
                           rates=copy.deepcopy(a.RATES), holds_microdollars=dict(a.ctl.HOLDS))
        self.auth = dict(schema="staged-paid-run-approval/1", operator="Howard", operation_id=h("new-operation"),
                         intent_sha256=a.ctl.sha(raw(self.intent)), approved_at=self.issued, latest_start=self.end,
                         mode="STAGED_PUBLIC", model=a.ctl.MODEL, graph_mode="off", cap_microdollars=a.ctl.CEILING,
                         window_seconds=a.ctl.WINDOW, count_billing_assumption_accepted=True)
        self.binding["authority_sha256"] = a.ctl.sha(raw(self.auth))
        self.store = self.enterContext(patch.object(a,"DurablePorts"))
        self.store.return_value.record.side_effect = lambda name,row:a.ctl.sha(raw(row)+b"\n")
        self.key = self.enterContext(patch.object(a.key,"published_key"))
        self.key.return_value.manifest_sha256 = self.binding["public_answer_key_sha256"]
        self.checkout = self.enterContext(patch.object(a,"checkout",return_value=self.source))

    def port(self, **kwargs):
        args = dict(root="unused", authority_root="stable", expected_approval=self.binding["authority_sha256"],
                    approval=raw(self.auth), intent=raw(self.intent), context=self.ctx, key_binding=b"key", key_archive=b"zip",
                    host=raw(self.host), proofs=self.proofs, read_publication=lambda loc,end:(self.asset,self.pub),
                    wall=lambda:self.now, clock=lambda:10)
        return a.GraphOffAdmission(**dict(args,**kwargs))

    def refuse(self, port=None):
        with self.assertRaises(a.ctl.Refused):
            (port or self.port()).admit(raw(self.binding), 100)
        self.store.assert_not_called()

    def test_exact_port_shape_and_operation_key(self):
        port = self.port()
        result = port.admit(raw(self.binding),100)
        self.assertEqual(set(result), {"receipt_sha256","binding_sha256"})
        self.assertEqual(result["binding_sha256"], a.ctl.digest(self.binding))
        self.assertEqual(self.store.call_args.args[:2], ("stable",self.auth["operation_id"]))
        self.store.return_value.close.assert_called_once()
        with self.assertRaisesRegex(a.ctl.Refused,"used"):
            port.admit(raw(self.binding),100)

    def test_fresh_authority_only(self):
        self.refuse(self.port(expected_approval=h("earlier-run")))

    def test_expired_or_future_authority(self):
        for when in ("08:05","07:59"):
            with self.subTest(when=when):
                self.now = datetime.fromisoformat("2030-02-04T"+when+":00+00:00")
                self.refuse()

    def test_after_publication_before_claim(self):
        self.pub["asset_updated_at"] = self.issued
        self.refuse()

    def test_readback_must_join_exact_asset(self):
        self.pub["asset_id"] += 1
        self.refuse()

    def test_extra_or_private_commitment_fields(self):
        self.asset = raw(dict(json.loads(self.asset), cases=[]))
        self.refuse()

    def test_observation_attachment_altered(self):
        e,_ = self.proofs["mac_tls_1"]
        self.proofs["mac_tls_1"] = (e,b"changed")
        self.refuse()

    def test_missing_disk_receipt(self):
        del self.proofs["disk_headroom"]
        self.refuse()

    def test_host_and_source_mismatch(self):
        self.host["comparison_criterion_met"] = False
        self.refuse()
        self.host["comparison_criterion_met"] = True
        self.source["tree"] = "a"*40
        self.refuse()

    def test_wrong_public_suite_and_graph_mode(self):
        for k,v in (("public_suite_sha256",h("other")),("graph_mode","on"),("window_seconds",26880)):
            with self.subTest(key=k), patch.dict(self.binding,{k:v}):
                self.refuse()

    def test_byte_exact_authority_and_duplicate_keys(self):
        self.refuse(self.port(approval=b" "+raw(self.auth)))
        self.refuse(self.port(approval=b'{"schema":1,"schema":2}'))

    def test_key_refusal_precedes_claim(self):
        self.key.side_effect = ValueError()
        self.refuse()

    def test_deadline_expires_during_read(self):
        self.refuse(self.port(clock=iter([10,100]).__next__))

    def test_exclusive_claim_refusal_is_terminal(self):
        self.store.side_effect = OSError()
        port = self.port()
        with self.assertRaisesRegex(a.ctl.Refused,"admission-refused"):
            port.admit(raw(self.binding),100)
        with self.assertRaisesRegex(a.ctl.Refused,"used"):
            port.admit(raw(self.binding),100)

    def test_durable_readback_mismatch(self):
        self.store.return_value.record.side_effect = None
        self.store.return_value.record.return_value = h("different")
        with self.assertRaisesRegex(a.ctl.Refused,"admission-receipt"):
            self.port().admit(raw(self.binding),100)
        self.store.return_value.close.assert_called_once()

    def test_changed_pricing_even_with_new_digest(self):
        self.intent["rates"]["count_input"] = 0
        self.auth["intent_sha256"] = a.ctl.sha(raw(self.intent))
        self.binding["authority_sha256"] = a.ctl.sha(raw(self.auth))
        self.refuse()

    def test_receipt_time_offset_required(self):
        self.pub["published_at"] = "2030-02-04T06:00:00"
        self.refuse()

    def test_all_facts_have_finite_expiry(self):
        row = json.loads(self.proofs["ledger_volume"][0])
        row["valid_until"] = self.now.astimezone(timezone.utc).isoformat()
        self.proofs["ledger_volume"] = (raw(row),b"ledger_volume")
        self.intent["proofs"]["ledger_volume"] = a.ctl.sha(raw(row))
        self.auth["intent_sha256"] = a.ctl.sha(raw(self.intent))
        self.binding["authority_sha256"] = a.ctl.sha(raw(self.auth))
        self.refuse()


class CheckoutTests(unittest.TestCase):
    def test_actual_blob_comparison_and_dirty_refusal(self):
        with TemporaryDirectory() as folder, patch.object(a,"SOURCES",("bound.txt",)):
            root=Path(folder).resolve()
            def git(*args):
                subprocess.run(["git","-C",str(root),*args],check=True,capture_output=True)
            git("init")
            git("config","core.autocrlf","false")
            (root/"bound.txt").write_bytes(b"reviewed\n")
            git("add","bound.txt")
            git("-c","user.name=Synthetic","-c","user.email=ci@example.invalid",
                "-c","commit.gpgsign=false","commit","-m","synthetic")
            self.assertEqual(a.checkout(root)["modules"]["bound.txt"], h("reviewed\n"))
            (root/"bound.txt").write_bytes(b"changed")
            with self.assertRaisesRegex(a.ctl.Refused,"admission-checkout"):
                a.checkout(root)
