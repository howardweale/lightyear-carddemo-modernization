from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contracts import ContractError, WorkOrder, canonical_hash


class ModelProvider(Protocol):
    provider_id: str
    model: str

    def complete(
        self,
        role: str,
        instruction: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> "ProviderResult": ...


@dataclass(frozen=True)
class ProviderResult:
    content: dict[str, Any]
    evidence: dict[str, Any]


class ProviderError(ContractError):
    """Sanitized provider failure safe to expose in evaluation control receipts."""

    def __init__(
        self,
        role: str,
        code: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        attempts: int = 1,
        retries: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(f"OpenAI {role} request failed ({code})")
        self.role = role
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.attempts = attempts
        self.retries = list(retries or [])

    def safe_dict(self) -> dict[str, Any]:
        return {
            "provider": "openai-responses",
            "role": self.role,
            "error_code": self.code,
            "status_code": self.status_code,
            "retryable": self.retryable,
            "attempts": self.attempts,
            "retries": self.retries,
        }


class OpenAIResponsesProvider:
    """Stateless Responses API provider with strict structured output."""

    provider_id = "openai-responses"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.6-terra",
        opener: Callable[..., Any] = urlopen,
        input_usd_per_million: float = 0.0,
        output_usd_per_million: float = 0.0,
        max_output_tokens: int = 25_000,
        max_retries: int = 4,
        request_timeout_seconds: int = 240,
        retry_base_seconds: float = 1.0,
        retry_max_seconds: float = 60.0,
        token_preflight: bool = True,
        max_input_tokens_per_call: int = 60_000,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float], float] | None = None,
    ) -> None:
        if not api_key:
            raise ContractError("OPENAI_API_KEY is required for the OpenAI factory provider")
        self.api_key = api_key
        self.model = model
        self.opener = opener
        self.input_usd_per_million = max(0.0, float(input_usd_per_million))
        self.output_usd_per_million = max(0.0, float(output_usd_per_million))
        self.max_output_tokens = max(1, int(max_output_tokens))
        self.max_retries = max(0, min(8, int(max_retries)))
        self.request_timeout_seconds = max(1, min(600, int(request_timeout_seconds)))
        self.retry_base_seconds = max(0.1, float(retry_base_seconds))
        self.retry_max_seconds = max(self.retry_base_seconds, float(retry_max_seconds))
        self.token_preflight = bool(token_preflight)
        self.max_input_tokens_per_call = max(1_000, int(max_input_tokens_per_call))
        self.sleep = sleep
        self.jitter = jitter or (lambda upper: random.uniform(0.0, upper))

    def complete(
        self,
        role: str,
        instruction: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> ProviderResult:
        body = {
            "model": self.model,
            "store": False,
            "max_output_tokens": self.max_output_tokens,
            "instructions": (
                f"You are the LIGHTYEAR {role} worker. Communicate only through the required "
                f"JSON artifact. {instruction} The deterministic controller, never you, decides "
                "whether work is accepted."
            ),
            "input": json.dumps(payload, sort_keys=True, separators=(",", ":")),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": f"lightyear_{role}_artifact",
                    "schema": schema,
                    "strict": True,
                }
            },
        }
        started = time.monotonic()
        token_count: int | None = None
        token_count_attempts = 0
        token_count_retries: list[dict[str, Any]] = []
        token_count_headers: dict[str, str] = {}
        token_count_request_sha256: str | None = None
        if self.token_preflight:
            count_body = {
                key: body[key] for key in ("model", "instructions", "input", "text")
            }
            token_count_request_sha256 = canonical_hash(count_body)
            (
                token_count,
                token_count_attempts,
                token_count_retries,
                token_count_headers,
            ) = self._count_input_tokens(role, count_body)
            if token_count > self.max_input_tokens_per_call:
                raise ProviderError(
                    role,
                    "input_token_budget_exceeded",
                    retryable=False,
                    attempts=token_count_attempts,
                    retries=token_count_retries,
                )
        retries: list[dict[str, Any]] = []
        response_headers: dict[str, str] = {}
        response_payload: dict[str, Any] | None = None
        for attempt in range(1, self.max_retries + 2):
            request = Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with self.opener(request, timeout=self.request_timeout_seconds) as response:
                    response_headers = _safe_rate_limit_headers(getattr(response, "headers", {}))
                    response_payload = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                error_code = _http_error_code(exc)
                retryable = _retryable_http_error(exc.code, error_code)
                if not retryable or attempt > self.max_retries:
                    raise ProviderError(
                        role,
                        error_code,
                        status_code=exc.code,
                        retryable=retryable,
                        attempts=attempt,
                        retries=retries,
                    ) from exc
                delay = _retry_delay_seconds(
                    exc.headers,
                    attempt,
                    self.retry_base_seconds,
                    self.retry_max_seconds,
                    self.jitter,
                )
                retries.append(
                    {
                        "attempt": attempt,
                        "status_code": exc.code,
                        "error_code": error_code,
                        "delay_ms": int(delay * 1000),
                    }
                )
                self.sleep(delay)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    role,
                    "invalid_json_response",
                    retryable=False,
                    attempts=attempt,
                    retries=retries,
                ) from exc
            except (URLError, TimeoutError) as exc:
                error_code = "network_timeout" if isinstance(exc, TimeoutError) else "network_error"
                if attempt > self.max_retries:
                    raise ProviderError(
                        role,
                        error_code,
                        retryable=True,
                        attempts=attempt,
                        retries=retries,
                    ) from exc
                delay = min(
                    self.retry_max_seconds,
                    self.retry_base_seconds * (2 ** (attempt - 1)),
                ) + self.jitter(min(1.0, self.retry_base_seconds))
                retries.append(
                    {
                        "attempt": attempt,
                        "status_code": None,
                        "error_code": error_code,
                        "delay_ms": int(delay * 1000),
                    }
                )
                self.sleep(delay)
        if response_payload is None:
            raise ProviderError(role, "empty_response", retryable=False)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if response_payload.get("status") == "incomplete":
            reason = (
                response_payload.get("incomplete_details", {}).get("reason")
                or "incomplete_response"
            )
            raise ProviderError(role, str(reason), retryable=False, attempts=len(retries) + 1)
        output_text = None
        for output in response_payload.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "refusal":
                    raise ContractError(f"OpenAI {role} request was refused")
                if content.get("type") == "output_text":
                    output_text = content.get("text")
                    break
        if not isinstance(output_text, str):
            raise ContractError(f"OpenAI {role} response did not contain structured output")
        try:
            result = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise ContractError(f"OpenAI {role} response was not valid JSON") from exc
        _validate_schema(result, schema, role)
        usage = response_payload.get("usage", {})
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        estimated_cost = (
            input_tokens * self.input_usd_per_million
            + output_tokens * self.output_usd_per_million
        ) / 1_000_000
        cost_estimate_available = (
            self.input_usd_per_million > 0 and self.output_usd_per_million > 0
        )
        evidence = {
            "schema_version": "1.0",
            "evidence_type": "lightyear-model-call",
            "provider": self.provider_id,
            "model": str(response_payload.get("model") or self.model),
            "role": role,
            "store": False,
            "strict_schema": True,
            "max_output_tokens": self.max_output_tokens,
            "input_token_preflight": self.token_preflight,
            "input_tokens_preflight": token_count,
            "max_input_tokens_per_call": self.max_input_tokens_per_call,
            "token_count_attempts": token_count_attempts,
            "token_count_retry_count": len(token_count_retries),
            "token_count_retries": token_count_retries,
            "token_count_rate_limits": token_count_headers,
            "token_count_request_sha256": token_count_request_sha256,
            "attempts": len(retries) + 1,
            "retry_count": len(retries),
            "retries": retries,
            "rate_limits": response_headers,
            "request_sha256": canonical_hash(body),
            "request_manifest": _request_manifest(instruction, payload),
            "response_sha256": canonical_hash({"content": result}),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(estimated_cost, 8),
            "cost_estimate_available": cost_estimate_available,
            "elapsed_ms": elapsed_ms,
        }
        evidence["content_sha256"] = canonical_hash(evidence)
        return ProviderResult(result, evidence)

    def _count_input_tokens(
        self, role: str, body: dict[str, Any]
    ) -> tuple[int, int, list[dict[str, Any]], dict[str, str]]:
        retries: list[dict[str, Any]] = []
        response_headers: dict[str, str] = {}
        for attempt in range(1, self.max_retries + 2):
            request = Request(
                "https://api.openai.com/v1/responses/input_tokens",
                data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with self.opener(request, timeout=self.request_timeout_seconds) as response:
                    response_headers = _safe_rate_limit_headers(
                        getattr(response, "headers", {})
                    )
                    payload = json.loads(response.read().decode("utf-8"))
                count = payload.get("input_tokens")
                if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                    raise ProviderError(
                        role,
                        "invalid_token_count_response",
                        retryable=False,
                        attempts=attempt,
                        retries=retries,
                    )
                return count, attempt, retries, response_headers
            except HTTPError as exc:
                error_code = _http_error_code(exc)
                retryable = _retryable_http_error(exc.code, error_code)
                if not retryable or attempt > self.max_retries:
                    raise ProviderError(
                        role,
                        f"token_count_{error_code}",
                        status_code=exc.code,
                        retryable=retryable,
                        attempts=attempt,
                        retries=retries,
                    ) from exc
                delay = _retry_delay_seconds(
                    exc.headers,
                    attempt,
                    self.retry_base_seconds,
                    self.retry_max_seconds,
                    self.jitter,
                )
                retries.append(
                    {
                        "attempt": attempt,
                        "status_code": exc.code,
                        "error_code": error_code,
                        "delay_ms": int(delay * 1000),
                    }
                )
                self.sleep(delay)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    role,
                    "invalid_token_count_response",
                    retryable=False,
                    attempts=attempt,
                    retries=retries,
                ) from exc
            except (URLError, TimeoutError) as exc:
                error_code = (
                    "token_count_network_timeout"
                    if isinstance(exc, TimeoutError)
                    else "token_count_network_error"
                )
                if attempt > self.max_retries:
                    raise ProviderError(
                        role,
                        error_code,
                        retryable=True,
                        attempts=attempt,
                        retries=retries,
                    ) from exc
                delay = min(
                    self.retry_max_seconds,
                    self.retry_base_seconds * (2 ** (attempt - 1)),
                ) + self.jitter(min(1.0, self.retry_base_seconds))
                retries.append(
                    {
                        "attempt": attempt,
                        "status_code": None,
                        "error_code": error_code,
                        "delay_ms": int(delay * 1000),
                    }
                )
                self.sleep(delay)
        raise ProviderError(role, "token_count_empty_response", retryable=False)


class BoundedModelProvider:
    """Controller-side budget boundary around a replaceable model provider."""

    def __init__(self, provider: ModelProvider, order: WorkOrder) -> None:
        self.provider = provider
        self.provider_id = provider.provider_id
        self.model = provider.model
        self.order = order
        self.started = time.monotonic()
        self.calls: list[dict[str, Any]] = []
        self.input_bytes = 0
        self.output_bytes = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.estimated_cost_usd = 0.0
        self.cost_estimate_available = True

    def complete(
        self,
        role: str,
        instruction: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> ProviderResult:
        self._check_elapsed()
        if len(self.calls) >= self.order.max_model_calls:
            raise ContractError("Model provider exceeded max_model_calls")
        request_bytes = len(
            json.dumps(
                {"instruction": instruction, "payload": payload, "schema": schema},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if self.input_bytes + request_bytes > self.order.max_model_input_bytes:
            raise ContractError("Model provider exceeded max_model_input_bytes")
        input_price = float(getattr(self.provider, "input_usd_per_million", 0.0))
        output_price = float(getattr(self.provider, "output_usd_per_million", 0.0))
        output_cap = int(getattr(self.provider, "max_output_tokens", 0))
        if input_price > 0 and output_price > 0 and output_cap > 0:
            conservative_call_cost = (
                request_bytes * input_price + output_cap * output_price
            ) / 1_000_000
            if self.estimated_cost_usd + conservative_call_cost > self.order.max_model_cost_usd:
                raise ContractError("Model provider cannot admit call inside max_model_cost_usd")
        result = self.provider.complete(role, instruction, payload, schema)
        response_bytes = len(
            json.dumps(result.content, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        next_input_tokens = self.input_tokens + int(result.evidence.get("input_tokens", 0))
        next_output_tokens = self.output_tokens + int(result.evidence.get("output_tokens", 0))
        next_cost = self.estimated_cost_usd + float(
            result.evidence.get("estimated_cost_usd", 0.0)
        )
        next_cost_available = self.cost_estimate_available and bool(
            result.evidence.get("cost_estimate_available", False)
        )
        if self.output_bytes + response_bytes > self.order.max_model_output_bytes:
            raise ContractError("Model provider exceeded max_model_output_bytes")
        if next_input_tokens + next_output_tokens > self.order.max_model_tokens:
            raise ContractError("Model provider exceeded max_model_tokens")
        if next_cost > self.order.max_model_cost_usd:
            raise ContractError("Model provider exceeded max_model_cost_usd")
        self.input_bytes += request_bytes
        self.output_bytes += response_bytes
        self.input_tokens = next_input_tokens
        self.output_tokens = next_output_tokens
        self.estimated_cost_usd = next_cost
        self.cost_estimate_available = next_cost_available
        evidence = dict(result.evidence)
        evidence["call_sequence"] = len(self.calls) + 1
        evidence["request_bytes"] = request_bytes
        evidence["response_bytes"] = response_bytes
        evidence["content_sha256"] = canonical_hash(evidence, {"content_sha256"})
        self.calls.append(evidence)
        self._check_elapsed()
        return ProviderResult(result.content, evidence)

    def summary(self) -> dict[str, Any]:
        payload = {
            "mode": "model-backed",
            "provider": self.provider_id,
            "model": self.model,
            "calls": len(self.calls),
            "provider_attempts": sum(int(item.get("attempts", 1)) for item in self.calls),
            "provider_retries": sum(int(item.get("retry_count", 0)) for item in self.calls),
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "input_token_preflight_calls": sum(
                1 for item in self.calls if item.get("input_token_preflight")
            ),
            "input_token_count_attempts": sum(
                int(item.get("token_count_attempts", 0)) for item in self.calls
            ),
            "input_token_count_retries": sum(
                int(item.get("token_count_retry_count", 0)) for item in self.calls
            ),
            "input_tokens_preflight": sum(
                int(item.get("input_tokens_preflight") or 0) for item in self.calls
            ),
            "estimated_cost_usd": round(self.estimated_cost_usd, 8),
            "cost_estimate_available": self.cost_estimate_available,
            "elapsed_ms": int((time.monotonic() - self.started) * 1000),
            "call_evidence_sha256": [item["content_sha256"] for item in self.calls],
            "budgets": {
                "max_calls": self.order.max_model_calls,
                "max_input_bytes": self.order.max_model_input_bytes,
                "max_output_bytes": self.order.max_model_output_bytes,
                "max_tokens": self.order.max_model_tokens,
                "max_cost_usd": self.order.max_model_cost_usd,
                "max_elapsed_seconds": self.order.max_elapsed_seconds,
            },
        }
        payload["content_sha256"] = canonical_hash(payload)
        return payload

    def _check_elapsed(self) -> None:
        if time.monotonic() - self.started > self.order.max_elapsed_seconds:
            raise ContractError("Model provider exceeded max_elapsed_seconds")


class ScriptedModelProvider:
    """Deterministic test provider; never represents real model performance."""

    provider_id = "scripted-test"
    model = "scripted-test-model"

    def __init__(self, outputs: list[dict[str, Any]]) -> None:
        self.outputs = list(outputs)
        self.requests: list[dict[str, Any]] = []

    def complete(
        self,
        role: str,
        instruction: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> ProviderResult:
        if not self.outputs:
            raise ContractError("Scripted provider has no remaining output")
        self.requests.append(
            {"role": role, "instruction": instruction, "payload": payload, "schema": schema}
        )
        content = self.outputs.pop(0)
        _validate_schema(content, schema, role)
        evidence = {
            "schema_version": "1.0",
            "evidence_type": "lightyear-model-call",
            "provider": self.provider_id,
            "model": self.model,
            "role": role,
            "store": False,
            "strict_schema": True,
            "request_sha256": canonical_hash({"instruction": instruction, "payload": payload}),
            "request_manifest": _request_manifest(instruction, payload),
            "response_sha256": canonical_hash({"content": content}),
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "cost_estimate_available": False,
            "elapsed_ms": 0,
        }
        evidence["content_sha256"] = canonical_hash(evidence)
        return ProviderResult(content, evidence)


_NON_RETRYABLE_LIMIT_CODES = {
    "billing_hard_limit_reached",
    "credit_balance_exhausted",
    "insufficient_quota",
    "organization_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
    "project_spend_limit_exceeded",
}


def _http_error_code(error: HTTPError) -> str:
    try:
        raw = error.read(65_536)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        detail = payload.get("error", {}) if isinstance(payload, dict) else {}
        code = detail.get("code") or detail.get("type")
        if isinstance(code, str) and code.strip():
            return code.strip()[:120]
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    return f"http_{error.code}"


def _retryable_http_error(status_code: int, error_code: str) -> bool:
    if error_code in _NON_RETRYABLE_LIMIT_CODES:
        return False
    return status_code in {408, 409, 429} or 500 <= status_code <= 599


def _retry_delay_seconds(
    headers: Any,
    attempt: int,
    base: float,
    maximum: float,
    jitter: Callable[[float], float],
) -> float:
    retry_after = _retry_after_seconds(headers)
    if retry_after is not None:
        if retry_after > maximum:
            return maximum
        return max(0.0, retry_after) + jitter(min(1.0, base))
    exponential = min(maximum, base * (2 ** (attempt - 1)))
    return min(maximum, exponential + jitter(min(1.0, base)))


def _retry_after_seconds(headers: Any) -> float | None:
    value = headers.get("Retry-After") if headers is not None else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            when = parsedate_to_datetime(str(value))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def _safe_rate_limit_headers(headers: Any) -> dict[str, str]:
    allowed = (
        "x-ratelimit-limit-requests",
        "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
        "x-request-id",
    )
    result: dict[str, str] = {}
    for name in allowed:
        value = headers.get(name) if headers is not None else None
        if value is not None:
            result[name] = str(value)[:200]
    return result


def _request_manifest(instruction: str, payload: dict[str, Any]) -> dict[str, Any]:
    context = payload.get("planner_context") or payload.get("graph_context") or {}
    manifest = {
        "instruction_sha256": canonical_hash({"instruction": instruction}),
        "payload_sha256": canonical_hash(payload),
        "payload_keys": sorted(payload),
        "context_type": context.get("context_type"),
        "context_sha256": context.get("content_sha256"),
        "context_statistics": context.get("statistics", {}),
        "selected_evidence_capsule_ids": context.get(
            "selected_evidence_capsule_ids", []
        ),
        "selected_graph_node_ids": context.get("selected_graph_node_ids", []),
    }
    manifest["content_sha256"] = canonical_hash(manifest)
    return manifest


def _validate_schema(value: Any, schema: dict[str, Any], location: str) -> None:
    expected = schema.get("type")
    allowed_types = expected if isinstance(expected, list) else [expected]
    if value is None and "null" in allowed_types:
        return
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if expected and not any(checks[item](value) for item in allowed_types if item in checks):
        raise ContractError(f"Structured output at {location} has the wrong type")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError(f"Structured output at {location} is outside the allowed enum")
    if isinstance(value, dict):
        required = set(schema.get("required", []))
        missing = required - set(value)
        if missing:
            raise ContractError(
                f"Structured output at {location} is missing: {', '.join(sorted(missing))}"
            )
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                raise ContractError(
                    f"Structured output at {location} has unexpected fields: "
                    f"{', '.join(sorted(extras))}"
                )
        for key, child in value.items():
            if key in properties:
                _validate_schema(child, properties[key], f"{location}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, child in enumerate(value):
            _validate_schema(child, schema["items"], f"{location}[{index}]")
