"""Opt-in failed-call accounting without changing the historical provider module."""

import json
from typing import Any
from .contracts import ContractError, canonical_hash
from .providers import BoundedModelProvider, ProviderError, ProviderResult


class AccountedModelProvider(BoundedModelProvider):
    """Keep failed/fallback attempts in the existing shared budget and evidence."""

    def complete(
        self,
        role: str,
        instruction: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> ProviderResult:
        if not getattr(self.provider, "manage_failure_budget", False):
            return super().complete(role, instruction, payload, schema)
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
        strict_budget = getattr(self.provider, "manage_failure_budget", False)
        if strict_budget and hasattr(self.provider, "request"):
            _, _, wire_body = self.provider.request(instruction, payload, schema)
            request_bytes = len(
                json.dumps(wire_body, sort_keys=True, separators=(",", ":")).encode()
            )
        if self.input_bytes + request_bytes > self.order.max_model_input_bytes:
            raise ContractError("Model provider exceeded max_model_input_bytes")
        input_price = float(getattr(self.provider, "input_usd_per_million", 0.0))
        output_price = float(getattr(self.provider, "output_usd_per_million", 0.0))
        output_cap = int(getattr(self.provider, "max_output_tokens", 0))
        reserved_input_tokens = (
            (2 * request_bytes + 1024) if strict_budget else request_bytes
        )
        if input_price > 0 and output_price > 0 and output_cap > 0:
            conservative_call_cost = (
                reserved_input_tokens * input_price + output_cap * output_price
            ) / 1_000_000
            if (
                self.estimated_cost_usd + conservative_call_cost
                > self.order.max_model_cost_usd
            ):
                raise ContractError(
                    "Model provider cannot admit call inside max_model_cost_usd"
                )
        if (
            strict_budget
            and self.input_tokens
            + self.output_tokens
            + reserved_input_tokens
            + output_cap
            > self.order.max_model_tokens
        ):
            raise ContractError(
                "Model provider cannot admit call inside max_model_tokens"
            )
        try:
            result = self.provider.complete(role, instruction, payload, schema)
        except (ProviderError, ContractError):
            if strict_budget:
                # A failed call can still be billed. Charge its reserved maximum,
                # retain a call record, and let the controller decide fallback.
                cost = (
                    reserved_input_tokens * input_price + output_cap * output_price
                ) / 1_000_000
                self.input_bytes += request_bytes
                self.input_tokens += reserved_input_tokens
                self.output_tokens += output_cap
                self.estimated_cost_usd += cost
                evidence = dict(
                    evidence_type="lightyear-model-call",
                    provider=self.provider.provider_id,
                    model=self.provider.model,
                    role=role,
                    status="failed",
                    usage="reserved-upper-bound",
                    request_sha256=canonical_hash(
                        {
                            "instruction": instruction,
                            "payload": payload,
                            "schema": schema,
                        }
                    ),
                    call_sequence=len(self.calls) + 1,
                    input_tokens=reserved_input_tokens,
                    output_tokens=output_cap,
                    estimated_cost_usd=cost,
                    cost_estimate_available=True,
                )
                evidence["content_sha256"] = canonical_hash(evidence)
                self.calls.append(evidence)
            raise
        response_bytes = len(
            json.dumps(result.content, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        next_input_tokens = self.input_tokens + int(
            result.evidence.get("input_tokens", 0)
        )
        next_output_tokens = self.output_tokens + int(
            result.evidence.get("output_tokens", 0)
        )
        next_cost = self.estimated_cost_usd + float(
            result.evidence.get("estimated_cost_usd", 0.0)
        )
        next_cost_available = self.cost_estimate_available and bool(
            result.evidence.get("cost_estimate_available", False)
        )
        if strict_budget:
            # Preserve usage even when the provider returned an over-budget or
            # invalid response; a billed attempt never vanishes from evidence.
            charged = dict(
                result.evidence,
                call_sequence=len(self.calls) + 1,
                request_bytes=request_bytes,
                response_bytes=response_bytes,
            )
            charged["content_sha256"] = canonical_hash(charged, {"content_sha256"})
            self.calls.append(charged)
            self.input_bytes += request_bytes
            self.output_bytes += response_bytes
            self.input_tokens, self.output_tokens = (
                next_input_tokens,
                next_output_tokens,
            )
            self.estimated_cost_usd, self.cost_estimate_available = (
                next_cost,
                next_cost_available,
            )
            if (
                self.output_bytes > self.order.max_model_output_bytes
                or next_input_tokens + next_output_tokens > self.order.max_model_tokens
                or next_cost > self.order.max_model_cost_usd
            ):
                raise ContractError("Model provider exceeded admitted budget")
            self._check_elapsed()
            return ProviderResult(result.content, charged)
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
