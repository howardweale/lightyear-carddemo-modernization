import copy
import json
import subprocess
import types
from dataclasses import replace
from pathlib import Path
from verify_graph_support import GraphFixture, read, leak_check, digest
from lightyear_control_tower.decisions import canonical
from lightyear_knowledge_graph.hybrid import build_index, search, LocalEmbedding
from lightyear_toolkit.graph import GraphTools
from lightyear_factory.context import GraphContextAssembler
from lightyear_factory.benchmark import benchmark_work_order


class SearchTests(GraphFixture):
    def test_public_carddemo_hybrid_and_projection_identity(self):
        manifest = self.build(hybrid=True)
        p = read(self.out / "projection.json.gz")
        self.assertEqual(
            p["search_index"],
            build_index({k: v for k, v in p.items() if k != "search_index"}),
        )
        self.assertEqual(
            manifest["search_index_sha256"], p["search_index"]["content_sha256"]
        )
        results = search(p, "monthly interest on account balance")
        self.assertTrue(
            any(
                "CBACT04C" in r["id"]
                and "INTEREST" in r["id"]
                and r["kind"] == "cobol_paragraph"
                for r in results[:3]
            ),
            results[:3],
        )
        self.assertTrue(all(r["id"] in {n["id"] for n in p["nodes"]} for r in results))
        self.assertTrue(all("why" in r and "line_ranges" in r for r in results))
        with self.assertRaises(ValueError):
            search(p, "interest", anchor="outside")
        p["search_index"]["documents"][0]["text"] = "poison"
        with self.assertRaises(ValueError):
            search(p, "interest")

    def test_confidential_external_refused_before_provider_call(self):
        self.build(mode="confidential")
        p = read(self.out / "projection.json.gz")

        class External:
            local = False
            provider_id = "external"
            version = "1"

            def embed(self, texts):
                raise AssertionError("external call forbidden")

        with self.assertRaisesRegex(ValueError, "confidential"):
            build_index(p, External())

    def test_default_lexical_unchanged_and_bounded_hybrid_pages(self):
        self.build(hybrid=True)
        p = read(self.out / "projection.json.gz")
        tools = GraphTools(
            p,
            read(self.out / "projection-manifest.json"),
            {"review_after": "2099-01-01"},
            self.root,
            None,
            cap=2048,
        )
        self.assertEqual(
            tools._graph_search("INTEREST"),
            tools._graph_search("INTEREST", mode="lexical"),
        )
        page = tools._graph_search(
            "monthly interest on account balance", mode="hybrid", limit=2
        )
        self.assertLessEqual(len(canonical(page)), 2048)
        if page["cursor"]:
            next_page = tools._graph_search(
                "monthly interest on account balance",
                mode="hybrid",
                limit=2,
                cursor=page["cursor"],
            )
            self.assertFalse(
                {r["id"] for r in page["items"]} & {r["id"] for r in next_page["items"]}
            )

    def test_context_default_matches_base_bytes(self):
        root = Path(__file__).resolve().parents[1]
        source = subprocess.check_output(
            ["git", "show", "990369c1:src/lightyear_factory/context.py"], cwd=root
        ).decode()
        module = types.ModuleType("lightyear_factory.old_context")
        module.__package__ = "lightyear_factory"
        exec(compile(source, "old_context.py", "exec"), module.__dict__)
        order = benchmark_work_order("rounding-mode")
        graph = root / "knowledge/graph.snapshot.json.gz"
        evidence = root / "knowledge/evidence/source.pack.json.gz"
        old = module.GraphContextAssembler(graph, evidence).assemble(order, self.root)
        new = GraphContextAssembler(graph, evidence).assemble(order, self.root)
        self.assertEqual(canonical(old), canonical(new))

    def test_context_11_requires_real_projection_approval(self):
        manifest = self.build(hybrid=True)
        leak_check(
            self.out,
            digest(self.lane),
            set(),
            self.signer,
            evaluation_inventory_sha256="a" * 64,
        )
        proof, trust = self.approve(manifest)
        p = read(self.out / "projection.json.gz")
        root = p["nodes"][0]["id"]
        order = replace(
            benchmark_work_order("rounding-mode"),
            graph_node_ids=(root,),
            metadata={"context_schema": "1.1", "customer_id": "carddemo-reference"},
        )
        with self.assertRaises(ValueError):
            GraphContextAssembler(None, None).assemble(order, self.root)
        context = GraphContextAssembler(
            None, None, approved_projection=(self.out, proof, trust)
        ).assemble(order, self.root)
        self.assertEqual(context["schema_version"], "1.1")
        self.assertEqual(context["annotation_ids"], [])
        self.assertEqual(
            context["context_projection_sha256"], manifest["projection_sha256"]
        )
        for meta in (
            {"customer_id": "other"},
            {"campaign_id": "B06"},
            {"evaluation_class": "sealed-holdout"},
        ):
            with self.assertRaises(ValueError):
                GraphContextAssembler(
                    None, None, approved_projection=(self.out, proof, trust)
                ).assemble(
                    replace(order, metadata={**order.metadata, **meta}), self.root
                )
