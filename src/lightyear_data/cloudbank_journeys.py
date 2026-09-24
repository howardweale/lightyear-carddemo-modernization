"""Execute the shared CloudBank business contract against running services.

The runtime adapter performs I/O; this module owns business assertions. An HTTP
200, an accepted queue write, or a restart command alone cannot pass a journey.
This evidence has its own type: it is not an MS65, MS66 or MS67 execution receipt.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .cloudbank_whole_application_equivalence import SCENARIOS, SERVICES, journey_contract
from .contracts import canonical_bytes, sign
from .service_journeys import cloudbank_pack, target_lane
from lightyear_workflow.service_pack import JourneyFailure, Runner

OBSERVATION_TYPE = "lightyear-cloudbank-shared-journey-execution"
ACK = "I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS"
OWNER_SCOPES = "cloudbank.read cloudbank.write cloudbank.transfer"
ROLE_SCOPES = {"owner": OWNER_SCOPES, "account": "cloudbank.internal",
               "test": "cloudbank.test", "credit": "cloudbank.read", "chat": "cloudbank.read"}


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self):
        try:
            return json.loads(self.body)
        except (ValueError, UnicodeError):
            raise JourneyFailure("response-json-invalid") from None


class Runtime(Protocol):
    owner: str

    def ready(self) -> dict: ...
    def authorize(self) -> dict: ...
    def request(self, service: str, method: str, path: str, role: str | None,
                body: Any = None, headers: dict | None = None) -> Response: ...
    def queue(self, message_id: str) -> dict: ...
    def stop(self, service: str) -> None: ...
    def start(self, service: str) -> dict: ...
    def crash_stop(self, service: str) -> dict: ...
    def block_checks_delivery(self) -> None: ...
    def restore_checks_delivery(self) -> None: ...
    def restart(self, service: str) -> None: ...
    def restart_all(self) -> None: ...
    def close(self) -> dict: ...


def require(condition: bool, code: str) -> None:
    if not condition:
        raise JourneyFailure(code)


def integer(value: Any, code: str) -> int:
    require(type(value) is int, code)
    return value


def hashed(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class _CloudBankRunner(Runner):
    """Keep the existing gate entry points patchable for qualification tests."""
    def call(self, name, args=None):
        result = getattr(self.driver, name)(**(args or {}))
        if isinstance(result, Response):
            return {"status": result.status, "body": result.body, "headers": result.headers}
        return result


class Journeys:
    """Compatibility facade. All sequences and business assertions live in JSON."""
    def __init__(self, runtime: Runtime, run_id: str, *, timeout=180,
                 pause=time.sleep, clock=time.monotonic, pack=None):
        require(bool(re.fullmatch(r"[a-z0-9-]{1,60}", run_id)), "run-id-invalid")
        require(bool(re.fullmatch(r"[a-zA-Z0-9_-]{1,20}", runtime.owner)), "synthetic-owner-id-invalid")
        self.runtime, self.run_id = runtime, run_id
        self.pack = pack or cloudbank_pack()
        # Global controls in this adapter cover the fixed eight-service estate.
        # A declaration cannot narrow their footprint by omitting a service.
        require(self.pack.raw["services"] == list(SERVICES), "journey-service-scope-invalid")
        self.runner = _CloudBankRunner(self.pack, target_lane(runtime),
            {"owner": runtime.owner, "run_id": run_id}, timeout=timeout, pause=pause, clock=clock)
        self.runner.driver = self

    @property
    def accounts(self): return self.runner.state["accounts"]

    @accounts.setter
    def accounts(self, value): self.runner.state["accounts"] = list(value)

    @property
    def last_queue_observation(self): return self.runner.state["last_queue_observation"]


def _entrypoint(name):
    def run(self, *args, **kwargs):
        macro = self.runner.raw["macros"][name]
        if len(args) > len(macro["params"]):
            raise TypeError("too many macro arguments")
        positional = dict(zip(macro["params"], args))
        if positional.keys() & kwargs.keys():
            raise TypeError("duplicate macro argument")
        values = {**self.runner.value(macro.get("defaults", {}), {}), **positional, **kwargs}
        result = Runner.call(self.runner, name, values)
        if isinstance(result, dict) and set(result) == {"status", "body", "headers"} and isinstance(result["body"], bytes):
            return Response(**result)
        return result
    run.__name__ = name
    run.__doc__ = "Execute the validated reference-pack macro " + name
    return run


# Compatibility names come from the same declaration as execution and planning.
# There is no hand-maintained scenario-to-method list.
for _name in cloudbank_pack().raw["macros"]:
    setattr(Journeys, _name, _entrypoint(_name))


def _state_property(name):
    return property(lambda self: self.runner.state[name],
                    lambda self, value: self.runner.state.__setitem__(name, value))


for _name in cloudbank_pack().raw["state"]:
    if not hasattr(Journeys, _name):
        setattr(Journeys, _name, _state_property(_name))


def execute_journeys(runtime: Runtime, bindings: dict, key: str, signer: str, *,
                     run_id: str | None = None, progress: Callable[[str], None] = lambda _: None,
                     checkpoint: Callable[[dict], None] = lambda _: None,
                     timeout: float = 180, pause=time.sleep, clock=time.monotonic) -> dict:
    require(bool(key and signer.strip()), "journey-signing-identity-required")
    run_id = run_id or "journeys-" + uuid.uuid4().hex
    driver = Journeys(runtime, run_id, timeout=timeout, pause=pause, clock=clock)
    result = {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE,
              "run_id": run_id, "bindings": {**bindings, "journey_contract_sha256": journey_contract()["content_sha256"],
              "journey_pack_sha256": driver.pack.sha256},
              "status": "running", "scenarios": [], "started_at_unix": int(time.time()),
              "synthetic_data_only": True, "raw_output_persisted": False, "credentials_persisted": False,
              "production_environment": False, "whole_application_equivalent": False,
              "ms65_complete": False, "ms66_complete": False, "ms67_complete": False}
    failure = False
    try:
        for journey in driver.pack.journeys:
            identifier, normalized = journey["id"], journey["normalized_result"]
            if failure:
                result["scenarios"].append({"id": identifier, "status": "not-run", "reason": "prior-journey-failed"})
                continue
            progress(identifier)
            try:
                evidence = driver.runner.journey(identifier)
                result["scenarios"].append({"id": identifier, "status": "passed", "normalized_result": normalized,
                    "evidence": evidence, "evidence_sha256": hashed(evidence)})
            except Exception as exc:
                code = str(exc) if isinstance(exc, JourneyFailure) else "unexpected-runtime-error"
                result["scenarios"].append({"id": identifier, "status": "failed", "reason": code})
                failure = True
            checkpoint(result)
    except KeyboardInterrupt:
        failure = True
        result["interrupted"] = True
    except Exception:
        failure = True
        result["reason"] = "execution-or-checkpoint-failed"
    finally:
        try:
            result["recovery"] = runtime.close()
            if result["recovery"].get("status") != "restored":
                failure = True
        except Exception:
            result["recovery"] = {"status": "failed", "reason": "runtime-restoration-failed"}
            failure = True
        existing = {row["id"] for row in result["scenarios"]}
        for journey in driver.pack.journeys:
            identifier = journey["id"]
            if identifier not in existing:
                result["scenarios"].append({"id": identifier, "status": "not-run", "reason": "run-interrupted"})
        result["status"] = "failed" if failure else "passed-shared-journeys"
        result["finished_at_unix"] = int(time.time())
        result["scenario_count"] = len(result["scenarios"])
        result["fixture_account_ids"] = driver.accounts
        result["fixture_records_retained"] = True
        result = sign(result, key, signer)
        checkpoint(result)
    return result
