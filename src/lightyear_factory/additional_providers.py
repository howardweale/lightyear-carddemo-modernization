"""Provider-neutral structured JSON adapters. Tests use injected HTTP fixtures.

API formats: platform.claude.com/docs/en/build-with-claude/structured-outputs
and ai.google.dev/gemini-api/docs/structured-output. No default model IDs.
"""

import json
import math
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from .contracts import ContractError, canonical_hash
from .providers import (
    ProviderError,
    ProviderResult,
    _validate_schema,
    _request_manifest,
)


class TransportError(ProviderError):
    def __init__(self, role, provider, code, status=None):
        super().__init__(role, code, status_code=status)
        self.provider = provider
        self.args = (f"{provider} transport failed ({code})",)

    def safe_dict(self):
        return {**super().safe_dict(), "provider": self.provider}


class JSONProvider:
    """No implicit retries; the controller owns every call and fallback."""

    manage_failure_budget = True

    def __init__(
        self,
        model,
        *,
        api_key=None,
        input_usd_per_million,
        output_usd_per_million,
        max_output_tokens=4096,
        opener=None,
    ):
        if not model or not isinstance(model, str):
            raise ValueError("model identifier required")
        self.model = model
        self.api_key = api_key or os.environ.get(self.key_env, "")
        if not self.api_key:
            raise ValueError("provider credential required")
        self.input_usd_per_million = float(input_usd_per_million)
        self.output_usd_per_million = float(output_usd_per_million)
        if not all(
            math.isfinite(p) and p > 0
            for p in (self.input_usd_per_million, self.output_usd_per_million)
        ):
            raise ValueError("positive finite prices required")
        if type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 65536:
            raise ValueError("output token cap required")
        self.max_output_tokens = max_output_tokens
        self.opener = opener or urlopen

    def complete(self, role, instruction, payload, schema):
        url, headers, body = self.request(instruction, payload, schema)
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        started = time.monotonic()
        try:
            with self.opener(
                Request(
                    url,
                    data=raw,
                    headers={"Content-Type": "application/json", **headers},
                    method="POST",
                ),
                timeout=120,
            ) as response:
                data = response.read(8 * 1024 * 1024 + 1)
        except HTTPError as exc:
            raise TransportError(
                role, self.provider_id, "http-error", exc.code
            ) from None
        except (URLError, TimeoutError, OSError):
            raise TransportError(role, self.provider_id, "transport-error") from None
        if len(data) > 8 * 1024 * 1024:
            raise ContractError("provider response exceeds byte cap")
        try:
            response = json.loads(data)
            from .model_versions import verify_response
            verify_response(self,response)
            content, usage = self.parse(response)
            _validate_schema(content, schema, role)
            if any(type(v) is not int or v < 0 for v in usage.values()):
                raise ValueError()
        except (KeyError, ValueError, TypeError, IndexError):
            # Bad/refused/truncated output is a result, not a transport fallback.
            raise ContractError("invalid provider structured result or usage") from None
        cost = (
            usage["input_tokens"] * self.input_usd_per_million
            + usage["output_tokens"] * self.output_usd_per_million
        ) / 1e6
        e = dict(
            schema_version="1.0",
            evidence_type="lightyear-model-call",
            provider=self.provider_id,
            model=self.model,
            role=role,
            strict_schema=True,
            request_sha256=canonical_hash(body),
            request_manifest=_request_manifest(instruction, payload),
            response_sha256=canonical_hash({"content": content}),
            **usage,
            estimated_cost_usd=round(cost, 8),
            cost_estimate_available=True,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            attempts=1,
            retry_count=0,
        )
        e["content_sha256"] = canonical_hash(e)
        return ProviderResult(content, e)


class AnthropicMessagesProvider(JSONProvider):
    provider_id, key_env = "anthropic-messages", "ANTHROPIC_API_KEY"

    def request(self, instruction, payload, schema):
        return (
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            dict(
                model=self.model,
                max_tokens=self.max_output_tokens,
                system=instruction,
                messages=[
                    dict(role="user", content=json.dumps(payload, sort_keys=True))
                ],
                output_config=dict(format=dict(type="json_schema", schema=schema)),
            ),
        )

    def parse(self, response):
        if response["stop_reason"] != "end_turn":
            raise ValueError()
        blocks = response["content"]
        if len(blocks) != 1 or blocks[0]["type"] != "text":
            raise ValueError()
        u = response["usage"]
        cached = u.get("cache_read_input_tokens", 0)
        return json.loads(blocks[0]["text"]), dict(
            input_tokens=u["input_tokens"]
            + cached
            + u.get("cache_creation_input_tokens", 0),
            cached_input_tokens=cached,
            output_tokens=u["output_tokens"],
        )


class GeminiProvider(JSONProvider):
    provider_id, key_env = "gemini-generate-content", "GEMINI_API_KEY"

    def request(self, instruction, payload, schema):
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + quote(self.model, safe="")
            + ":generateContent",
            {"x-goog-api-key": self.api_key},
            dict(
                systemInstruction=dict(parts=[dict(text=instruction)]),
                contents=[
                    dict(
                        role="user",
                        parts=[dict(text=json.dumps(payload, sort_keys=True))],
                    )
                ],
                generationConfig=dict(
                    maxOutputTokens=self.max_output_tokens,
                    responseMimeType="application/json",
                    responseJsonSchema=schema,
                ),
            ),
        )

    def parse(self, response):
        c = response["candidates"]
        if len(c) != 1 or c[0]["finishReason"] != "STOP":
            raise ValueError()
        u = response["usageMetadata"]
        return json.loads("".join(p["text"] for p in c[0]["content"]["parts"])), dict(
            input_tokens=u["promptTokenCount"],
            cached_input_tokens=u.get("cachedContentTokenCount", 0),
            output_tokens=u["candidatesTokenCount"] + u.get("thoughtsTokenCount", 0),
        )
