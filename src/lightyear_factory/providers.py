from __future__ import annotations

import json
import time
from dataclasses import dataclass
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


class OpenAIResponsesProvider:
    """Stateless Responses API provider with strict structured output."""

    provider_id = "openai-responses"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.6",
        opener: Callable[..., Any] = urlopen,
        input_usd_per_million: float = 0.0,
        output_usd_per_million: float = 0.0,
    ) -> None:
        if not api_key:
            raise ContractError("OPENAI_API_KEY is required for the OpenAI factory provider")
        self.api_key = api_key
        self.model = model
        self.opener = opener
        self.input_usd_per_million = max(0.0, float(input_usd_per_million))
        self.output_usd_per_million = max(0.0, float(output_usd_per_million))

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
        request = Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.monotonic()
        try:
            with self.opener(request, timeout=180) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ContractError(f"OpenAI {role} request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            detail = exc.reason if hasattr(exc, "reason") else exc
            raise ContractError(f"OpenAI {role} request failed: {detail}") from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)
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
            "request_sha256": canonical_hash(body),
            "response_sha256": canonical_hash({"content": result}),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": round(estimated_cost, 8),
            "cost_estimate_available": cost_estimate_available,
            "elapsed_ms": elapsed_ms,
        }
        evidence["content_sha256"] = canonical_hash(evidence)
        return ProviderResult(result, evidence)


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
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
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
            "response_sha256": canonical_hash({"content": content}),
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "cost_estimate_available": False,
            "elapsed_ms": 0,
        }
        evidence["content_sha256"] = canonical_hash(evidence)
        return ProviderResult(content, evidence)


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
