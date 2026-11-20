"""Preparation uses synthetic public evidence. No network, model, generator or Docker."""
from argparse import Namespace
from datetime import datetime, timedelta, timezone
import io
from contextlib import redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import prepare_staged_public as prep


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2030,1,1,tzinfo=timezone.utc)
        self.location = dict(repository=prep.admission.REPOSITORY, release_id=1, asset_id=2, tag="test")
        self.request = dict(schema="staged-preparation-request/1", operation_id="1"*64,
                            approved_at=self.now.isoformat(), latest_start=(self.now+timedelta(minutes=5)).isoformat(),
                            publication=self.location)
        self.docs = {"PROPOSED-APPROVAL.json":b"approval","BINDING.json":b"binding","INTENT.json":b"intent"}

    def test_draft_can_precede_start_but_preflight_cannot(self):
        early = self.now - timedelta(seconds=1)
        self.assertEqual(prep.timing(self.request, early, False), self.now)
        with self.assertRaisesRegex(ValueError,"window"):
            prep.timing(self.request, early, True)

    def test_expired_and_oversize_windows_refuse(self):
        with self.assertRaisesRegex(ValueError,"window"):
            prep.timing(self.request,self.now+timedelta(minutes=5),False)
        self.request["latest_start"] = (self.now+timedelta(seconds=prep.ctl.WINDOW+1)).isoformat()
        with self.assertRaisesRegex(ValueError,"window"):
            prep.timing(self.request,self.now,True)

    def test_request_rejects_endpoint_override(self):
        self.request["publication"]["url"] = "unreviewed"
        with self.assertRaises(ValueError):
            prep.timing(self.request,self.now,False)

    def test_worker_join_binds_both_raw_inputs(self):
        row = prep.worker_join(b"config", b"proof")
        self.assertNotEqual(row, prep.worker_join(b"config\n",b"proof"))
        self.assertNotEqual(row, prep.worker_join(b"config",b"proof\n"))

    def test_commitment_uses_latest_asset_event(self):
        asset = prep.ctl.canonical(dict(schema="heldout-public-commitment/1",commitment_sha256="a"*64))
        seen = (self.now-timedelta(seconds=1)).isoformat()
        earlier = (self.now-timedelta(days=1)).isoformat()
        observation = dict(self.location, published_at=earlier,asset_created_at=earlier,asset_updated_at=seen,
                           asset_sha256=prep.ctl.sha(asset),public=True,draft=False)
        row = prep.commitment(self.request,self.now,asset,observation)
        self.assertEqual(row["committed_at"], seen)
        observation["asset_updated_at"] = self.now.isoformat()
        with self.assertRaises(ValueError):
            prep.commitment(self.request,self.now,asset,observation)

    def test_three_way_approval_byte_check(self):
        raw=b"Howard-approved bytes"
        prep.check_approval(raw,raw,prep.ctl.sha(raw))
        for changed, independent in ((raw+b"\n",prep.ctl.sha(raw)), (raw,"0"*64),
                                     (raw+b"\n",prep.ctl.sha(raw+b"\n"))):
            with self.subTest(independent=independent), self.assertRaisesRegex(ValueError,"approval"):
                prep.check_approval(raw,changed,independent)

    def test_prepare_join_feeds_real_admission_validation(self):
        import test_staged_run_admission as fixtures
        fixture = fixtures.AdmissionTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        raw = prep.ctl.canonical
        config, qual = b"local config", b"public worker proof"
        request = dict(self.request, publication=fixture.loc,approved_at=fixture.issued,
                       latest_start=fixture.end, operation_id=fixture.auth["operation_id"])
        ctx=raw(fixture.ctx)
        data={"REQUEST.json":raw(request),"CURRENT-CONTEXT.json":ctx,"HOST.json":raw(fixture.host),
              "LOCAL-WORKER.json":config,"WORKER-QUALIFICATION.receipt":qual}
        for k,(proof,attachment) in fixture.proofs.items():
            if k == "public_worker":
                attachment=raw(prep.worker_join(config,qual))
                proof=raw(dict(prep.admission.record(proof),receipt_sha256=prep.ctl.sha(attachment)))
            data[k+".json"],data[k+".receipt"]=proof,attachment
        reviewed=Mock(manifest_sha256=fixture.binding["public_answer_key_sha256"])
        with patch.object(prep,"CONTEXT",prep.ctl.sha(ctx)):
            docs=prep.documents(data,fixture.source,reviewed,fixture.binding["build_profile"],fixture.commitment,fixture.now)
        intent,binding,approval=(prep.staged.strict(docs[k]) for k in ("INTENT.json","BINDING.json","PROPOSED-APPROVAL.json"))
        self.assertEqual(approval["intent_sha256"],prep.ctl.digest(intent))
        self.assertEqual(binding["authority_sha256"],prep.ctl.digest(approval))
        self.assertEqual(intent["binding_intent_sha256"],prep.ctl.digest({k:v for k,v in binding.items() if k!="authority_sha256"}))
        self.assertEqual(prep.ctl.canonical(approval),docs["PROPOSED-APPROVAL.json"])

    def test_exclusive_output_does_not_replace_existing_directory(self):
        with tempfile.TemporaryDirectory() as root, patch.object(prep,"owner_directory"):
            target=Path(root)/"stage"
            prep.exclusive_files(target,{"example":b"first"})
            with self.assertRaises(FileExistsError):
                prep.exclusive_files(target,{"example":b"second"})
            self.assertEqual((target/"example").read_bytes(),b"first")

    def setup_mode(self, mode):
        self.enterContext(patch.object(prep.sys,"platform","darwin"))
        self.enterContext(patch.object(prep.platform,"machine",return_value="arm64"))
        self.enterContext(patch.object(prep,"inputs",return_value={"answer-key.zip":b"zip"}))
        self.enterContext(patch.object(prep,"review",return_value=(self.docs,Mock())))
        return Namespace(mode=mode,directory=Path("input"),output=Path("output"),
                         approval=Path("approved"),approval_sha256=prep.ctl.sha(b"approval"))

    def test_draft_outputs_only_review_documents(self):
        args=self.setup_mode("draft")
        with patch.object(prep,"exclusive_files") as write:
            self.assertEqual(prep.execute(args)["status"],"PROPOSED")
        self.assertNotIn("APPROVAL.json",write.call_args.args[1])

    def test_seal_declines_changed_approval_before_writing(self):
        args=self.setup_mode("seal")
        with patch.object(prep.staged,"read_owned",return_value=b"changed"), patch.object(prep,"exclusive_files") as write:
            with self.assertRaisesRegex(ValueError,"approval"):
                prep.execute(args)
            write.assert_not_called()

    def test_preflight_performs_no_write_or_claim(self):
        args=self.setup_mode("preflight")
        def read(path, cap):
            return {"INTENT.json":b"intent","BINDING.json":b"binding","APPROVAL.json":b"approval"}[path.name]
        with patch.object(prep.staged,"read_owned",side_effect=read), patch.object(prep.key,"load"), \
             patch.object(prep.admission,"record",return_value={"operation_id":"1"*64}), \
             patch.object(prep,"inspect_placement") as inspect, patch.object(prep,"exclusive_files") as write, \
             patch.object(prep.archive,"unpack") as unpack:
            self.assertEqual(prep.execute(args)["status"],"PREFLIGHT_READY")
            self.assertEqual(prep.execute(args)["status"],"PREFLIGHT_READY")
        self.assertEqual(inspect.call_count,2)
        write.assert_not_called()
        unpack.assert_not_called()

    def test_refusal_does_not_print_exception_text(self):
        sink=io.StringIO()
        with patch.object(prep,"execute",side_effect=ValueError("do not print")),redirect_stderr(sink):
            self.assertEqual(prep.main(["worker-join","--directory","example"]),2)
        self.assertEqual(sink.getvalue(),"staged-preparation-refused\n")
