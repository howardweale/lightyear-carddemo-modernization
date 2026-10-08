import copy
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import test_graph_memory as fixtures
from verify_graph_support import GraphFixture, read, leak_check, digest
from lightyear_control_tower.decisions import canonical
from lightyear_control_tower.knowledge_status import read_status, annotation_view
from lightyear_factory.annotations import leak_certificate
from lightyear_factory.annotation_tools import review_request
from lightyear_factory.knowledge_service import KnowledgeService
from lightyear_factory.evaluation_matrix import run_matrix
from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_toolkit.graph import GraphTools


class IntegrationTests(unittest.TestCase):
    setUp = fixtures.MemoryTests.setUp
    body = fixtures.MemoryTests.body
    create = fixtures.MemoryTests.create
    approve = fixtures.MemoryTests.approve
    proof = fixtures.MemoryTests.proof
    outcome = fixtures.MemoryTests.outcome

    def test_signed_outcome_service_binds_context_idempotently(self):
        a = self.create()
        self.approve(a)
        context = dict(annotation_ids=[a["id"]])
        context["content_sha256"] = canonical_hash(context)
        receipt = dict(
            run_id="one",
            annotation_context=dict(
                annotation_ids=[a["id"]], context_sha256=context["content_sha256"]
            ),
        )
        receipt["content_sha256"] = canonical_hash(receipt)
        bound = dict(
            annotation_ids=[a["id"]], full_context_sha256=context["content_sha256"]
        )
        attestation = self.judge.sign(
            dict(
                schema="annotation-outcome/1",
                customer_id="public",
                evaluation_class="public-calibration",
                independently_replayed=True,
                context=bound,
                context_sha256=digest(bound),
                run_id="one",
                status="passed",
                anchors=a["anchors"],
                resolved_categories=[],
                run_receipt_sha256=receipt["content_sha256"],
            )
        )
        row = dict(run_receipt=receipt, context=context, attestation=attestation)
        service = KnowledgeService(self.ledger, self.signer, self.root)
        for _ in range(2):
            service.sync(outcomes=[row], trust={}, protected_values=(), leak_checks={})
        self.assertEqual(len(self.ledger.replay()[a["id"]]["outcomes"]), 1)
        changed = copy.deepcopy(row)
        changed["context"]["annotation_ids"] = []
        with self.assertRaises(ValueError):
            service.sync(
                outcomes=[changed], trust={}, protected_values=(), leak_checks={}
            )
        changed = copy.deepcopy(row)
        changed["attestation"]["status"] = "failed"
        with self.assertRaises(ValueError):
            service.sync(
                outcomes=[changed], trust={}, protected_values=(), leak_checks={}
            )

    def test_failed_leak_can_be_rejected_but_never_shown(self):
        a = self.create(text="protected-test-string")
        cert = leak_certificate(
            a, ["protected-test-string"], self.judge, inventory_sha256="a" * 64
        )
        proof = self.proof(
            "graph-annotation", dict(annotation=a, leak_check=cert), "rejected"
        )
        head = proof["journal"]["journal_head_sha256"]
        self.ledger.append(
            "reject",
            dict(id=a["id"], leak_check=cert, proof=proof, trusted_head=head),
            self.signer,
            expected_head=head,
        )
        self.assertEqual(self.ledger.replay()[a["id"]]["status"], "rejected")
        request = review_request(
            self.root,
            "graph-memory",
            "graph-annotation",
            dict(annotation=a, leak_check=cert),
        )
        item = self.console.review(self.token, request["id"])
        folder = self.root / "factory"
        folder.mkdir(exist_ok=True)
        (self.root / "judge-public.pem").write_bytes(self.judge.public)
        (folder / "knowledge-console.json").write_bytes(
            canonical(
                dict(
                    scope="graph-memory",
                    judge_public_key="judge-public.pem",
                    inventory_sha256="a" * 64,
                )
            )
        )
        self.assertTrue(annotation_view(self.root, item)["text_withheld"])
        self.assertNotIn(
            "protected-test-string", json.dumps(annotation_view(self.root, item))
        )

    def test_signed_status_and_decision_head_fail_closed(self):
        a = self.create()
        cert = leak_certificate(a, [], self.judge, inventory_sha256="a" * 64)
        proof = self.proof(
            "graph-annotation", dict(annotation=a, leak_check=cert), "approved"
        )
        head = proof["journal"]["journal_head_sha256"]
        payload = dict(id=a["id"], leak_check=cert, proof=proof, trusted_head=head)
        with self.assertRaises(ValueError):
            self.ledger.append("approve", payload, self.signer, expected_head="b" * 64)
        changed = copy.deepcopy(payload)
        changed["proof"]["decision_sha256"] = "b" * 64
        with self.assertRaises(ValueError):
            self.ledger.append("approve", changed, self.signer, expected_head=head)
        service = KnowledgeService(self.ledger, self.signer, self.root)
        status = service.status()
        folder = self.root / "factory"
        folder.mkdir(exist_ok=True)
        (self.root / "ledger-public.pem").write_bytes(self.signer.public)
        (folder / "status.json").write_bytes(canonical(status))
        (folder / "knowledge-console.json").write_bytes(
            canonical(
                dict(
                    scope="graph-memory",
                    status_file="factory/status.json",
                    public_key="ledger-public.pem",
                )
            )
        )
        self.assertTrue(read_status(self.root, "graph-memory")["available"])
        self.assertFalse(read_status(self.root, "other")["available"])
        status["health"]["items"] = []
        (folder / "status.json").write_bytes(canonical(status))
        with self.assertRaises(ValueError):
            read_status(self.root, "graph-memory")

    def test_matrix_without_approval_never_invokes_agents(self):
        agents = Mock()
        plan = dict(
            commit="abc",
            max_cost_usd=1,
            cells=[dict(model="model", policy=dict(max_cost_usd=1))],
        )
        with self.assertRaises((ValueError, TypeError, KeyError)):
            run_matrix(
                plan,
                None,
                {},
                commit="abc",
                project_root=self.root,
                output_root=self.root / "matrix",
                agent_factories={"model": agents},
                catalogs={},
            )
        agents.assert_not_called()
        self.assertFalse((self.root / "matrix").exists())

    def test_matrix_validates_all_cells_before_first_execution(self):
        catalog = dict(evaluation_class="public-calibration", workload_id="INTCALC")
        h = canonical_hash(catalog)
        path = self.root / "catalog.json"
        path.write_bytes(canonical(catalog))
        good = dict(
            model="m",
            task_type="implement",
            workload="INTCALC",
            catalog_sha256=h,
            evaluation_class="public-calibration",
            policy=dict(max_cost_usd=1),
        )
        plan = dict(
            commit="abc", max_cost_usd=2, cells=[good, {**good, "task_type": "invalid"}]
        )
        with (
            patch(
                "lightyear_factory.evaluation_matrix.approve",
                return_value={"actor": {"id": "howard"}},
            ),
            patch(
                "lightyear_factory.evaluation_matrix.subprocess.run",
                side_effect=[Mock(stdout="abc"), Mock(stdout="")],
            ),
            patch(
                "lightyear_factory.evals.load_evaluation_catalog", return_value=catalog
            ),
            patch("lightyear_factory.evals.run_model_evaluation") as execute,
        ):
            with self.assertRaisesRegex(ContractError, "invalid matrix cell"):
                run_matrix(
                    plan,
                    {},
                    {"operator_id": "howard"},
                    commit="abc",
                    project_root=Path(__file__).resolve().parents[1],
                    output_root=self.root / "matrix",
                    agent_factories={"m": Mock()},
                    catalogs={h: path},
                )
            execute.assert_not_called()
        self.assertFalse((self.root / "matrix").exists())


    def test_matrix_refuses_alias_or_unverified_provider_before_calls(self):
        catalog=dict(evaluation_class='public-calibration',workload_id='INTCALC')
        h=canonical_hash(catalog);path=self.root/'catalog.json';path.write_bytes(canonical(catalog))
        for version,verified in [('gpt-latest',True),('gpt-4.1-2025-04-14',False)]:
            good=dict(model='m',model_id=version,task_type='implement',workload='INTCALC',
                catalog_sha256=h,evaluation_class='public-calibration',policy=dict(max_cost_usd=1))
            plan=dict(commit='abc',max_cost_usd=1,cells=[good])
            with patch('lightyear_factory.evaluation_matrix.approve',return_value={'actor':{'id':'howard'}}), patch(
                'lightyear_factory.evaluation_matrix.subprocess.run',side_effect=[Mock(stdout='abc'),Mock(stdout='')]), patch(
                'lightyear_factory.evals.load_evaluation_catalog',return_value=catalog), patch(
                'lightyear_factory.evals.run_model_evaluation') as execute:
                with self.assertRaises((ContractError,ValueError)):
                    run_matrix(plan,{}, {'operator_id':'howard'},commit='abc',project_root=self.root,output_root=self.root/'matrix',
                        agent_factories={'m':Mock()},catalogs={h:path},
                        providers={'m':Mock(model=version,require_snapshot_response=verified)})
                execute.assert_not_called()
            self.assertFalse((self.root/'matrix').exists())


class ProjectionIntegrationTests(GraphFixture):
    def test_reviewed_annotation_reaches_guidance_and_protected_value_blocks_projection(
        self,
    ):
        f = fixtures.MemoryTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        anchor = "legacy:cobol-paragraph:CBACT04C:1300-COMPUTE-INTEREST"
        a = f.create(anchors=[anchor], customer_id="carddemo-reference")
        f.approve(a)
        manifest = self.build(annotation_ledger=f.ledger, hybrid=True)
        p = read(self.out / "projection.json.gz")
        self.assertEqual([x["id"] for x in p["annotations"]], [a["id"]])
        leak_check(
            self.out,
            digest(self.lane),
            set(),
            self.signer,
            evaluation_inventory_sha256="a" * 64,
        )
        proof, trust = self.approve(manifest)
        from lightyear_factory.revocations import subscribe
        from lightyear_toolkit.revocations import RevocationReader,provision_state
        subscribe(f.ledger,f.signer,self.out)
        provision_state(self.root/'reader-state',p['revocation_binding'],manifest['projection_sha256'],json.loads((self.out/'revocations/head.json').read_bytes()),json.loads((self.out/'revocations/revocations.json').read_bytes()))
        reader=RevocationReader(self.out/'revocations',p['revocation_binding'],manifest['projection_sha256'],state_directory=self.root/'reader-state')
        tools = GraphTools(p, manifest, {"review_after": "2099-01-01"}, self.root, None,revocations=reader)
        guidance = tools._graph_guidance(anchor)
        self.assertIn(a["id"], json.dumps(guidance))
        self.assertNotIn(a["text"], json.dumps(p["search_index"]))
        second = self.root / "second-projection"
        self.build(annotation_ledger=f.ledger, hybrid=True, out=second)
        report = leak_check(
            second,
            digest(self.lane),
            {a["text"]},
            self.signer,
            evaluation_inventory_sha256="a" * 64,
        )
        self.assertFalse(report["passed"])

    def test_inferred_annotation_never_enters_search_index(self):
        self.build()
        p = read(self.out / "projection.json.gz")
        p["annotations"] = [
            dict(
                anchors=[p["nodes"][0]["id"]],
                provenance="inferred",
                text="inferred-unique-text",
            )
        ]
        from lightyear_knowledge_graph.hybrid import build_index

        self.assertNotIn("inferred-unique-text", json.dumps(build_index(p)))
