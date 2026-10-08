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
                "configure model identifiers and environment credentials only"
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
        from .model_versions import require_snapshot
        require_snapshot(c["model"])
        from .provider_secrets import NAMES
        name=NAMES[c['provider']]
        key=secret_store.read(name) if secret_store is not None else os.environ.get(name,'')
        if not key:raise ValueError('provider credential unavailable')
        if c["provider"] == "openai":
            p = SnapshotOpenAIResponsesProvider(
                key,
                model=c["model"],
                max_retries=0,
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
