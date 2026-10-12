"""Operator-invoked POSTTRAN Phase 1 transport; standard library only.

Importing, plan validation and tests never read a credential or open a socket.
Only the HTTP worker reads LIGHTYEAR_POSTTRAN_OPENAI_KEY, immediately before
its single request. There is no credential fallback, redirect or retry.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
KEY_NAME = "LIGHTYEAR_POSTTRAN_OPENAI_KEY"
HOST = "api.openai.com"
COUNT = "/v1/responses/input_tokens"
GENERATE = "/v1/responses"
WALL_TIMEOUTS = {COUNT: 120, GENERATE: 1800}
CONNECT_TIMEOUT = 30
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_REQUEST_BYTES = 8 * 1024 * 1024
SCHEMA = "posttran-independent-preregistration/4"


class Refusal(Exception):
    """Messages are fixed codes, never exception/server/credential text."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def seal(value):
    return dict(value, content_sha256=sha(canonical(value)))


def now():
    return datetime.now(timezone.utc).isoformat()


def verify_seal(value):
    if value.get("content_sha256") != sha(canonical({k: v for k, v in value.items()
                                                   if k != "content_sha256"})):
        raise Refusal("content-seal-mismatch")


def save(path, value, *, new=False):
    """Flush then atomically publish; callers hold their operation lock."""
    path = Path(path)
    if new and path.exists():
        raise Refusal("evidence-already-exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".pending")
    with temporary.open("xb") as out:
        out.write(canonical(value) + b"\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


def lock(path):
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Refusal("operation-busy-or-interrupted") from None
    os.close(descriptor)


def _payload_valid(endpoint, payload):
    if endpoint not in WALL_TIMEOUTS or not isinstance(payload, dict):
        raise Refusal("endpoint-or-payload-refused")
    if payload.get("model") != "gpt-6-astra" or payload.get("reasoning") != {"effort": "high"}:
        raise Refusal("model-or-reasoning-refused")
    if endpoint == COUNT:
        if set(payload) != {"model", "reasoning", "input"}:
            raise Refusal("count-payload-fields-refused")
    elif (set(payload) != {"model", "reasoning", "input", "service_tier",
                           "max_output_tokens", "truncation", "store"}
          or payload.get("store") is not False
          or payload.get("max_output_tokens") != 64000
          or payload.get("service_tier") != "default"
          or payload.get("truncation") != "disabled"):
        raise Refusal("generation-contract-refused")


def _response_valid(endpoint, value):
    if not isinstance(value, dict):
        raise Refusal("response-object-required")
    if endpoint == COUNT:
        tokens = value.get("input_tokens")
        if (value.get("object") != "response.input_tokens" or type(tokens) is not int
                or not 0 < tokens <= 250000):
            raise Refusal("input-count-invalid-or-over-cap")
    else:
        if value.get("status") != "completed":
            raise Refusal("incomplete-response")
        usage = value.get("usage")
        if not isinstance(usage, dict):
            raise Refusal("missing-usage")
        inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
        if type(inputs) is not int or type(outputs) is not int or inputs < 0 or outputs < 0:
            raise Refusal("missing-or-invalid-usage")
        if inputs > 250000 or outputs > 64000:
            raise Refusal("usage-cap-exceeded")
        if value.get("service_tier", "default") != "default":
            raise Refusal("service-tier-refused")


def _http_worker(endpoint, payload):
    """One request. This is the sole credential-reading function."""
    request_hash = None
    response_hash = None
    connection = None
    try:
        _payload_valid(endpoint, payload)
        body = canonical(payload)
        request_hash = sha(body)
        if len(body) > MAX_REQUEST_BYTES:
            raise Refusal("request-size-cap")
        key = os.environ.get(KEY_NAME)  # Never read at import/preparation time.
        if not key or any(c in key for c in "\r\n"):
            raise Refusal("dedicated-credential-missing-or-invalid")
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        connection = http.client.HTTPSConnection(HOST, 443, timeout=CONNECT_TIMEOUT,
                                                 context=context)
        connection.connect()
        connection.sock.settimeout(WALL_TIMEOUTS[endpoint])
        connection.request("POST", endpoint, body=body, headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            "Accept": "application/json", "Accept-Encoding": "identity"})
        response = connection.getresponse()
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        response_hash = sha(raw)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise Refusal("response-size-cap")
        # Never return even a successful response that echoes the credential.
        if key.encode("utf-8") in raw:
            raise Refusal("sensitive-response-refused")
        if not 200 <= response.status < 300:
            # Includes redirects and 429/5xx. Never follow or retry.
            raise Refusal("http-status-refused")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise Refusal("invalid-json-response") from None
        def contains_key(item):
            if isinstance(item, str):
                return key in item
            if isinstance(item, dict):
                return any(contains_key(k) or contains_key(v) for k, v in item.items())
            if isinstance(item, list):
                return any(contains_key(v) for v in item)
            return False
        if contains_key(value):
            raise Refusal("sensitive-response-refused")
        _response_valid(endpoint, value)
        return dict(ok=True, request_sha256=request_hash, response_sha256=response_hash,
                    response=value)
    except Refusal as error:
        return dict(ok=False, error_code=str(error), request_sha256=request_hash,
                    response_sha256=response_hash)
    except Exception:
        # No exception repr, server body, request headers or traceback escapes.
        return dict(ok=False, error_code="network-or-transport-failure",
                    request_sha256=request_hash, response_sha256=response_hash)
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def network_once(endpoint, payload):
    """Child-process wall timeout also bounds DNS and slow/trickling reads."""
    _payload_valid(endpoint, payload)
    job = canonical(dict(endpoint=endpoint, payload=payload))
    request_hash = sha(canonical(payload))
    try:
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                                 "--http-worker"], input=job, capture_output=True,
                                timeout=WALL_TIMEOUTS[endpoint], check=False)
        if result.returncode != 0 or result.stderr:
            raise Refusal("worker-failed")
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or value.get("request_sha256") != request_hash:
            raise Refusal("worker-response-binding")
        return value
    except subprocess.TimeoutExpired:
        # subprocess.run kills and waits for the child. No retry/cancel request.
        return dict(ok=False, error_code="transport-wall-timeout",
                    request_sha256=request_hash, response_sha256=None)
    except Exception:
        return dict(ok=False, error_code="worker-failed",
                    request_sha256=request_hash, response_sha256=None)


def load_plan(path, approval):
    plan = json.loads(Path(path).read_bytes())
    verify_seal(plan)
    if plan.get("schema") != SCHEMA:
        raise Refusal("exact-amended-plan-approval-required")
    # Factory activation is operator configuration, never supplied by the packet.
    # The HTTP worker remains standard-library-only and receives no trust keys.
    if os.environ.get("LIGHTYEAR_FACTORY_AUTHORITY"):
        from .tower_authority import configured_authority, proof_contract
        try:
            configured_authority().spend(plan, approval, proof_contract(approval), phase=1)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise Refusal("signed-factory-spend-required") from None
    elif approval != "go POSTTRAN " + plan["content_sha256"]:
        raise Refusal("exact-amended-plan-approval-required")
    transport = plan["dispatch"]["dedicated_transport"]
    if sha(Path(__file__).read_bytes()) != transport["sha256"]:
        raise Refusal("transport-hash-mismatch")
    if (transport["credential_environment_variable"] != KEY_NAME
            or transport["base_url"] != "https://" + HOST
            or transport["wall_timeouts_seconds"] != WALL_TIMEOUTS
            or transport["connect_timeout_seconds"] != CONNECT_TIMEOUT):
        raise Refusal("transport-contract-mismatch")
    if sha(Path(plan["client"]["path"]).read_bytes()) != plan["client"]["sha256"]:
        raise Refusal("pinned-client-hash-mismatch")
    limits = plan["phases"]["1"]
    if (limits["attempts"], limits["model_calls"], limits["compilations"],
        limits["input_tokens"], limits["output_tokens"], limits["hours"],
        limits["api_equivalent_hard_cap_usd"], limits["per_call_output_tokens"],
        limits["per_call_input_tokens"], limits["per_call_worst_case_usd"]) != (
            3, 3, 3, 750000, 192000, 2, 36, 64000, 250000, 11.05):
        raise Refusal("phase1-limits-mismatch")
    return plan


def packet_payload(plan):
    files = dict(plan["inputs"])
    prompt_path = "docs/factory/posttran-second-opinion/phase1-work-order.md"
    files[prompt_path] = plan["prompts"]["phase1-work-order.md"]
    packet = {}
    for relative, expected in files.items():
        path = ROOT / relative
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise Refusal("packet-path-boundary")
        raw = path.read_bytes()
        if sha(raw) != expected:
            raise Refusal("public-packet-hash-mismatch")
        packet["phase1-work-order.md" if relative == prompt_path else relative] = raw
    payload = dict(model=plan["model"], reasoning={"effort": plan["reasoning_effort"]},
                   service_tier="default", max_output_tokens=64000,
                   truncation="disabled", store=False, input=[{"role": "user", "content": [
                       {"type": "input_text", "text": name + "\n" + raw.decode("utf-8")
                        if name.endswith((".md", ".cbl", ".cpy", ".jcl")) else
                        name + "\nPUBLIC FIXED BYTES HEX\n" + raw.hex()}
                       for name, raw in sorted(packet.items())]}])
    _payload_valid(GENERATE, payload)
    return payload, {name: sha(raw) for name, raw in packet.items()}


def locations(plan):
    base = ROOT / "work/posttran-dedicated-phase1" / plan["content_sha256"]
    base.mkdir(parents=True, exist_ok=True)
    return base, ROOT / "work/posttran-dedicated-phase1/phase1-ledger.json"


def preflight(plan, approved):
    payload, packet = packet_payload(plan)
    count = {k: payload[k] for k in ("model", "reasoning", "input")}
    base, _ = locations(plan)
    output, guard = base / "preflight.json", base / "preflight.lock"
    lock(guard)
    try:
        if output.exists():
            raise Refusal("preflight-already-recorded-no-retry")
        receipt = dict(schema="posttran-token-preflight/1", plan_sha256=approved,
                       approved_command="go POSTTRAN " + approved, started_at=now(),
                       status="requested", generation=False, outside_reservation_ledger=True,
                       attempts_consumed=0, packet_sha256=packet,
                       generation_request_sha256=sha(canonical(payload)),
                       request_sha256=sha(canonical(count)))
        save(output, seal(receipt), new=True)
        result = network_once(COUNT, count)
        receipt.update(status="completed" if result["ok"] else "failed", finished_at=now(),
                       response_sha256=result.get("response_sha256"))
        if result["ok"]:
            _response_valid(COUNT, result["response"])
            receipt["input_tokens"] = result["response"]["input_tokens"]
        else:
            receipt["error_code"] = result["error_code"]
        save(output, seal(receipt))
        if not result["ok"]:
            raise Refusal("preflight-failed-see-redacted-receipt")
        return dict(status="preflight-completed", receipt=str(output),
                    input_tokens=receipt["input_tokens"], attempts_consumed=0,
                    content_sha256=seal(receipt)["content_sha256"])
    finally:
        guard.unlink(missing_ok=True)


def attempt_one(plan, approved):
    payload, packet = packet_payload(plan)
    base, ledger = locations(plan)
    before = json.loads((base / "preflight.json").read_bytes())
    verify_seal(before)
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(before["finished_at"])).total_seconds()
    if (before.get("status") != "completed" or before.get("plan_sha256") != approved
            or before.get("packet_sha256") != packet or not 0 <= age <= 3600
            or before.get("generation_request_sha256") != sha(canonical(payload))):
        raise Refusal("completed-exact-preflight-required-within-one-hour")
    _response_valid(COUNT, dict(object="response.input_tokens", input_tokens=before.get("input_tokens")))
    guard = ledger.with_suffix(".lock")
    lock(guard)
    try:
        if ledger.exists():
            raise Refusal("phase1-already-reserved-no-retry")
        state = dict(schema="posttran-dedicated-reservation-ledger/1", plan_sha256=approved,
                     approved_command="go POSTTRAN " + approved, started_at=now(),
                     reservations=[dict(attempt=1, reserved_usd=11.05, input_tokens=250000,
                                        output_tokens=64000, status="reserved",
                                        request_sha256=sha(canonical(payload)),
                                        preflight_sha256=before["content_sha256"])])
        save(ledger, seal(state), new=True)  # Reservation precedes generation only.
        started = time.monotonic()
        result = network_once(GENERATE, payload)
        entry = state["reservations"][0]
        entry.update(finished_at=now(), response_sha256=result.get("response_sha256"))
        if result["ok"]:
            _response_valid(GENERATE, result["response"])
            if result["response"]["usage"]["input_tokens"] != before["input_tokens"]:
                result = dict(result, ok=False, error_code="input-count-usage-mismatch")
            elif time.monotonic() - started > WALL_TIMEOUTS[GENERATE]:
                result = dict(result, ok=False, error_code="generation-wall-timeout")
        if result["ok"]:
            artifact = base / "attempt-1-response.json"
            save(artifact, result["response"], new=True)
            entry.update(status="completed", usage=result["response"]["usage"],
                         artifact_sha256=sha(artifact.read_bytes()))
        else:
            entry.update(status="failed", error_code=result["error_code"])
        save(ledger, seal(state))
        if not result["ok"]:
            raise Refusal("attempt-failed-reservation-consumed-no-retry")
        return dict(status="attempt-1-completed", ledger=str(ledger), response=str(artifact),
                    response_sha256=entry["response_sha256"],
                    artifact_sha256=entry["artifact_sha256"], compilations=0,
                    phase2_authorized=False)
    finally:
        guard.unlink(missing_ok=True)


def main():
    if sys.argv[1:] == ["--http-worker"]:
        try:
            job = json.loads(sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
            result = _http_worker(job["endpoint"], job["payload"])
        except Exception:
            result = dict(ok=False, error_code="worker-input-refused")
        sys.stdout.buffer.write(canonical(result))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("preflight", "attempt-1"))
    parser.add_argument("--plan", required=True)
    approvals = parser.add_mutually_exclusive_group(required=True)
    approvals.add_argument("--go", help="Historical mode only: go POSTTRAN <amended plan hash>")
    approvals.add_argument("--approval-proof", type=Path, help="Signed Factory proof after activation")
    args = parser.parse_args()
    try:
        plan = load_plan(args.plan, json.loads(args.approval_proof.read_bytes()) if args.approval_proof else args.go)
        result = (preflight if args.operation == "preflight" else attempt_one)(plan, plan["content_sha256"])
        print(json.dumps(result, sort_keys=True))
        return 0
    except Refusal as error:
        print(json.dumps(dict(status="refused", error_code=str(error))), file=sys.stderr)
        return 2
    except Exception:
        print('{"status":"refused","error_code":"local-validation-or-state-error"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
