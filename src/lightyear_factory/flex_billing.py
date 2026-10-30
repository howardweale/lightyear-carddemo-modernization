"""Explicit first-run Flex policy; public rate-card facts, not account data."""
from copy import deepcopy
from decimal import Decimal

from .contracts import ContractError, canonical_hash


_POLICY = {
    'schema': 'factory-flex-billing-policy/1',
    'model': 'gpt-5.4-2026-03-05',
    'service_tier': 'flex',
    'api_origin': 'https://api.openai.com/v1',
    'rate_card_url': 'https://developers.openai.com/api/docs/models/gpt-5.4',
    'reasoning_source_url': 'https://developers.openai.com/api/docs/guides/reasoning',
    'flex_source_url': 'https://developers.openai.com/api/docs/guides/flex-processing',
    'rate_card_checked_date': '2026-10-27',
    'currency': 'USD',
    'per_tokens': 1000000,
    'standard_input': '2.50',
    'standard_cached_input': '0.25',
    'standard_output': '15.00',
    'long_context_input_multiplier': '2',
    'long_context_output_multiplier': '1.5',
    'regional_multiplier': '1.10',
    'input_reservation_rate': '5.50',
    'output_reservation_rate': '24.75',
    'reasoning_included_in_output': True,
    'cached_discount_used_for_reservation': False,
    'count_billing_status': 'unknown',
    'count_charge_basis': 'operator-conservative-input-token-rate',
    'billing_final': False,
    'automatic_tier_fallback': False,
}


def flex_billing_policy():
    result = deepcopy(_POLICY)
    result['content_sha256'] = canonical_hash(result)
    return result


def is_flex_billing_policy(policy):
    expected = flex_billing_policy()
    return (type(policy) is dict and policy == expected
            and canonical_hash(policy, {'content_sha256'}) == expected['content_sha256'])


def validate_flex_billing(policy, *, model, input_price, output_price,
                          token_preflight, max_retries, service_tier):
    if (not is_flex_billing_policy(policy) or model != _POLICY['model']
            or service_tier != 'flex' or token_preflight is not True
            or type(max_retries) is not int or max_retries != 0
            or type(input_price) not in (int, float)
            or type(output_price) not in (int, float)
            or Decimal(str(input_price)) != Decimal('5.50')
            or Decimal(str(output_price)) != Decimal('24.75')):
        raise ContractError('factory-flex-billing-binding')
    return deepcopy(policy)


def flex_response_evidence(policy, response):
    if not is_flex_billing_policy(policy):
        raise ContractError('factory-flex-policy-changed')
    # Do not relabel a missing/default/priority response as Flex. Reported usage
    # is retained by the existing physical journal before this check runs.
    if not isinstance(response, dict) or response.get('service_tier') != 'flex':
        raise ContractError('factory-flex-response-tier-mismatch')
    return dict(policy_sha256=policy['content_sha256'],
                rate_card_url=policy['rate_card_url'],
                requested_service_tier='flex', observed_service_tier='flex',
                input_reservation_rate=policy['input_reservation_rate'],
                output_reservation_rate=policy['output_reservation_rate'],
                count_billing_status='unknown', billing_final=False)
