from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lightyear_knowledge_graph.extractors import extract_modern
from lightyear_knowledge_graph.inputs import (
    canonical_hash,
    load_semantic_inputs,
    validate_semantic_inputs,
)
from lightyear_knowledge_graph.model import KnowledgeGraph


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "knowledge" / "semantic-inputs.json"


class SemanticInputTests(unittest.TestCase):
    def test_committed_manifest_is_content_addressed_and_resolves_exact_files(self) -> None:
        payload = load_semantic_inputs(MANIFEST, ROOT)
        self.assertEqual(payload["content_sha256"], canonical_hash(payload))
        self.assertIn(
            "candidate-java/src/main/java/ai/lightyear/carddemo/service/MixedPliAuthorizationService.java",
            payload["modern_files"],
        )
        self.assertNotIn("src/lightyear_knowledge_graph/capability.py", payload["modern_files"])

    def test_manifest_rejects_drift_unsafe_paths_and_missing_files(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        payload["modern_files"].append("../outside.py")
        self.assertIn(
            "semantic input content_sha256 is invalid",
            validate_semantic_inputs(payload, ROOT),
        )
        self.assertTrue(
            any("escapes the project" in error for error in validate_semantic_inputs(payload, ROOT))
        )

        missing = json.loads(MANIFEST.read_text(encoding="utf-8"))
        missing["modern_files"].append("zz-missing.py")
        missing["modern_files"].sort()
        missing["content_sha256"] = canonical_hash(missing)
        self.assertTrue(
            any("is missing" in error for error in validate_semantic_inputs(missing, ROOT))
        )

    def test_undeclared_implementation_edit_does_not_change_semantic_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            declared = root / "candidate.py"
            unrelated = root / "viewer.py"
            declared.write_text("VALUE = 1\n", encoding="utf-8")
            unrelated.write_text("LABEL = 'first'\n", encoding="utf-8")

            first = self._graph(root, declared).to_dict()["content_sha256"]
            unrelated.write_text("LABEL = 'second'\n", encoding="utf-8")
            second = self._graph(root, declared).to_dict()["content_sha256"]
            self.assertEqual(first, second)

            declared.write_text("VALUE = 2\n", encoding="utf-8")
            third = self._graph(root, declared).to_dict()["content_sha256"]
            self.assertNotEqual(second, third)

    @staticmethod
    def _graph(root: Path, declared: Path) -> KnowledgeGraph:
        graph = KnowledgeGraph(
            "test:semantic-inputs",
            [
                {
                    "id": "source:lightyear-carddemo",
                    "kind": "git_repository",
                    "repository": "test",
                    "commit": "test",
                }
            ],
            {"ontology_id": "test", "schema_version": "1.0", "content_sha256": "0" * 64},
        )
        extract_modern(graph, root, [declared])
        return graph


if __name__ == "__main__":
    unittest.main()
