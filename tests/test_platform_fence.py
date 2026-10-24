"""Synthetic trusted-record tests, run in CI only."""
from hashlib import sha256
import json
import unittest
from tools.ci import platform_fence as fence


class PlatformFenceTests(unittest.TestCase):
    def documents(self):
        encoded = {}
        def put(path, value):
            raw = json.dumps(value, sort_keys=True).encode()
            encoded[path] = raw
            return dict(path=path, sha256=sha256(raw).hexdigest())
        item = lambda path: dict(path=path, sha256="1" * 64)
        original = put(fence.ORIGINAL, dict(files=[item("frozen/original")]))
        put(fence.AMENDMENT, dict(original_manifest_sha256=original["sha256"],
            files=[item("app/service/src/test/Original.java")], existing_authorized_change=item("frozen/changed")))
        scope = put("scope.json", dict(candidate_directory="candidate", interfaces=dict(source_path="interface.py")))
        workspace = put("workspace.json", {"work/capsule/manifest-only.py": "2" * 64})
        put(fence.F2, dict(schema="copau-f2-preparation/1", engineering_source_bindings={"a": item("engineering.py")},
            bindings=dict(scope=scope, workspace=workspace), work_order=dict(scope=dict(allowed_paths=["candidate"]))))
        put("docs/factory/copau-f8-support-bindings-synthetic.json", dict(selection=dict(source_bindings=[item("support.py")])))
        put(fence.PLAN, dict(bound_files={"posttran/original.py": "3" * 64}, candidate_files={"posttran/candidate.cbl": "4" * 64}))
        put(fence.KEY_CHANGE, {"synthetic": True})
        put("docs/factory/posttran-not-adopted-synthetic.json", {"not_adopted": True})
        return encoded

    def test_union_includes_original_amendment_manifest_only_and_posttran(self):
        docs = self.documents()
        result = fence.derive(docs.__getitem__, docs)
        required = {"frozen/original", "frozen/changed", "engineering.py", "support.py",
                    "work/capsule/manifest-only.py", "posttran/original.py", "posttran/candidate.cbl",
                    "docs/factory/posttran-not-adopted-synthetic.json"}
        self.assertTrue(required <= set(result["paths"]))
        self.assertFalse(result["automatic_expiry"])

    def test_additions_deletions_renames_and_prefix_replacement_refused(self):
        docs = self.documents()
        result = fence.derive(docs.__getitem__, docs)
        changed = ["posttran/original.py", "new-renamed.py", "candidate/Added.java", "candidate",
                   "app/service/src/test/Added.java"]
        self.assertEqual(fence.violations(result, changed), sorted(p for p in changed if p != "new-renamed.py"))
        self.assertEqual(fence.violations(result, ["unfenced/new-tool.py"]), [])

    def test_missing_or_changed_trusted_binding_refuses(self):
        for mutation in ("delete", "alter"):
            docs = self.documents()
            if mutation == "delete":
                del docs[fence.KEY_CHANGE]
            else:
                docs["scope.json"] = b'{"candidate_directory":"changed"}'
            with self.assertRaises((KeyError, ValueError)):
                fence.derive(docs.__getitem__, docs)

    def test_candidate_record_cannot_replace_trusted_base_record(self):
        trusted = self.documents()
        candidate = dict(trusted)
        candidate[fence.PLAN] = b'{"bound_files":{},"candidate_files":{}}'
        result = fence.derive(trusted.__getitem__, trusted)
        self.assertIn(fence.PLAN, fence.violations(result, [fence.PLAN]))
        self.assertIn("posttran/original.py", result["paths"])
        with self.assertRaises(ValueError):
            fence.derive(candidate.__getitem__, candidate)

    def test_invalid_paths_and_support_inventory_refuse(self):
        for path in ("../x", "/x", "C:/x", "a\\b", "a//b", "a\nb"):
            with self.assertRaises(ValueError):
                fence.safe_path(path)
        docs = self.documents()
        with self.assertRaisesRegex(ValueError, "missing-support-bindings"):
            fence.derive(docs.__getitem__, [p for p in docs if "support-bindings-" not in p])
