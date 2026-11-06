"""CI-only graph-on variant of the existing two-user Linux acceptance flow."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

from tests.test_verify_mcp import VerifyAcceptance
from tests.verify_graph_support import GraphFixture
from lightyear_control_tower.decisions import canonical, digest
from lightyear_factory.contracts import ContractError
from lightyear_judge.graph_projection import read, leak_check
from lightyear_judge.service import inventory
from lightyear_toolkit.graph_inventory import scan_inventory
from lightyear_toolkit.graph_approval import load_approved

GRAPH_TOOLS = {"graph_search", "graph_node", "graph_neighbors", "graph_references",
               "graph_guidance", "explain_divergence"}

class GraphOnAcceptance(VerifyAcceptance):
    def graph_config(self):
        fixture = GraphFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        manifest = fixture.build()
        projection = read(fixture.out / "projection.json.gz")
        self.scan_canaries = {k: k + "-" + uuid.uuid4().hex for k in
                              ("expected-state", "reference-output", "session-answer")}
        self.inventory_report = scan_inventory(
            projection, canaries=self.scan_canaries, protected_values=self.protected_values,
            projection_sha256=manifest["projection_sha256"])
        # A planted source excerpt must fail the exact full inventory scanner.
        poisoned = json.loads(json.dumps(projection))
        poisoned["nodes"][0].setdefault("source", []).append(
            {"text": base64.b64encode((self.canary * 4).encode()).decode()})
        with self.assertRaisesRegex(ContractError, "isolation-breach"):
            scan_inventory(poisoned, canaries=self.scan_canaries,
                           protected_values=self.protected_values,
                           projection_sha256=manifest["projection_sha256"])
        report = leak_check(fixture.out, digest(fixture.lane), self.protected_values,
                            fixture.signer, evaluation_inventory_sha256=digest(inventory(self.eval)))
        self.assertTrue(report["passed"])
        proof, trust = fixture.approve(manifest, reason="Synthetic CI fixture only; no operator activation")
        load_approved(fixture.out, proof, trust)
        self.graph_dir = self.public / "context"
        self.graph_dir.mkdir()
        for name in ("projection.json.gz", "projection-manifest.json", "graph-leak-certificate.json"):
            shutil.copyfile(fixture.out / name, self.graph_dir / name)
        self.graph_proof = self.public / "context-proof.json"
        self.graph_proof.write_bytes(canonical(proof))
        public = json.loads(self.manifest.read_bytes())
        public["graph_trust"] = trust
        self.manifest.write_bytes(canonical(public))
        self.projection_hash = manifest["projection_sha256"]
        self.proof_hash = hashlib.sha256(self.graph_proof.read_bytes()).hexdigest()
        self.inventory_report["evaluation_inventory_sha256"] = digest(inventory(self.eval))
        self.inventory_report["authority"] = "ephemeral-CI-fixture"
        # Only the informational query log is agent-writable; public inputs stay read-only.
        query_log = self.public / "graph-queries.jsonl"
        query_log.touch(mode=0o600)
        os.chown(query_log, self.agent, self.agent)
        self.graph_calls = set()
        return {"context_projection_sha256": self.projection_hash, "disclosure_mode": "field",
                "graph_context": {"directory": str(self.graph_dir),
                                  "decision": str(self.graph_proof), "trust": trust}}

    def mcp_graph_args(self):
        return ["--graph-projection", str(self.graph_dir), "--graph-decision", str(self.graph_proof)]

    def extra_tool_names(self):
        return GRAPH_TOOLS

    async def exercise_graph(self, call):
        before = await call("get_budget")
        search = await call("graph_search", query="ACCT-CURR-BAL", kind="cobol_field")
        self.assertNotIn("error", search, search)
        self.assertTrue(search["items"])
        node = search["items"][0]["id"]
        for name, args in (
            ("graph_node", {"node_id": node, "include_source": True}),
            ("graph_neighbors", {"node_id": node}),
            ("graph_references", {"node_id": node}),
            ("graph_guidance", {"node_id": node}),
            ("explain_divergence", {"attempt_id": "unknown"}),
        ):
            result = await call(name, **args)
            self.assertNotIn(self.canary, json.dumps(result))
            if name != "explain_divergence":
                self.assertNotIn("error", result)
            self.graph_calls.add(name)
        self.graph_calls.add("graph_search")
        for name in ("graph_node", "graph_neighbors", "graph_references", "graph_guidance"):
            for forbidden in (str(self.eval), str(self.root / "receipts"), "../operator/session/token",
                              "expected-state", "reference-output", "session-answer"):
                result = await call(name, node_id=forbidden)
                self.assertNotIn(self.canary, json.dumps(result))
                self.assertFalse(result.get("items"))
        self.assertEqual(before, await call("get_budget"))

    async def exercise_public_decode(self, call):
        # Request every public record through the existing graph-on pagination API.
        # Each complete page is retained by call() and receives the full leak scan.
        raw = (self.public / "accounts.bin").read_bytes()
        self.assertEqual(0, len(raw) % 300)
        total = len(raw) // 300
        self.assertGreater(total, 0)
        source_hash = hashlib.sha256(raw).hexdigest()
        received = 0
        for offset in range(0, total, 5):
            page = await call("decode_records", path="accounts.bin", copybook="account.cpy",
                              offset=offset, limit=5)
            self.assertNotIn("error", page)
            self.assertEqual(source_hash, page["sha256"])
            self.assertEqual(total, page["total_records"])
            self.assertEqual(offset, page["offset"])
            self.assertEqual(5, page["limit"])
            self.assertEqual(min(5, total - offset), len(page["records"]))
            received += len(page["records"])
            self.assertEqual(received if received < total else None, page["next_offset"])
        self.assertEqual(total, received)

    async def inspect_graph_verdict(self, call, attempt):
        result = await call("explain_divergence", attempt_id=attempt)
        self.assertNotIn("error", result)
        self.assertNotIn(self.canary, json.dumps(result))

    def finish_graph_acceptance(self):
        self.assertEqual(GRAPH_TOOLS, self.graph_calls)
        # Scan every complete response, including candidate verdicts/receipts.
        # The scanner bounds apply to each response, not the accumulated session.
        # Normal acceptance additionally checks every short protected watch value.
        from lightyear_factory.isolation_scan import scan
        artifacts = [("mcp-response-" + str(i), canonical(response))
                     for i, response in enumerate(self.responses)]
        self.assertTrue(artifacts)
        # Identify bounded scan failures without exporting response contents.
        for name, data in artifacts:
            try:
                scan([(name, data)], self.scan_canaries, self.protected_values)
            except ContractError:
                print("GRAPH_RESPONSE_SCAN_FAILED " + json.dumps({
                    "artifact": name, "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }), flush=True)
                raise
        # A leak after all real responses must still be detected, with no truncation.
        leak = base64.b64encode(self.scan_canaries["session-answer"].encode()).decode()
        with self.assertRaisesRegex(ContractError, "isolation-breach"):
            scan(artifacts + [("late-encoded-leak", canonical({"text": leak}))],
                 self.scan_canaries, self.protected_values)
        response_scan = scan(artifacts, self.scan_canaries, self.protected_values)
        self.assertEqual(len(self.responses), len(response_scan["scanned"]))
        folder = Path(os.environ["VERIFY_GRAPH_REPORT_DIR"])
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        scan_name = "graph-inventory-scan-" + stamp + ".json"
        scan_raw = canonical(self.inventory_report)
        # Public CI output is an explicitly non-authorizing synthetic record.
        # The nested proof tests human-role policy using a simulated identity;
        # its disposable trust must never become production trust.
        internal_proof = json.loads(self.graph_proof.read_bytes())
        fixture_record = dict(schema="synthetic-ci-fixture-proof/1",
            actor=dict(id="ci-fixture", kind="service", name="Synthetic CI fixture"),
            synthetic=True, human_approval=False, activation_authorized=False,
            qualified_run_admissible=False,
            simulated_control_path_proof=internal_proof,
            simulated_proof_sha256=self.proof_hash,
            run_id=os.environ["GITHUB_RUN_ID"], run_attempt=os.environ["GITHUB_RUN_ATTEMPT"])
        from lightyear_control_tower.verification import verify_decision, DecisionVerificationError
        event = next(e for e in internal_proof["journal"]["events"]
                     if e["content_sha256"] == internal_proof["decision_sha256"])
        self.assertEqual("ci-fixture", event["actor"]["id"])
        self.assertEqual("Synthetic CI fixture", event["actor"]["name"])
        source_root = Path(__file__).resolve().parents[1]
        for key_path, expected_key in (
            ("docs/factory/posttran-key-change-2026-10-23/authority.public.pem",
             "658ba69010237ebc143a1e6d2c519f7d2adb1843993bc171c1d015e7b86b0c8a"),
            ("docs/factory/factory-authority.public.pem",
             "7e1fc72cf3d4d66e6e269a1b73c7e5a215cfa537824a28ceb9861ce006b12f61")):
            public_key = (source_root / key_path).read_bytes()
            self.assertEqual(expected_key, hashlib.sha256(public_key).hexdigest())
            for rejected in (internal_proof, fixture_record):
                with self.assertRaises(DecisionVerificationError):
                    verify_decision(rejected, public_key, "verify-graph-projection",
                        event["payload"]["bound"], scope="verify-graph",
                        expected_head=internal_proof["journal"]["journal_head_sha256"],
                        outcomes=["approved"])
        fixture_raw = canonical(fixture_record)
        fixture_hash = hashlib.sha256(fixture_raw).hexdigest()
        report = dict(schema="verify-graph-on-acceptance/1", status="passed",
                      observed_at=datetime.now(timezone.utc).isoformat(), tools_exercised=16,
                      graph_tools=sorted(self.graph_calls), projection_sha256=self.projection_hash,
                      approval_proof_sha256=fixture_hash, leak_scan_sha256=hashlib.sha256(scan_raw).hexdigest(),
                      actual_native_submissions=5, offline_replays=5, model_calls=0,
                      authority="ephemeral-CI-fixture", live_activation=False,
                      run_id=os.environ["GITHUB_RUN_ID"], run_attempt=os.environ["GITHUB_RUN_ATTEMPT"],
                      commit=os.environ["GITHUB_SHA"])
        report_raw = canonical(report)
        request = dict(schema="verify-graph-activation-preparation/1", unsigned=True,
                       importable=False, activation_authorized=False,
                       projection_sha256=self.projection_hash, approval_proof_sha256=fixture_hash,
                       leak_scan_sha256=hashlib.sha256(scan_raw).hexdigest(),
                       acceptance_sha256=hashlib.sha256(report_raw).hexdigest(),
                       run_id=report["run_id"], run_attempt=report["run_attempt"], commit=report["commit"],
                       approval_scope="ephemeral-CI-fixture-only",
                       remaining=["operator-approved projection proof and current trusted journal",
                                  "fresh VM acceptance bound to the operator evaluation inventory",
                                  "Howard activation decision"])
        # No private evaluation, response transcripts, keys, credentials or detailed
        # watch report are exported. The synthetic public proof is retained as proof.
        for name, raw in ((scan_name, scan_raw), ("graph-on-acceptance.json", report_raw),
                          ("unsigned-activation-preparation.json", canonical(request)),
                          ("ci-fixture-approval-proof.json", fixture_raw)):
            with (folder / name).open("xb") as stream:
                stream.write(raw)
