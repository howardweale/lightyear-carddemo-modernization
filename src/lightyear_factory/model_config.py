"""Load host configuration; use scoped broker leases in hardened execution."""

import json
import math
import os
from pathlib import Path
from .model_versions import SnapshotOpenAIResponsesProvider
from .additional_providers import AnthropicMessagesProvider, GeminiProvider
from .routing import TaskRouter, admitted_policy


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
    if c["default"] not in c["models"]:
        raise ValueError("default model not configured")
    admitted = admitted_policy(
        c.get("policy"), c.get("matrix_receipt"), c.get("approval"), c.get("trust"),
        versions={identifier: row.get("model") for identifier, row in c["models"].items()},
    )
    # Approval precedes credential leases, not merely the first model call.
    # Per-call routing admission still checks expiry, evidence and versions.
    selected = {c["default"]}
    if admitted is not None:
        for route in admitted["policy"]["routes"].values():
            selected.add(route["primary"])
            if route.get("fallback"):
                selected.add(route["fallback"])
    active = {**c, "models": {k: v for k, v in c["models"].items() if k in selected}}
    return TaskRouter(
        configured_models(active,secret_store=secret_store),
        c["default"],
        policy=c.get("policy"),
        matrix=c.get("matrix_receipt"),
        proof=c.get("approval"),
        trust=c.get("trust"),
    )
