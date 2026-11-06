"""Admit optional routing credentials before constructing configured providers."""

import json
from pathlib import Path

from .model_config import configured_models
from .routing import TaskRouter, admitted_policy


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
