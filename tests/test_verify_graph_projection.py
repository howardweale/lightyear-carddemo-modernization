"""Projection, decision and receipt regressions for PR A."""
from tests.verify_graph_support import *


class ProjectionTests(GraphFixture):
    def test_confidential_source_and_redaction(self):
        self.build(mode="confidential",watch={"2022071800"})
        payload=read(self.out/"projection.json.gz")
        for n in payload["nodes"]:
            self.assertNotIn("statement",n["properties"])
            for s in n["source"]:
                if "text" in s:
                    self.assertEqual(s["path"],"app/cbl/CBACT04C.cbl")
                    self.assertNotIn("2022071800",s["text"])
                    self.assertLessEqual(len(s["text"].splitlines()),120)


    def test_leak_hashes_only_and_source_literal_requires_explicit_approval(self):
        m=self.build()
        # Plant a long token only in approved-projection test bytes.
        p=read(self.out/"projection.json.gz")
        p["nodes"][0]["properties"]["statement"]="PRIVATE-CANARY-983741"
        (self.out/"projection.json.gz").write_bytes(gzip.compress(canonical(p),mtime=0))
        report=leak_check(self.out,digest(self.lane),{"PRIVATE-CANARY-983741"},self.signer,evaluation_inventory_sha256=digest({}),
                          approved_source="MOVE 'PRIVATE-CANARY-983741' TO X")
        self.assertFalse(report["passed"])
        self.assertEqual(report["matches"][0]["classification"],"source-literal")
        self.assertNotIn("PRIVATE-CANARY-983741",json.dumps(report))
        self.assertEqual(sha(b"PRIVATE-CANARY-983741"),report["matches"][0]["value_sha256"])


    def test_real_tower_gate_and_tampering(self):
        m=self.build()
        leak_check(self.out,digest(self.lane),set(),self.signer,evaluation_inventory_sha256=digest({}))
        proof,trust=self.approve(m)
        load_approved(self.out,proof,trust)
        for change in (dict(lane_sha256="f"*64),dict(mode="confidential"),
                       dict(trusted_head="f"*64),dict(customer_id="other")):
            with self.subTest(change=change),self.assertRaises(ValueError):
                load_approved(self.out,proof,{**trust,**change})
        with self.assertRaises(ValueError):
            load_approved(self.out,proof,trust,now=datetime.now(timezone.utc)+timedelta(days=11))
        (self.out/"projection.json.gz").write_bytes(b"tampered")
        with self.assertRaises(ValueError): load_approved(self.out,proof,trust)


    def test_rejected_decision(self):
        m=self.build(); leak_check(self.out,digest(self.lane),set(),self.signer,evaluation_inventory_sha256=digest({}))
        proof,trust=self.approve(m,outcome="rejected")
        with self.assertRaises(ValueError): load_approved(self.out,proof,trust)


    def test_receipts_new_required_old_implied_null(self):
        self.assertIsNone(receipt_context({"schema":"lightyear-verify-receipt/1"},{}))
        self.assertEqual("a"*64,receipt_context({"schema":"lightyear-verify-receipt/2",
            "context_projection_sha256":"a"*64},{"context_projection_sha256":"a"*64}))
        for r in ({"schema":"lightyear-verify-receipt/2"},
                  {"schema":"lightyear-verify-receipt/2","context_projection_sha256":"b"*64},
                  {"schema":"lightyear-verify-receipt/1"}):
            with self.assertRaises(ValueError): receipt_context(r,{"context_projection_sha256":"a"*64})


    def test_signed_public_receipt_versions_and_evaluation_binding(self):
        from lightyear_control_tower.decisions import verify_envelope
        from lightyear_judge.service import public_body, initialize
        body={k:None for k in ("task_sha256","attempt_id","attempt_number","submission_limit",
             "artifact_sha256","verdict","diagnostics","status","budget","review","disclosure_mode")}
        for version in (1,2):
            receipt={**body,"schema":f"lightyear-verify-receipt/{version}"}
            if version==2: receipt["context_projection_sha256"]="a"*64
            public=self.signer.sign(public_body(receipt))
            self.assertTrue(verify_envelope(public,self.signer.public))
            self.assertEqual("context_projection_sha256" in public,version==2)
            receipt_context(public,{"context_projection_sha256":"a"*64} if version==2 else {})
        m=self.build()
        leak_check(self.out,digest(self.lane),set(),self.signer,evaluation_inventory_sha256="f"*64)
        proof,trust=self.approve(m)
        decision=self.root/"proof.json"; decision.write_bytes(canonical(proof))
        evaluation=self.root/"evaluation"; evaluation.mkdir()
        config=dict(context_projection_sha256=m["projection_sha256"],fixture=True,disclosure_mode="field",
                    evaluation=str(evaluation),graph_context=dict(directory=str(self.out),decision=str(decision),trust=trust))
        with self.assertRaisesRegex(ValueError,"context-evaluation-mismatch"):
            initialize(self.root/"task",config)


    def test_deny_kinds_properties_and_transitive_provenance(self):
        graph=read(ROOT/"knowledge/graph.snapshot.json.gz")
        proto=next(n for n in graph["nodes"] if n["kind"]=="cobol_field" and n["name"]=="ACCT-CURR-BAL")
        nodes=[{**copy.deepcopy(proto),"id":"good"}]
        nodes[0]["properties"]["unexpected_value"]="SHOULD-DROP"
        for i,kind in enumerate(("execution","trace","observed_output","verification_scenario","test_case","unknown")):
            nodes.append({**copy.deepcopy(proto),"id":"kind"+str(i),"kind":kind})
        for i,props in enumerate(({"visibility":"inspector_private"},{"provenance":{"origin":"runtime-capture"}},
                {"customer_id":"maintec-private"},{"provenance_dependencies":["kind0"]},
                {"inspector_private":True},{"audience":"inspector_private"})):
            nodes.append({**copy.deepcopy(proto),"id":"bad"+str(i),"properties":props})
        nodes.append({**copy.deepcopy(proto),"id":"derived"})
        nodes.append({**copy.deepcopy(proto),"id":"runtime-rule","kind":"business_rule",
                      "properties":{"provenance":{"origin":"reference_data"},"confidence":"observed"}})
        g=self.root/"graph.json"; e=self.root/"evidence.json"
        g.write_bytes(canonical({"nodes":nodes,"edges":[{"id":"cause","source":"derived","target":"bad1","relation":"DERIVED_FROM"}]}))
        e.write_bytes(canonical({"capsules":[]}))
        build(g,e,self.policy,"INTCALC","field","carddemo-reference",self.out,self.signer,source_root=ROOT)
        p=read(self.out/"projection.json.gz")
        self.assertEqual(["good"],[n["id"] for n in p["nodes"]])
        self.assertNotIn("SHOULD-DROP",json.dumps(p))


    def test_source_literal_exception_requires_exact_signed_reason(self):
        m=self.build()
        # Public source contains the quoted error text; choose it as a synthetic watch value.
        literal="ACCOUNT-FILE"
        leak_check(self.out,digest(self.lane),{literal},self.signer,evaluation_inventory_sha256=digest({}),approved_source="'ACCOUNT-FILE'")
        proof,trust=self.approve(m)
        with self.assertRaises(ValueError): load_approved(self.out,proof,trust)
        proof,trust=self.approve(m,reason="Reviewed source-literal:"+sha(literal.encode()))
        # Only a source-literal report can be accepted, and all exact hashes are acknowledged.
        load_approved(self.out,proof,trust)
        (self.out/"leak-check.json").unlink()
        load_approved(self.out,proof,trust)  # detailed judge report is not an agent-side dependency


    def test_private_watch_list_decodes_real_fixture_without_printing_values(self):
        from lightyear_judge.graph_projection import watch_values
        from lightyear_mainframe.records import load_copybook
        source=ROOT/"tests/mainframe/fixtures/arrival-rehearsal/INTCALC-run1-2026-10-05"
        evaluation=self.root/"evaluation"
        shutil.copytree(source,evaluation/"run")
        layout=load_copybook(ROOT/"spec/mainframe/copybooks/CVACT01Y.cpy")
        f=next(f for f in layout.fields if f.path.endswith("ACCT-ADDR-ZIP"))
        target=evaluation/"run/before/ACCTFILE.bin"
        data=bytearray(target.read_bytes())
        token="ZXQ837291"
        data[f.offset:f.offset+f.length]=token.ljust(f.length).encode("cp037")
        target.write_bytes(data)
        values=watch_values(evaluation,"INTCALC")
        with self.assertRaisesRegex(ValueError,"graph-evaluation-lane"):
            watch_values(evaluation,"OTHER")
        self.assertIn(token,values)
        m=self.build()
        report=leak_check(self.out,digest(self.lane),values,self.signer,evaluation_inventory_sha256=digest({}))
        self.assertNotIn(token,json.dumps(report))
        certificate=read(self.out/"graph-leak-certificate.json")
        self.assertNotIn("watch_list_size",certificate)
        self.assertNotIn("matches",certificate)


    def test_deterministic_and_watch_independent(self):
        self.build(mode="confidential",watch={"FIRST-PRIVATE-TOKEN"})
        self.build(mode="confidential",watch={"OTHER-PRIVATE-TOKEN"},out=self.root/"other")
        for name in ("projection.json.gz","projection-manifest.json"):
            self.assertEqual((self.out/name).read_bytes(),(self.root/"other"/name).read_bytes())
