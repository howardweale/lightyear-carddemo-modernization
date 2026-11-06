"""CI-only loader regressions; synthetic fixtures, no provider transport."""

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import test_graph_memory as fixtures
import test_graph_memory_routing as routing_fixtures
from lightyear_factory.agents import ModelAgentSet
from lightyear_factory.benchmark import benchmark_work_order
from lightyear_factory.contracts import ContractError
from lightyear_factory.model_config import load_router


class DefaultRouterLoadingTests(unittest.TestCase):
    def test_unapproved_alternatives_do_not_lease_credentials(self):
        default = dict(provider="openai", model="gpt-5.4-2026-03-05",
                       input_usd_per_million=2.5, output_usd_per_million=15,
                       max_output_tokens=4096)
        config = dict(default="default", models={
            "default": default,
            "alternative": {**default, "provider": "anthropic"},
        })
        broker = Mock()
        broker.read.return_value = "synthetic-test-only"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with patch("lightyear_factory.model_config.SnapshotOpenAIResponsesProvider") as constructor:
                router = load_router(path, secret_store=broker)
        from lightyear_factory.provider_secrets import NAMES
        broker.read.assert_called_once_with(NAMES["openai"])
        constructor.assert_called_once()
        self.assertEqual({"default"}, set(router.providers))
        constructor.return_value.complete.assert_not_called()
        # Loading a router does not grant controller/runtime admission.
        with self.assertRaisesRegex(ContractError, "controller-binding-required"):
            ModelAgentSet(router)._provider_for(benchmark_work_order("rounding-mode"))
        constructor.return_value.complete.assert_not_called()

    def test_missing_default_fails_before_credentials(self):
        broker = Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.json"
            path.write_text(json.dumps(dict(default="missing", models={})), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "default model not configured"):
                load_router(path, secret_store=broker)
        broker.read.assert_not_called()


class PolicyRouterLoadingTests(unittest.TestCase):
    # Reuse the existing real synthetic Tower proof fixture in CI. These test
    # keys are disposable fixtures, never operator credentials or qualification.
    setUp = fixtures.MemoryTests.setUp
    proof = fixtures.MemoryTests.proof

    def config(self):
        providers = {name: routing_fixtures.FakeProvider(name) for name in ("default", "primary", "fallback")}
        router = routing_fixtures.RoutingTests.router(self, providers)
        return dict(default="default", models={name: dict(model=name) for name in (*providers, "spare")},
                    policy=router.policy, matrix_receipt=router.matrix,
                    approval=router.proof, trust=router.trust)

    def load(self, config):
        path = self.root / "model-config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        # Only transport construction is replaced. Policy compilation, signature,
        # journal bindings, expiry and version admission use production code.
        def construct(active, *, secret_store):
            return {name: routing_fixtures.FakeProvider(row["model"]) for name, row in active["models"].items()}
        with patch("lightyear_factory.model_config.configured_models", side_effect=construct):
            return load_router(path, secret_store=Mock())

    def test_valid_policy_loads_only_default_and_named_routes(self):
        router = self.load(self.config())
        self.assertEqual({"default", "primary", "fallback"}, set(router.providers))
        self.assertTrue(all(p.calls == 0 for p in router.providers.values()))

    def test_missing_proof_tampered_policy_and_changed_version_load_only_default(self):
        original = self.config()
        for change in ("proof", "policy", "version"):
            with self.subTest(change=change):
                config = copy.deepcopy(original)
                if change == "proof":
                    config["approval"] = None
                elif change == "policy":
                    config["policy"]["routes"]["plan"]["primary"] = "spare"
                else:
                    config["models"]["primary"]["model"] = "different-snapshot"
                router = self.load(config)
                self.assertEqual({"default"}, set(router.providers))

    def test_expired_policy_does_not_load_alternatives(self):
        config = self.config()
        with patch("lightyear_factory.routing.datetime", wraps=datetime) as clock:
            clock.now.return_value = self.now + timedelta(days=11)
            router = self.load(config)
        self.assertEqual({"default"}, set(router.providers))

