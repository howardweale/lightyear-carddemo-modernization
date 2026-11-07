"""Public opaque fixtures only, executed through existing CI discovery."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import unittest

from lightyear_control_tower.decisions import canonical
from lightyear_execution.helper_route_contract import (
    MAX_CIPHERTEXT, CiphertextDescriptor, HelperRouteBinding,
    HelperRouteExchange, HelperRouteRefused,
)


class HelperRouteContractTests(unittest.TestCase):
    def setUp(self):
        self.binding = HelperRouteBinding("1" * 40, "2" * 64, "3" * 64, "4" * 64,
                                          "5" * 64, "6" * 64, "2099-01-01T00:00:00Z")
        self.rows = (CiphertextDescriptor.from_ciphertext(
            "expected-source.json", b"age-encryption.org/v1\nopaque-public-fixture"),)
        self.names = frozenset(["expected-source.json"])
        self.wall = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.mono = 10

    def exchange(self, **updates):
        args = dict(binding=self.binding, artifacts=self.rows, expected_names=self.names,
                    original_monotonic_deadline=50, wall_clock=lambda: self.wall,
                    monotonic_clock=lambda: self.mono)
        args.update(updates)
        return HelperRouteExchange(**args)

    def reply(self, request, **updates):
        value = json.loads(request)
        response = dict(schema="helper-route-response/1",
                        request_sha256=hashlib.sha256(request).hexdigest(),
                        binding=value["binding"], artifacts=value["artifacts"],
                        result="ciphertext-received")
        response.update(updates)
        return canonical(response)

    def test_round_trip_matches_public_binding_without_native_claim(self):
        exchange = self.exchange()
        request = exchange.export_request()
        self.assertIs(json.loads(request)["native_qualification"], False)
        response = self.reply(request)
        result = exchange.consume_authenticated_response(response)
        self.assertEqual(result.artifact_names, ("expected-source.json",))
        self.assertEqual(result.request_sha256, hashlib.sha256(request).hexdigest())
        self.assertEqual(result.response_sha256, hashlib.sha256(response).hexdigest())

    def test_export_and_response_are_each_single_use(self):
        exchange = self.exchange()
        request = exchange.export_request()
        with self.assertRaises(HelperRouteRefused):
            exchange.export_request()
        exchange.consume_authenticated_response(self.reply(request))
        with self.assertRaises(HelperRouteRefused):
            exchange.consume_authenticated_response(self.reply(request))

    def test_response_before_export_refused_without_enabling_dispatch(self):
        exchange = self.exchange()
        with self.assertRaises(HelperRouteRefused):
            exchange.consume_authenticated_response(b"{}")
        self.assertTrue(exchange.export_request())

    def test_bad_response_consumes_attempt(self):
        for bad in (b"{}", b"[]", b"not-json", b'{"x":1,"x":1}', b"x" * 17000):
            exchange = self.exchange()
            request = exchange.export_request()
            with self.assertRaises(HelperRouteRefused):
                exchange.consume_authenticated_response(bad)
            with self.assertRaisesRegex(HelperRouteRefused, "no-response-retry"):
                exchange.consume_authenticated_response(self.reply(request))

    def test_all_provenance_fields_are_bound(self):
        for field in self.binding.document():
            exchange = self.exchange()
            request = exchange.export_request()
            binding = dict(self.binding.document())
            binding[field] = "substitution"
            with self.subTest(field=field), self.assertRaises(HelperRouteRefused):
                exchange.consume_authenticated_response(self.reply(request, binding=binding))

    def test_recipient_seed_and_source_scope_cannot_be_omitted(self):
        for field in ("recipient_policy_sha256", "seed_commitment_sha256", "source_index_sha256"):
            with self.subTest(field=field), self.assertRaises(HelperRouteRefused):
                replace(self.binding, **{field: ""})

    def test_reply_cannot_change_hash_size_or_inventory(self):
        for field, substitute in (("name", "another.json"),
                                  ("ciphertext_sha256", "a" * 64), ("ciphertext_bytes", 1)):
            exchange = self.exchange()
            request = exchange.export_request()
            rows = json.loads(request)["artifacts"]
            rows[0][field] = substitute
            with self.subTest(field=field), self.assertRaises(HelperRouteRefused):
                exchange.consume_authenticated_response(self.reply(request, artifacts=rows))

    def test_unknown_claim_or_secret_field_is_refused(self):
        for extra in (dict(native_qualified=True), dict(plaintext="fixture"), dict(pin="fixture")):
            exchange = self.exchange()
            request = exchange.export_request()
            with self.assertRaises(HelperRouteRefused):
                exchange.consume_authenticated_response(self.reply(request, **extra))

    def test_equal_numeric_value_with_wrong_json_type_refused(self):
        exchange = self.exchange()
        request = exchange.export_request()
        rows = json.loads(request)["artifacts"]
        rows[0]["ciphertext_bytes"] = float(rows[0]["ciphertext_bytes"])
        with self.assertRaises(HelperRouteRefused):
            exchange.consume_authenticated_response(self.reply(request, artifacts=rows))

    def test_missing_duplicate_or_extra_artifacts_refused(self):
        extra = replace(self.rows[0], name="another.json")
        for rows in ((), self.rows * 2, self.rows + (extra,)):
            with self.subTest(rows=rows), self.assertRaises(HelperRouteRefused):
                self.exchange(artifacts=rows)
        with self.assertRaises(HelperRouteRefused):
            self.exchange(expected_names=frozenset(["another.json"]))

    def test_original_wall_and_monotonic_deadlines_each_enforced(self):
        for wall, mono in ((datetime(2099, 1, 1, tzinfo=timezone.utc), 10),
                           (self.wall, 50)):
            exchange = self.exchange()
            request = exchange.export_request()
            self.wall, self.mono = wall, mono
            with self.assertRaises(HelperRouteRefused):
                exchange.consume_authenticated_response(self.reply(request))
            self.wall = datetime(2026, 1, 1, tzinfo=timezone.utc)
            self.mono = 10

    def test_expired_export_cannot_rebase_and_retry(self):
        exchange = self.exchange()
        self.mono = 50
        with self.assertRaises(HelperRouteRefused):
            exchange.export_request()
        self.mono = 10
        with self.assertRaises(HelperRouteRefused):
            exchange.export_request()

    def test_post_verification_deadline_rechecked(self):
        sequence = iter([10, 10, 10, 50])
        exchange = self.exchange(monotonic_clock=lambda: next(sequence))
        request = exchange.export_request()
        with self.assertRaises(HelperRouteRefused):
            exchange.consume_authenticated_response(self.reply(request))

    def test_clock_shape_and_nonfinite_deadlines_refused(self):
        for deadline in (True, float("nan"), float("inf"), "50"):
            with self.assertRaises(HelperRouteRefused):
                self.exchange(original_monotonic_deadline=deadline)
        with self.assertRaises(HelperRouteRefused):
            self.exchange(wall_clock=lambda: datetime(2026, 1, 1))
        with self.assertRaises(HelperRouteRefused):
            self.exchange(monotonic_clock=lambda: float("nan"))

    def test_descriptor_names_sizes_and_input_format(self):
        for name in ("../secret.json", "/secret.json", "key.pem", "x\n.json"):
            with self.assertRaises(HelperRouteRefused):
                replace(self.rows[0], name=name)
        for size in (0, True, MAX_CIPHERTEXT + 1):
            with self.assertRaises(HelperRouteRefused):
                replace(self.rows[0], ciphertext_bytes=size)
        for value in (b"", b"plaintext", "age-encryption.org/v1\ntext"):
            with self.assertRaises(HelperRouteRefused):
                CiphertextDescriptor.from_ciphertext("expected-source.json", value)

    def test_total_size_is_bounded_and_artifact_order_canonical(self):
        large = (replace(self.rows[0], ciphertext_bytes=MAX_CIPHERTEXT),
                 replace(self.rows[0], name="another.json"))
        names = frozenset(row.name for row in large)
        with self.assertRaises(HelperRouteRefused):
            self.exchange(artifacts=large, expected_names=names)
        rows = (self.rows[0], replace(self.rows[0], name="another.json"))
        a = self.exchange(artifacts=rows, expected_names=names).export_request()
        b = self.exchange(artifacts=rows[::-1], expected_names=names).export_request()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
