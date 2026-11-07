"""Opaque public fixtures; existing CI discovery executes these tests."""
from dataclasses import replace
import hashlib
import json
import unittest

from lightyear_control_tower.decisions import canonical
from lightyear_execution.helper_route_contract import (
    MAX_CIPHERTEXT, CiphertextDescriptor, HelperRouteBinding, HelperRouteRefused,
)
from lightyear_execution.helper_route_provenance import match_helper_provenance


class HelperRouteProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.execution = "run-17.case-b.attempt-2"
        self.names = frozenset({"answer-a.json", "answer-b.json"})
        self.rows = (
            CiphertextDescriptor("sealed-a.json", "a" * 64, 100),
            CiphertextDescriptor("sealed-b.json", "b" * 64, 200),
        )
        self.index_doc = dict(
            schema="helper-source-index/1",
            source_commit="1" * 40,
            execution_id=self.execution,
            attempt_identity_sha256="2" * 64,
            sources=[
                dict(source_name="answer-a.json", ciphertext_name="sealed-a.json"),
                dict(source_name="answer-b.json", ciphertext_name="sealed-b.json"),
            ],
        )
        self.index = canonical(self.index_doc)
        self.binding = HelperRouteBinding(
            "1" * 40, "2" * 64, hashlib.sha256(self.index).hexdigest(),
            "4" * 64, "5" * 64, "6" * 64, "2099-01-01T00:00:00Z",
        )

    def inventory(self, binding=None, **updates):
        doc = dict(
            schema="helper-ciphertext-inventory/1",
            binding=(binding or self.binding).document(),
            execution_id=self.execution,
            artifacts=[row.document() for row in self.rows],
        )
        doc.update(updates)
        return canonical(doc)

    def match(self, index=None, inventory=None, **updates):
        args = dict(
            expected_binding=self.binding,
            expected_execution_id=self.execution,
            expected_source_names=self.names,
            expected_artifacts=self.rows,
        )
        args.update(updates)
        return match_helper_provenance(
            self.index if index is None else index,
            self.inventory() if inventory is None else inventory, **args,
        )

    def assert_index_refused_even_if_digest_pinned(self, doc):
        raw = canonical(doc)
        binding = replace(self.binding, source_index_sha256=hashlib.sha256(raw).hexdigest())
        with self.assertRaises(HelperRouteRefused):
            self.match(index=raw, inventory=self.inventory(binding),
                       expected_binding=binding)

    def test_complete_bijection_matches_without_execution_capability(self):
        result = self.match()
        self.assertEqual(result.source_ciphertext_pairs, (
            ("answer-a.json", "sealed-a.json"), ("answer-b.json", "sealed-b.json")))
        self.assertEqual(result.source_index_sha256, self.binding.source_index_sha256)
        self.assertEqual(result.inventory_sha256, hashlib.sha256(self.inventory()).hexdigest())
        self.assertEqual(result.execution_id, self.execution)
        self.assertEqual(set(vars(result)), {
            "source_index_sha256", "inventory_sha256", "execution_id",
            "source_ciphertext_pairs",
        })

    def test_expected_descriptor_order_does_not_change_match(self):
        self.assertEqual(self.match(), self.match(expected_artifacts=self.rows[::-1]))

    def test_rebinding_any_source_execution_attempt_field_refuses(self):
        for field, value in (
            ("source_commit", "9" * 40),
            ("execution_id", "another-execution"),
            ("attempt_identity_sha256", "9" * 64),
            ("schema", "helper-source-index/2"),
        ):
            with self.subTest(field=field):
                self.assert_index_refused_even_if_digest_pinned(
                    dict(self.index_doc, **{field: value}))

    def test_index_bytes_must_match_retained_digest(self):
        changed = dict(self.index_doc, sources=list(reversed(self.index_doc["sources"])))
        with self.assertRaisesRegex(HelperRouteRefused, "index-digest"):
            self.match(index=canonical(changed))

    def test_row_order_is_unambiguous_even_if_digest_pinned(self):
        self.assert_index_refused_even_if_digest_pinned(
            dict(self.index_doc, sources=list(reversed(self.index_doc["sources"]))))

    def test_source_omission_extra_duplicate_and_substitution_refused(self):
        rows = self.index_doc["sources"]
        bad = [
            rows[:1], rows + [rows[0]], [rows[0], rows[0]],
            [rows[0], dict(rows[1], source_name="unexpected.json")],
        ]
        for sources in bad:
            with self.subTest(sources=sources):
                self.assert_index_refused_even_if_digest_pinned(
                    dict(self.index_doc, sources=sources))

    def test_ciphertext_alias_requires_one_to_one_exact_inventory(self):
        rows = self.index_doc["sources"]
        for name in ("sealed-a.json", "unexpected.json"):
            with self.subTest(name=name):
                self.assert_index_refused_even_if_digest_pinned(dict(
                    self.index_doc, sources=[rows[0], dict(rows[1], ciphertext_name=name)]))

    def test_malformed_or_secret_source_rows_refused(self):
        rows = self.index_doc["sources"]
        for bad in (
            None, [], "answer-a.json", {}, dict(rows[0], plaintext="public-fixture"),
            dict(source_name="answer-a.json"), dict(rows[0], source_name="../answer.json"),
            dict(rows[0], ciphertext_name="/private.json"),
            dict(rows[0], source_name=True),
        ):
            with self.subTest(row=bad):
                self.assert_index_refused_even_if_digest_pinned(
                    dict(self.index_doc, sources=[bad, rows[1]]))

    def test_index_unknown_missing_fields_and_nonlist_rows_refused(self):
        for doc in (
            dict(self.index_doc, private_path="fixture"),
            {k: v for k, v in self.index_doc.items() if k != "schema"},
            dict(self.index_doc, sources={}),
        ):
            self.assert_index_refused_even_if_digest_pinned(doc)

    def test_every_inventory_binding_field_is_exact(self):
        for field in self.binding.document():
            binding = dict(self.binding.document(), **{field: "substitution"})
            with self.subTest(field=field), self.assertRaises(HelperRouteRefused):
                doc = json.loads(self.inventory())
                doc["binding"] = binding
                self.match(inventory=canonical(doc))

    def test_inventory_execution_schema_unknown_and_missing_fields_refused(self):
        docs = [
            dict(execution_id="another-execution"), dict(schema="unknown/1"),
            dict(native_qualified=True), dict(pin="public-fixture"),
        ]
        for update in docs:
            with self.subTest(update=update), self.assertRaises(HelperRouteRefused):
                self.match(inventory=self.inventory(**update))
        doc = json.loads(self.inventory())
        del doc["binding"]
        with self.assertRaises(HelperRouteRefused):
            self.match(inventory=canonical(doc))

    def test_inventory_omission_extra_duplicate_and_reordering_refused(self):
        rows = [row.document() for row in self.rows]
        for bad in ([], rows[:1], rows + [rows[0]], [rows[0], rows[0]], rows[::-1]):
            with self.subTest(rows=bad), self.assertRaises(HelperRouteRefused):
                self.match(inventory=self.inventory(artifacts=bad))

    def test_inventory_descriptor_hash_size_name_and_type_refused(self):
        rows = [row.document() for row in self.rows]
        for field, value in (
            ("name", "other.json"), ("ciphertext_sha256", "9" * 64),
            ("ciphertext_bytes", 99), ("ciphertext_bytes", 100.0),
            ("ciphertext_bytes", True), ("plaintext", "public-fixture"),
        ):
            changed = [dict(rows[0], **{field: value}), rows[1]]
            with self.subTest(field=field, value=value), self.assertRaises(HelperRouteRefused):
                self.match(inventory=self.inventory(artifacts=changed))

    def test_invalid_json_duplicate_keys_noncanonical_and_oversize_refused(self):
        bad = (
            b"", b"[]", b"null", b"invalid", b'{"x":1,"x":1}',
            b'{"schema":"x", "schema":"y"}', b'{"x":NaN}',
            b"x" * 17000, self.index + b"\n", self.index.decode(),
            b"\xff",
        )
        for raw in bad:
            with self.subTest(raw=repr(raw)[:50]):
                with self.assertRaises(HelperRouteRefused):
                    self.match(index=raw)
                with self.assertRaises(HelperRouteRefused):
                    self.match(inventory=raw)

    def test_independent_expected_scope_cannot_be_empty_or_ambiguous(self):
        for names in (frozenset(), set(self.names), frozenset({"wrong.json"}),
                      frozenset({"answer-a.json", "../answer.json"})):
            with self.subTest(names=names), self.assertRaises(HelperRouteRefused):
                self.match(expected_source_names=names)
        for rows in ((), list(self.rows), self.rows * 2, (self.rows[0], self.rows[0]),
                     (self.rows[0], {})):
            with self.subTest(rows=rows), self.assertRaises(HelperRouteRefused):
                self.match(expected_artifacts=rows)
        with self.assertRaises(HelperRouteRefused):
            self.match(expected_binding=self.binding.document())

    def test_expected_execution_is_independent_and_bounded(self):
        for execution in (None, True, "", "../run", "x" * 101, "new-execution"):
            with self.subTest(execution=execution), self.assertRaises(HelperRouteRefused):
                self.match(expected_execution_id=execution)

    def test_total_ciphertext_size_is_bounded(self):
        rows = (replace(self.rows[0], ciphertext_bytes=MAX_CIPHERTEXT), self.rows[1])
        with self.assertRaisesRegex(HelperRouteRefused, "total-size"):
            self.match(expected_artifacts=rows)

    def test_same_ciphertext_digest_does_not_replace_expected_name(self):
        # Repeated opaque bytes can still be named distinctly; names stay exact.
        rows = (self.rows[0], replace(self.rows[1], ciphertext_sha256=self.rows[0].ciphertext_sha256))
        inventory = self.inventory(artifacts=[row.document() for row in rows])
        result = self.match(inventory=inventory, expected_artifacts=rows)
        self.assertEqual(len(result.source_ciphertext_pairs), 2)


if __name__ == "__main__":
    unittest.main()
