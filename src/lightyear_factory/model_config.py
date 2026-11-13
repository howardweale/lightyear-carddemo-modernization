"""Load host configuration; use scoped broker leases in hardened execution."""

import json
import math
import os
from pathlib import Path
from .model_versions import SnapshotOpenAIResponsesProvider
from .additional_providers import AnthropicMessagesProvider, GeminiProvider
from .routing import TaskRouter


def configured_models(config, *, secret_store=None):
    providers = {}
    for identifier, c in config["models"].items():
        if not c.get("model") or any(k in c for k in ("api_key", "token", "password")):
            raise ValueError(
                "configure model identifiers and scoped credential broker only"
            )
        prices = {
            k: c[k]
            for k in (
                "input_usd_per_million",
                "output_usd_per_million",
                "max_output_tokens",
            )
        }
        if (
            any(
                not math.isfinite(prices[k]) or prices[k] <= 0
                for k in ("input_usd_per_million", "output_usd_per_million")
            )
            or type(prices["max_output_tokens"]) is not int
            or not 1 <= prices["max_output_tokens"] <= 65536
        ):
            raise ValueError("finite positive prices and output token cap required")
        explicit_billing = {}
        if 'service_tier' in c or 'billing_policy' in c:
            if (c['provider'] != 'openai' or
                    set(c).intersection({'service_tier', 'billing_policy'}) != {'service_tier', 'billing_policy'}):
                raise ValueError('explicit tier and billing policy require the OpenAI provider and both fields')
            from .flex_billing import validate_flex_billing
            # Reject invalid bindings before requesting a credential lease.
            bound_policy = validate_flex_billing(c['billing_policy'], model=c['model'],
                input_price=prices['input_usd_per_million'], output_price=prices['output_usd_per_million'],
                token_preflight=True, max_retries=0, service_tier=c['service_tier'])
            explicit_billing = dict(service_tier='flex', billing_policy=bound_policy)
        from .model_versions import require_snapshot
        require_snapshot(c["model"])
        from .provider_secrets import NAMES
        name=NAMES[c['provider']]
        if secret_store is None:raise ValueError('scoped credential broker required')
        key=secret_store.read(name)
        if not key:raise ValueError('provider credential unavailable')
        if c["provider"] == "openai":
            p = SnapshotOpenAIResponsesProvider(
                key,
                model=c["model"],
                max_retries=0,
                **explicit_billing,
                **prices,
            )
            p.manage_failure_budget = True
        else:
            cls = {"anthropic": AnthropicMessagesProvider, "gemini": GeminiProvider}[
                c["provider"]
            ]
            p = cls(c["model"], api_key=key, **prices)
        p.require_snapshot_response=True
        providers[identifier] = p
    return providers


def load_router(path, *, secret_store=None):
    c = json.loads(Path(path).read_bytes())
    return TaskRouter(
        configured_models(c,secret_store=secret_store),
        c["default"],
        policy=c.get("policy"),
        matrix=c.get("matrix_receipt"),
        proof=c.get("approval"),
        trust=c.get("trust"),
    )
