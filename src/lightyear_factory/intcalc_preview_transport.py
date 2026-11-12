"""Inactive C2 transport/accounting seam. No CLI, admission, or credential discovery.

Trusted composition must verify admission, operator spend/billing authority,
public context and the pre-count bound before supplying these inputs. This module
does not authenticate the operator or qualify the runtime. Never a P5 route.
"""
from dataclasses import dataclass
import hashlib
import http.client
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import stat
import sys
import threading
import time

MODEL = "gpt-5.4-2026-03-05"
ROLES = ("planner", "builder-attempt1", "analysis-attempt1", "builder-repair1", "analysis-attempt2")
SLOT_HOLD = 1_892_000  # integer microdollars; count 550000 + generation 1342000
RUN_CAP = 9_460_000
MAX_BODY = 2 * 1024 * 1024
MAX_RESPONSE = 4 * 1024 * 1024
COUNT_PATH = "/v1/responses/input_tokens"
GENERATION_PATH = "/v1/responses"


class TransportRefused(ValueError):
    """Fixed diagnostic only; never expose credentials, body or provider error text."""


def require(ok, code):
    if not ok:
        raise TransportRefused(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def hash_value(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def integer(value, cap, code):
    require(type(value) is int and 0 <= value <= cap, code)
    return value


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate-json-key")
            result[key] = value
        return result
    def reject(_):
        raise TransportRefused("float-or-nonfinite-json")
    try:
        require(type(raw) is bytes and len(raw) <= MAX_RESPONSE, "response-size")
        return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                          parse_float=reject, parse_constant=reject)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise TransportRefused("invalid-response-json") from None


def persist(fd):
    require(os.name == "posix", "posix-required")
    if sys.platform == "darwin":
        import fcntl
        require(hasattr(fcntl, "F_FULLFSYNC"), "fullfsync-unavailable")
        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    else:
        os.fsync(fd)


class ExclusiveRunLedger:
    """Fresh owner-only directory; immutable O_EXCL records; no resume or refund.

    Parent must be controller-owned, outside model/candidate roots. Dirfd pins the
    checked directory. A partial/uncertain record consumes the slot permanently.
    A recreated transport may not attach to an old run directory.
    """
    def __init__(self, parent, run_id):
        require(os.name == "posix", "posix-required")
        require(hash_value(run_id), "run-id")
        self._pid = os.getpid()
        self._fd = None
        parent_fd = None
        try:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            path = Path(parent).absolute()
            for item in (path, *path.parents):
                require(not stat.S_ISLNK(item.lstat().st_mode), "linked-ledger-parent")
            parent_fd = os.open(path, flags)
            info = os.fstat(parent_fd)
            require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0,
                    "ledger-owner-mode")
            os.mkdir(run_id, 0o700, dir_fd=parent_fd)
            self._fd = os.open(run_id, flags, dir_fd=parent_fd)
            persist(self._fd)
            persist(parent_fd)
        except (OSError, TransportRefused):
            self.close()
            raise TransportRefused("ledger-exclusive-or-durability-fault") from None
        finally:
            if parent_fd is not None:
                os.close(parent_fd)

    def record_once(self, name, value):
        require(self._pid == os.getpid() and self._fd is not None, "ledger-process-changed")
        require(re.fullmatch(r"[a-z0-9-]+\.json", name) is not None, "ledger-record-name")
        fd = None
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=self._fd)
            raw = canonical(value) + b"\n"
            require(os.write(fd, raw) == len(raw), "ledger-short-write")
            persist(fd)
            persist(self._fd)
        except (OSError, TransportRefused):
            raise TransportRefused("ledger-consumed-or-uncertain") from None
        finally:
            if fd is not None:
                os.close(fd)

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


def https_once(path, body, key, timeout):
    """One stdlib HTTP request, no SDK/proxy/redirect/retry adapter."""
    require(path in (COUNT_PATH, GENERATION_PATH), "endpoint-not-allowed")
    connection = http.client.HTTPSConnection("api.openai.com", timeout=timeout)
    try:
        connection.request("POST", path, body=body, headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            "Accept": "application/json", "Connection": "close"})
        response = connection.getresponse()
        raw = response.read(MAX_RESPONSE + 1)
        require(len(raw) <= MAX_RESPONSE, "response-size")
        return response.status, raw
    finally:
        connection.close()


def _wire_worker(pipe, path, body, key, timeout):
    try:
        status, raw = https_once(path, body, key, timeout)
        pipe.send_bytes(status.to_bytes(2, "big") + raw)
    except BaseException:
        # No exception text crosses into retained evidence or model feedback.
        try:
            pipe.send_bytes(b"\x00\x00")
        except (BrokenPipeError, OSError):
            pass
    finally:
        pipe.close()


class DeadlineWire:
    """Spawned single-shot worker makes DNS/TLS/write/read killable as a whole.

    No shell or child code from the model. Secret exists only in controller/worker
    memory, never argv/environment/file/receipt. Failed or uncertain send is final.
    Parent parsing also checks the same phase deadline. Five seconds of reaping
    is reserved inside the absolute call/run budget, never added afterward.
    """
    max_retries = token_count_retries = sdk_max_retries = 0

    def __init__(self, clock=time.monotonic, context=None, worker_target=_wire_worker):
        self.clock = clock
        self.context = context or multiprocessing.get_context("spawn")
        # Trusted dependency injection for socket-free spawn tests; never candidate input.
        self.worker_target = worker_target

    def post_once(self, path, body, key, end):
        remaining = end - self.clock()
        require(remaining > 5, "phase-deadline")
        parent, child = self.context.Pipe(duplex=False)
        worker = self.context.Process(target=self.worker_target, args=(child, path, body, key, remaining-5))
        worker.daemon = True
        started = False
        watchdog = None
        try:
            worker.start()
            started = True
            child.close()
            # A pipe can become readable after only its frame header. Kill the
            # writer at the same deadline so recv_bytes cannot wait indefinitely
            # for a partial body from a stuck worker.
            def abort_worker():
                if worker.is_alive():
                    worker.kill()
            watchdog = threading.Timer(max(0, end-self.clock()-5), abort_worker)
            watchdog.daemon = True
            watchdog.start()
            require(parent.poll(max(0, end-self.clock()-5)), "wire-absolute-timeout")
            message = parent.recv_bytes(MAX_RESPONSE + 2)
            require(len(message) >= 2, "wire-response")
            require(self.clock() < end-5, "wire-absolute-timeout")
            status = int.from_bytes(message[:2], "big")
            require(status != 0, "wire-send-uncertain")
            return status, message[2:]
        except (EOFError, OSError):
            raise TransportRefused("wire-send-uncertain") from None
        finally:
            if watchdog is not None:
                watchdog.cancel()
                watchdog.join()
            child.close()
            parent.close()
            if started:
                if worker.is_alive():
                    worker.terminate()
                worker.join(timeout=max(0, min(1, end-self.clock())))
                if worker.is_alive():
                    worker.kill()
                    worker.join(timeout=max(0, end-self.clock()))
                require(not worker.is_alive(), "wire-cleanup-unconfirmed")
                worker.close()
            require(self.clock() <= end, "phase-deadline")


@dataclass(frozen=True)
class ReviewedRequest:
    """Controller-only result of separately reviewed context/bound verification.

    Hash presence is not approval: composition must authenticate these receipts
    and independently compute the conservative token bound before constructing.
    No tokenizer guess or byte-length-as-token-count fallback exists here.
    """
    projection: dict
    projection_sha256: str
    token_upper_bound: int
    bound_proof_sha256: str
    public_context_approval_sha256: str


@dataclass(frozen=True)
class ReviewedSpend:
    """Supplied only after exact Howard spend/billing review; not an issuer."""
    operator_approval_sha256: str
    account_billing_evidence_sha256: str
    count_billing_known: bool
    cap_microdollars: int


def projection_bytes(request):
    require(type(request) is ReviewedRequest, "reviewed-request-required")
    body = request.projection
    require(type(body) is dict and set(body) == {"model", "instructions", "input", "text"}, "projection-fields")
    require(body["model"] == MODEL and type(body["instructions"]) is str
            and type(body["input"]) is str and type(body["text"]) is dict, "projection-types")
    fmt = body["text"].get("format")
    require(set(body["text"]) == {"format"} and type(fmt) is dict
            and set(fmt) == {"type", "name", "schema", "strict"}
            and fmt["type"] == "json_schema" and fmt["strict"] is True
            and type(fmt["schema"]) is dict and type(fmt["name"]) is str
            and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", fmt["name"]) is not None, "artifact-schema-binding")
    raw = canonical(body)
    require(len(raw) <= MAX_BODY and hash_value(request.projection_sha256)
            and sha(raw) == request.projection_sha256, "projection-hash-size")
    integer(request.token_upper_bound, 100000, "pre-count-bound")
    require(hash_value(request.bound_proof_sha256) and hash_value(request.public_context_approval_sha256), "pre-count-proof-missing")
    return raw


def usage_cost(response, token_upper_bound):
    usage = response.get("usage")
    require(type(usage) is dict, "usage-missing")
    inp = integer(usage.get("input_tokens"), 100000, "input-usage")
    out = integer(usage.get("output_tokens"), 32000, "output-usage")
    total = integer(usage.get("total_tokens"), 132000, "total-usage")
    integer(token_upper_bound, 100000, "pre-count-bound")
    require(inp <= token_upper_bound, "input-usage-exceeds-bound")
    require(total == inp+out, "usage-total-mismatch")
    details = usage.get("output_tokens_details")
    require(type(details) is dict, "reasoning-usage-missing")
    integer(details.get("reasoning_tokens"), out, "reasoning-usage")
    # Rates USD5.50/24.75 per million; round upward to whole microdollars.
    microdollars = (inp*550 + out*2475 + 99)//100
    require(microdollars <= 1_342_000, "generation-hold-exceeded")
    return microdollars, {"input_tokens": inp, "output_tokens": out, "total_tokens": total}


class PreviewTransport:
    """Single controller process, fresh ledger, five irrevocable role slots.

    It accepts only a trusted admission seam, not an untrusted envelope. Composition
    must enforce exact admission type/binding/authentication and public-only context.
    It is intentionally unwired from all existing routes and the CLI.
    """
    def __init__(self, *, admission, spend, ledger, api_key, validate_artifact,
                 wire=None, clock=time.monotonic):
        receipt = admission.public_receipt()
        require(receipt.get("scope") == "NOT-P5/public-CBACT04C-only"
                and receipt.get("qualified") is False and receipt.get("production_controller_receipt") is False
                and receipt.get("status") == "ADMITTED_ONLY" and receipt.get("run_budget_seconds") == 8100,
                "preview-admission-required")
        require(type(spend) is ReviewedSpend and spend.count_billing_known is True
                and hash_value(spend.operator_approval_sha256) and hash_value(spend.account_billing_evidence_sha256),
                "spend-and-billing-authority-required")
        require(type(spend.cap_microdollars) is int and 0 < spend.cap_microdollars <= RUN_CAP, "spend-cap")
        start, end = admission.started_monotonic, admission.deadline_monotonic
        require(type(start) in (int,float) and type(end) in (int,float) and math.isfinite(start)
                and math.isfinite(end) and end == start + 8100, "fixed-run-deadline")
        require(type(api_key) is str and 0 < len(api_key) <= 512 and not any(c.isspace() for c in api_key), "credential-memory-only")
        require(callable(validate_artifact), "artifact-validator-required")
        self._pid, self._lock = os.getpid(), threading.Lock()
        self._start, self._end, self._last = start, end, start
        self._spend, self._ledger, self._key = spend, ledger, api_key
        self._wire, self._clock = wire or DeadlineWire(clock=clock), clock
        self._validate_artifact = validate_artifact
        self._used, self._holds, self._stopped = set(), 0, False
        self._binding = receipt["binding_sha256"]
        require(hash_value(self._binding), "admission-binding")

    def _now(self):
        now = self._clock()
        require(self._pid == os.getpid() and type(now) in (int,float) and math.isfinite(now)
                and self._last <= now < self._end-15, "run-deadline-or-process")
        self._last = now
        return now

    def _call(self, role, phase, path, body, cap):
        end = min(self._now()+cap, self._end-15)
        require(end-self._now() > 5, "phase-deadline")
        self._ledger.record_once(role+"-"+phase+"-send.json", {"request_sha256": sha(body), "consumed": True, "retries": 0})
        require(self._now() < end-5, "phase-deadline")
        status, raw = self._wire.post_once(path, body, self._key, end)
        self._now()
        self._ledger.record_once(role+"-"+phase+"-response.json", {"response_sha256": sha(raw), "http_status": status})
        require(200 <= status < 300, "http-status-failure")
        result = strict_json(raw)
        require(type(result) is dict and self._clock() < end, "phase-response-or-deadline")
        require(self._now() < end, "phase-deadline")
        return result, end

    def complete(self, role, request):
        with self._lock:
            require(not self._stopped and role in ROLES and role not in self._used, "role-consumed-or-stopped")
            self._now()
            raw = projection_bytes(request)
            body = strict_json(raw)  # private immutable copy before network/threads
            require(self._holds+SLOT_HOLD <= self._spend.cap_microdollars, "cap-shortage")
            self._used.add(role)
            self._holds += SLOT_HOLD
            try:
                self._ledger.record_once(role+"-reservation.json", {"role": role,"binding_sha256": self._binding,
                    "projection_sha256": sha(raw),"hold_microdollars": SLOT_HOLD,"slot_consumed": True,
                    "count_billing_evidence_sha256": self._spend.account_billing_evidence_sha256})
                counted, count_end = self._call(role,"count",COUNT_PATH,raw,120)
                require(counted.get("object") == "response.input_tokens", "count-object")
                count = integer(counted.get("input_tokens"),100000,"count-response")
                require(count <= request.token_upper_bound, "pre-count-proof-violated")
                require(self._now() < count_end, "count-phase-deadline")
                generation = dict(body,service_tier="flex",store=False,max_output_tokens=32000,
                    reasoning={"effort":"medium"},tools=[],background=False,stream=False,
                    previous_response_id=None,truncation="disabled")
                response, generation_end = self._call(role,"generation",GENERATION_PATH,canonical(generation),900)
                require(response.get("status") == "completed" and response.get("incomplete_details") is None
                        and response.get("error") is None, "incomplete-or-failed-response")
                require(response.get("model") == MODEL and response.get("service_tier") == "flex", "snapshot-or-flex-mismatch")
                cost, usage = usage_cost(response,request.token_upper_bound)
                texts=[]
                require(type(response.get("output")) is list, "output-missing")
                for item in response["output"]:
                    require(type(item) is dict, "output-item")
                    if item.get("type") == "reasoning":
                        require(item.get("status", "completed") == "completed", "incomplete-reasoning")
                        continue
                    require(item.get("type") == "message" and item.get("role") == "assistant"
                            and item.get("status") == "completed" and type(item.get("content")) is list, "unexpected-output")
                    for part in item["content"]:
                        require(type(part) is dict and part.get("type") == "output_text" and type(part.get("text")) is str, "non-artifact-output")
                        texts.append(part["text"])
                require(len(texts) == 1, "one-complete-artifact-required")
                artifact = strict_json(texts[0].encode("utf-8"))
                require(self._validate_artifact(artifact,body["text"]["format"]["schema"]) is True, "artifact-schema")
                require(self._now() < generation_end, "generation-phase-deadline")
                evidence = {"role":role,"status":"COMPLETED","count_tokens":count,"usage":usage,
                    "token_upper_bound":request.token_upper_bound,"count_matches_usage":count == usage["input_tokens"],
                    "generation_conservative_microdollars":cost,"count_hold_microdollars":550000,
                    "total_reserved_microdollars":SLOT_HOLD,"holds_released":False,"billing_final":False,
                    "requested_tier":"flex","observed_tier":"flex","model":MODEL,"attempts":1,"retries":0,
                    "artifact_sha256":sha(canonical(artifact)),"qualified":False,"production_controller_receipt":False}
                self._ledger.record_once(role+"-complete.json",evidence)
                require(self._now() < generation_end, "generation-phase-deadline")
                return artifact,evidence
            except BaseException as error:
                self._stopped = True
                # The full hold and consumed files stay. Failure evidence must not
                # replace an earlier durable record or disclose provider content.
                try:
                    self._ledger.record_once(role+"-failed.json",{"status":"FAILED_CONSUMED","full_hold_retained":True,"resume":False})
                except (OSError,TransportRefused):
                    pass
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise TransportRefused("slot-failed-consumed-no-retry") from None

    def public_totals(self):
        return {"consumed_slots":len(self._used),"reserved_microdollars":self._holds,
                "stopped":self._stopped,"billing_final":False,"holds_released":False,"qualified":False}
