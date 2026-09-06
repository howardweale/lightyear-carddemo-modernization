"""Execute the shared CloudBank business contract against running services.

The runtime adapter performs I/O; this module owns business assertions. An HTTP
200, an accepted queue write, or a restart command alone cannot pass a journey.
This evidence has its own type: it is not an MS65, MS66 or MS67 execution receipt.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.parse import quote, urlencode, urlsplit

from .cloudbank_whole_application_equivalence import SCENARIOS, SERVICES, journey_contract
from .contracts import canonical_bytes, sign

OBSERVATION_TYPE = "lightyear-cloudbank-shared-journey-execution"
ACK = "I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS"
OWNER_SCOPES = "cloudbank.read cloudbank.write cloudbank.transfer"
ROLE_SCOPES = {"owner": OWNER_SCOPES, "account": "cloudbank.internal",
               "test": "cloudbank.test", "credit": "cloudbank.read", "chat": "cloudbank.read"}


class JourneyFailure(Exception):
    """A bounded reason code, never a raw HTTP/SQL/credential exception."""

    def __init__(self, code: str):
        super().__init__(code if re.fullmatch(r"[a-z0-9-]{1,100}", code) else "journey-failed")


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
    def start(self, service: str) -> None: ...
    def crash_stopped(self, service: str) -> None: ...
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


class Journeys:
    def __init__(self, runtime: Runtime, run_id: str, *, timeout: float = 180,
                 pause: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        require(bool(re.fullmatch(r"[a-z0-9-]{1,60}", run_id)), "run-id-invalid")
        self.runtime, self.run_id = runtime, run_id
        self.timeout, self.pause, self.clock = timeout, pause, clock
        self.accounts: list[int] = []
        self.marker = "lightyear-synthetic-journey:" + run_id
        self.deposit_journal: int | None = None
        self.deposit_id = self.message_id("deposit")
        self.clear_id = self.message_id("clearance")
        self.last_queue_observation: dict | None = None

    def message_id(self, suffix: str) -> str:
        return "ly-" + hashlib.sha256(f"{self.run_id}:{suffix}".encode()).hexdigest()[:48]

    def wait(self, read: Callable[[], Any], predicate: Callable[[Any], bool], code: str):
        deadline = self.clock() + self.timeout
        while True:
            value = read()
            if predicate(value):
                return value
            require(self.clock() < deadline, code)
            self.pause(1)

    def customer(self) -> dict:
        owner = self.runtime.owner
        require(bool(re.fullmatch(r"[a-zA-Z0-9_-]{1,20}", owner)), "synthetic-owner-id-invalid")
        path = "/api/v1/customer/" + quote(owner, safe="")
        current = self.runtime.request("customer", "GET", path, "owner")
        if current.status == 404:
            created = self.runtime.request("customer", "POST", "/api/v1/customer", "owner", {
                "customerId": owner, "customerName": "LIGHTYEAR synthetic journey",
                "customerEmail": "journey@example.invalid",
                "customerOtherDetails": "lightyear-synthetic-journey-owner"})
            require(created.status == 201, "synthetic-customer-create-failed")
            current = self.runtime.request("customer", "GET", path, "owner")
        require(current.status == 200, "customer-owner-read-failed")
        row = current.json()
        require(isinstance(row, dict) and row.get("customerId") == owner,
                "customer-owner-identity-mismatch")
        # Never reuse an existing unmarked customer for mutations.
        require(row.get("customerOtherDetails") == "lightyear-synthetic-journey-owner",
                "existing-customer-is-not-a-journey-fixture")
        visible = self.runtime.request("customer", "GET", "/api/v1/customer", "owner")
        require(visible.status == 200, "customer-owner-list-failed")
        rows = visible.json()
        require(isinstance(rows, list) and len(rows) == 1
                and rows[0].get("customerId") == owner, "customer-owner-list-leaks-other-owner")
        return {"owner_visible": True, "visible_customer_count": 1}

    def prepare_accounts(self) -> dict:
        for index, balance in enumerate((1000, 250, 5)):
            response = self.runtime.request("account", "POST", "/api/v1/account", "account", {
                "accountId": 0, "accountName": f"LIGHTYEAR journey {index}", "accountType": "CH",
                "accountCustomerId": self.runtime.owner, "accountOtherDetails": self.marker,
                "accountBalance": balance})
            require(response.status == 201, "synthetic-account-create-failed")
            location = urlsplit(response.headers.get("location", "")).path
            match = re.fullmatch(r"/api/v1/account/([0-9]+)", location)
            require(match is not None, "synthetic-account-location-invalid")
            account_id = int(match.group(1))
            require(account_id > 0 and account_id not in self.accounts, "synthetic-account-id-invalid")
            self.accounts.append(account_id)
        state = self.state()
        require(state["balances"] == [1000, 250, 5] and state["journals"] == [],
                "synthetic-account-initial-state-invalid")
        return {"fixture_account_count": 3, "state_sha256": hashed(state)}

    def state(self) -> dict:
        require(len(self.accounts) == 3, "synthetic-account-fixture-incomplete")
        balances, journals = [], []
        for index, account_id in enumerate(self.accounts):
            response = self.runtime.request("account", "GET", f"/api/v1/account/{account_id}", "account")
            require(response.status == 200, "account-state-read-failed")
            row = response.json()
            require(isinstance(row, dict) and row.get("accountId") == account_id
                    and row.get("accountCustomerId") == self.runtime.owner
                    and row.get("accountOtherDetails") == self.marker, "account-fixture-identity-mismatch")
            balances.append(integer(row.get("accountBalance"), "account-balance-invalid"))
            response = self.runtime.request("account", "GET", f"/api/v1/account/{account_id}/journal", "account")
            require(response.status == 200, "journal-state-read-failed")
            rows = response.json()
            require(isinstance(rows, list) and len(rows) <= 200, "journal-state-shape-invalid")
            for item in rows:
                require(isinstance(item, dict) and item.get("accountId") == account_id,
                        "journal-account-identity-mismatch")
                kind = item.get("journalType")
                require(kind in {"WITHDRAW", "DEPOSIT", "PENDING"}, "journal-kind-invalid")
                journals.append({"account": index, "id": integer(item.get("journalId"), "journal-id-invalid"),
                    "type": kind, "amount": integer(item.get("journalAmount"), "journal-amount-invalid")})
        return {"balances": balances, "journals": sorted(journals, key=lambda row: (row["account"], row["id"]))}

    def transfer(self, source: int, target: int, amount: int, key: str, role: str | None = "owner") -> Response:
        query = urlencode({"fromAccount": self.accounts[source], "toAccount": self.accounts[target], "amount": amount})
        return self.runtime.request("transfer", "POST", "/transfer?" + query, role,
                                    headers={"Idempotency-Key": self.message_id(key)})

    def assert_transfer(self, before: dict, after: dict, source: int, target: int, amount: int) -> None:
        expected = list(before["balances"])
        expected[source] -= amount
        expected[target] += amount
        require(after["balances"] == expected, "transfer-balance-delta-invalid")
        prior = {row["id"] for row in before["journals"]}
        additions = [row for row in after["journals"] if row["id"] not in prior]
        require([row for row in after["journals"] if row["id"] in prior] == before["journals"],
                "transfer-mutated-prior-journal")
        require(sorted((r["account"], r["type"], r["amount"]) for r in additions)
                == sorted([(source, "WITHDRAW", amount), (target, "DEPOSIT", amount)]),
                "transfer-journal-delta-invalid")

    def unauthenticated(self) -> dict:
        # Run before creating fixture accounts; this request cannot mutate a
        # record if the service correctly enforces the external bearer boundary.
        response = self.runtime.request("customer", "GET", "/api/v1/customer", None)
        require(response.status == 401, "unauthenticated-request-not-rejected")
        return {"http_status": 401}

    def success(self, key="transfer-success", amount=25) -> dict:
        before = self.state()
        response = self.transfer(0, 1, amount, key)
        require(response.status == 200, "transfer-http-failed")
        after = self.state()
        self.assert_transfer(before, after, 0, 1, amount)
        return {"http_status": response.status, "before_sha256": hashed(before), "after_sha256": hashed(after)}

    def invalid(self) -> dict:
        before = self.state()
        response = self.transfer(0, 1, 0, "invalid")
        require(response.status == 400 and self.state() == before, "invalid-transfer-mutated-or-not-rejected")
        return {"http_status": 400, "unchanged_state_sha256": hashed(before)}

    def insufficient(self) -> dict:
        before = self.state()
        response = self.transfer(2, 0, before["balances"][2] + 1, "insufficient")
        # A 500 or timeout never qualifies as a business rejection.
        require(response.status in {400, 409, 422}, "insufficient-funds-not-business-rejection")
        require(self.state() == before, "insufficient-funds-mutated-state")
        return {"http_status": response.status, "unchanged_state_sha256": hashed(before)}

    def enqueue(self, message: str, *, journal: int | None = None, amount=30) -> Response:
        path = "/api/v1/testrunner/deposit" if journal is None else "/api/v1/testrunner/clear"
        body = {"accountId": self.accounts[0], "amount": amount} if journal is None else {"journalId": journal}
        return self.runtime.request("testrunner", "POST", path, "test", body, {"Idempotency-Key": message})

    def delivered(self, message: str, phase: str) -> dict:
        row = self.wait(lambda: self.runtime.queue(message), lambda r: r.get("state") in {"PROCESSED", "DEAD"},
                        "queue-delivery-timeout")
        self.last_queue_observation = {"phase": phase, "message_id_sha256": hashed(message),
            "state": row.get("state"), "attempts": row.get("attempts"), "error_code": row.get("error_code")}
        require(row.get("state") == "PROCESSED", "queue-message-dead-lettered")
        return row

    def assert_deposit(self, before: dict, after: dict, amount: int) -> int:
        # CloudBank models an uncleared check as a PENDING journal. Available
        # account balance must stay unchanged until the declared settlement path.
        require(after["balances"] == before["balances"], "pending-check-mutated-balance")
        prior = {row["id"] for row in before["journals"]}
        additions = [row for row in after["journals"] if row["id"] not in prior]
        require([row for row in after["journals"] if row["id"] in prior] == before["journals"],
                "check-mutated-prior-journal")
        require(len(additions) == 1 and additions[0]["account"] == 0
                and additions[0]["type"] == "PENDING" and additions[0]["amount"] == amount,
                "check-deposit-not-applied-once")
        return additions[0]["id"]

    def deposit(self) -> dict:
        before = self.state()
        response = self.enqueue(self.deposit_id)
        require(response.status == 201, "check-deposit-enqueue-failed")
        queue = self.delivered(self.deposit_id, "deposit")
        after = self.state()
        self.deposit_journal = self.assert_deposit(before, after, 30)
        return {"queue": queue, "before_sha256": hashed(before), "after_sha256": hashed(after)}

    def clearance(self) -> dict:
        require(self.deposit_journal is not None, "check-deposit-journal-missing")
        before = self.state()
        response = self.enqueue(self.clear_id, journal=self.deposit_journal)
        require(response.status == 201, "check-clearance-enqueue-failed")
        queue = self.delivered(self.clear_id, "clearance")
        expected = json.loads(json.dumps(before))
        for row in expected["journals"]:
            if row["id"] == self.deposit_journal:
                row["type"] = "DEPOSIT"
        after = self.state()
        require(after == expected, "check-clearance-state-invalid")
        # Replay must not cause a second journal effect.
        require(self.enqueue(self.clear_id, journal=self.deposit_journal).status == 200,
                "check-clearance-replay-not-suppressed")
        self.delivered(self.clear_id, "clearance-replay")
        require(self.state() == after, "check-clearance-replay-mutated-state")
        return {"queue": queue, "after_sha256": hashed(after), "replay_unchanged": True}

    def duplicate(self) -> dict:
        before = self.state()
        response = self.enqueue(self.deposit_id)
        require(response.status == 200, "duplicate-message-not-suppressed")
        queue = self.delivered(self.deposit_id, "deposit-replay")
        require(self.state() == before, "duplicate-message-mutated-state")
        return {"queue": queue, "unchanged_state_sha256": hashed(before)}

    def credit(self) -> dict:
        response = self.runtime.request("creditscore", "GET", "/api/v1/creditscore", "credit")
        require(response.status == 200, "credit-score-request-failed")
        payload = response.json()
        require(isinstance(payload, dict) and re.fullmatch(r"[0-9]{3}", str(payload.get("Credit Score", ""))) is not None,
                "credit-score-contract-invalid")
        require(500 <= int(payload["Credit Score"]) <= 899, "credit-score-outside-declared-range")
        return {"http_status": 200, "score_in_declared_range": True}

    def chat(self) -> dict:
        response = self.runtime.request("chatbot", "POST", "/chat", "chat", "What is a checking account?")
        require(response.status == 200, "chatbot-request-failed")
        try:
            text = response.body.decode("utf-8")
        except UnicodeError:
            raise JourneyFailure("chatbot-response-encoding-invalid") from None
        require(0 < len(text.strip()) <= 4000, "chatbot-response-length-invalid")
        require(re.search(r"(?i)(BEGIN (RSA )?PRIVATE KEY|authorization\s*:\s*bearer|"
                          r"(?:password|token|secret|api[_ -]?key)\s*[:=]\s*\S+)", text) is None,
                "chatbot-response-policy-failed")
        # Never persist the prompt, response or their hashes.
        return {"http_status": 200, "bounded_response": True, "response_characters": len(text)}

    def account_restart(self) -> dict:
        before = self.state()
        self.runtime.restart("account")
        require(self.state() == before, "account-restart-lost-state")
        return {"unchanged_state_sha256": hashed(before)}

    def checks_restart(self) -> dict:
        message = self.message_id("inflight")
        before = self.state()
        stopped = False
        try:
            # The adapter routes only Checks' delivery connection to a bounded
            # unavailable TEST-NET endpoint. A persisted PROCESSING state must
            # be seen before stopping the consumer; we never manufacture leases.
            self.runtime.block_checks_delivery()
            require(self.enqueue(message, amount=7).status == 201, "inflight-enqueue-failed")
            processing = self.wait(lambda: self.runtime.queue(message), lambda r: r.get("state") == "PROCESSING",
                                   "inflight-claim-not-observed")
            require(integer(processing.get("attempts"), "queue-attempts-invalid") >= 1,
                    "inflight-claim-not-observed")
            self.runtime.stop("checks")
            stopped = True
            self.runtime.crash_stopped("checks")
            self.runtime.restore_checks_delivery()
            self.runtime.start("checks")
            stopped = False
            completed = self.delivered(message, "inflight-redelivery")
            require(completed.get("attempts", 0) > processing["attempts"], "inflight-redelivery-not-observed")
            after = self.state()
            self.assert_deposit(before, after, 7)
            return {"claimed": processing, "redelivered": completed,
                    "before_sha256": hashed(before), "after_sha256": hashed(after)}
        finally:
            # Adapter also journals restoration intent before each scale-down;
            # its close() retries if this immediate recovery fails.
            self.runtime.restore_checks_delivery()
            if stopped:
                self.runtime.start("checks")

    def dependency(self) -> dict:
        before = self.state()
        self.runtime.stop("account")
        try:
            try:
                response = self.transfer(0, 1, 3, "dependency-failure")
                require(500 <= response.status <= 599, "dependency-failure-not-observed")
            except JourneyFailure as exc:
                if str(exc) != "http-transport-failed":
                    raise
        finally:
            self.runtime.start("account")
        require(self.state() == before, "dependency-failure-mutated-state")
        self.runtime.restart("transfer")
        return self.success("dependency-recovered", 3)

    def concurrent(self) -> dict:
        before = self.state()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.transfer, 0, 1, 5, "concurrent-forward")
            second = pool.submit(self.transfer, 1, 0, 5, "concurrent-reverse")
            responses = [first.result(), second.result()]
        require(all(response.status == 200 for response in responses), "concurrent-transfer-request-failed")
        after = self.state()
        require(after["balances"] == before["balances"], "concurrent-transfer-conservation-failed")
        prior = {row["id"] for row in before["journals"]}
        require([r for r in after["journals"] if r["id"] in prior] == before["journals"],
                "concurrent-transfer-mutated-prior-journal")
        additions = [r for r in after["journals"] if r["id"] not in prior]
        require(sorted((r["account"], r["type"], r["amount"]) for r in additions)
                == [(0, "DEPOSIT", 5), (0, "WITHDRAW", 5), (1, "DEPOSIT", 5), (1, "WITHDRAW", 5)],
                "concurrent-transfer-journal-invalid")
        return {"before_sha256": hashed(before), "after_sha256": hashed(after), "concurrent_requests": 2}

    def full_restart(self) -> dict:
        before = self.state()
        self.runtime.restart_all()
        self.runtime.authorize()  # Obtain fresh credentials through the live issuer.
        require(self.state() == before, "full-stack-restart-lost-state")
        self.customer()
        result = self.success("full-stack-recovered", 2)
        result["credit"] = self.credit()
        result["chat"] = self.chat()
        result["services"] = self.runtime.ready()
        return result

    def operations(self):
        return [self.runtime.ready, self.runtime.authorize, self.unauthenticated,
                self.customer, self.prepare_accounts, self.success, self.invalid,
                self.insufficient, self.deposit, self.clearance, self.duplicate,
                self.credit, self.chat, self.account_restart, self.checks_restart,
                self.dependency, self.concurrent, self.full_restart]


def execute_journeys(runtime: Runtime, bindings: dict, key: str, signer: str, *,
                     run_id: str | None = None, progress: Callable[[str], None] = lambda _: None,
                     checkpoint: Callable[[dict], None] = lambda _: None,
                     timeout: float = 180, pause=time.sleep, clock=time.monotonic) -> dict:
    require(bool(key and signer.strip()), "journey-signing-identity-required")
    run_id = run_id or "journeys-" + uuid.uuid4().hex
    driver = Journeys(runtime, run_id, timeout=timeout, pause=pause, clock=clock)
    result = {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE,
              "run_id": run_id, "bindings": {**bindings, "journey_contract_sha256": journey_contract()["content_sha256"]},
              "status": "running", "scenarios": [], "started_at_unix": int(time.time()),
              "synthetic_data_only": True, "raw_output_persisted": False, "credentials_persisted": False,
              "production_environment": False, "whole_application_equivalent": False,
              "ms65_complete": False, "ms66_complete": False, "ms67_complete": False}
    failure = False
    try:
        for (identifier, normalized), operation in zip(SCENARIOS, driver.operations(), strict=True):
            if failure:
                result["scenarios"].append({"id": identifier, "status": "not-run", "reason": "prior-journey-failed"})
                continue
            progress(identifier)
            try:
                evidence = operation()
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
        for identifier, _ in SCENARIOS:
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
