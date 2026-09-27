"""A separately versioned comparison of retained MS89 native observations.

The original judge is rerun on a disposable copy by the assessment command.
This module never changes a candidate, original observation, or old verdict.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

from .contracts import require, seal, verify

POLICY_ID = 'idempiere-partial-invoicing-comparison-v2'
NUMERIC_FIELDS = ('order.discount', 'order.reserved', 'shipment.delivered')
STAGES = ('firstShipment', 'shipment')
STAMP = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$')
DECIMAL = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$')


def exact_decimal(a, b):
    if not all(isinstance(v, str) and len(v) <= 128 and DECIMAL.fullmatch(v) for v in (a, b)):
        return False
    try:
        x, y = Decimal(a), Decimal(b)
        return x.is_finite() and y.is_finite() and x == y
    except InvalidOperation:
        return False


def timestamp(value):
    require(isinstance(value, str) and STAMP.fullmatch(value), 'Unsupported timestamp representation')
    return datetime.fromisoformat(value)


def same_second(a, b):
    try:
        oracle, postgres = timestamp(a), timestamp(b)
        return oracle.microsecond == 0 and oracle == postgres.replace(microsecond=0)
    except ValueError:
        return False


def validate_policy(policy, decision, assessed_on):
    require(policy['id'] == POLICY_ID and policy['version'] == 2, 'Unknown judge version')
    require(policy['numeric_trace_fields'] == list(NUMERIC_FIELDS)
            and policy['timestamp_stages'] == list(STAGES), 'Comparison scope changed')
    require(policy['timestamp_column'] == 'adempiere.m_inout.shipdate'
            and policy['oracle_datatype'] == 'DATE'
            and policy['postgresql_datatype'] == 'timestamp without time zone'
            and policy['capture_session_timezone'] == 'UTC', 'Unsupported datatype or timezone scope')
    require(decision['id'] == policy['timestamp_decision_id'] == 'idempiere-oracle-date-seconds-v1'
            and decision['content_sha256'] == policy['timestamp_decision_sha256'], 'Timestamp decision identity differs')
    require(decision['owner'] == policy['owner'] == 'Howard Weale'
            and decision['decision'] == 'accept-second-level-precision'
            and decision['scope']['columns'] == [policy['timestamp_column']]
            and decision['scope']['oracle_datatype'] == policy['oracle_datatype']
            and decision['scope']['application_source_commit'] == policy['application_source_commit'], 'Timestamp decision scope differs')
    require(date.fromisoformat(decision['effective_date']) <= assessed_on < date.fromisoformat(decision['review_date']),
            'Timestamp decision is not current on the assessment date')


def compare(lanes, effects, original, bindings, context, policy, decision, assessed_on):
    """Apply only named new rules after the original native gates are reproduced."""
    validate_policy(policy, decision, assessed_on)
    verify(effects); verify(original)
    require(set(lanes) == {'oracle', 'postgresql'}, 'Both native lanes are required')
    for lane, value in lanes.items():
        verify(value)
        require(value['lane'] == lane and value['status'] == 'passed-bounded-partial-invoicing-readback'
                and value['evidence_class'] == 'native-application-and-database-observation', 'Native business readback did not pass')
        require(value['state_sha256'] == effects['state_sha256'][lane]
                and value['content_sha256'] == original['lane_receipt_sha256'][lane], 'Lane evidence binding differs')
    require(original['effect_checkpoint_sha256'] == effects['content_sha256'], 'Effect evidence binding differs')
    require(lanes['oracle']['harness_sha256'] == lanes['postgresql']['harness_sha256']
            and lanes['oracle']['invoices'] == lanes['postgresql']['invoices'], 'Native harness or business results differ')
    require(context['oracle_datatype'] == policy['oracle_datatype']
            and context['postgresql_datatype'] == policy['postgresql_datatype']
            and context['capture_session_timezones'] == {'oracle': 'UTC', 'postgresql': 'UTC'},
            'Native datatype or timezone facts do not support the timestamp rule')
    require(context['state_sha256'] == effects['state_sha256'], 'Native context state binding differs')
    require(set(bindings) == set(STAGES), 'Shipment bindings differ')
    traces = {lane: value['trace'] for lane, value in lanes.items()}
    require(set(traces['oracle']) == set(traces['postgresql']), 'Trace field sets differ')
    accepted_rows = []; unresolved_rows = []
    by_key = {}
    for stage in STAGES:
        binding = bindings[stage]
        require(binding['table'] == 'm_inout' and binding['column'] == 'shipdate', 'Timestamp binding escaped scope')
        require(binding['key'] not in by_key, 'Shipment bindings must identify distinct rows')
        by_key[binding['key']] = binding
        require(timestamp(binding['oracle']).microsecond == 0, 'Oracle DATE contains fractional seconds')
        for lane in lanes:
            require(binding[lane+'_id'] == traces[lane][stage+'.id'], 'Trace shipment identity differs')
            require(timestamp(binding[lane]) == timestamp(traces[lane][stage+'.shipDate.readback']),
                    'Trace timestamp differs from native row')
    for finding in effects['unresolved_differences']:
        binding = by_key.get(finding.get('key'))
        allowed = (binding is not None and finding.get('table') == 'm_inout' and finding.get('column') == 'shipdate'
                   and all(finding.get(lane) == binding[lane] for lane in lanes)
                   and same_second(finding['oracle'], finding['postgresql']))
        (accepted_rows if allowed else unresolved_rows).append(
            {**finding, 'rule': decision['id']} if allowed else finding)
    accepted_trace = []; unresolved_trace = []; prior_trace = []
    for finding in original['raw_trace_differences']:
        field = finding['field']
        require(all(finding[lane] == traces[lane][field] for lane in lanes), 'Trace finding differs from observation')
        if finding['rule'] is not None:
            prior_trace.append(finding); continue
        rule = None
        if field in NUMERIC_FIELDS and exact_decimal(finding['oracle'], finding['postgresql']):
            rule = 'exact-decimal-value-v2'
        elif field in [s+'.shipDate.readback' for s in STAGES] and same_second(finding['oracle'], finding['postgresql']):
            rule = decision['id']
        (accepted_trace if rule else unresolved_trace).append({**finding, 'rule': rule})
    # Equal invalid spellings must not bypass validation merely by being equal.
    for field in NUMERIC_FIELDS:
        require(field in traces['oracle'], 'Required numeric trace field is missing')
        if not exact_decimal(traces['oracle'][field], traces['postgresql'][field]):
            if not any(x['field'] == field for x in unresolved_trace):
                unresolved_trace.append({'field':field,'oracle':traces['oracle'][field],
                                         'postgresql':traces['postgresql'][field],'rule':None})
    passed = not unresolved_rows and not unresolved_trace
    return seal({'artifact_type':'lightyear-versioned-native-comparison','judge_version':POLICY_ID,
        'status':'passed-bounded-partial-invoicing-contract-v2' if passed else 'partial-invoicing-v2-review-required',
        'passed':passed,'bounded_partial_invoicing_contract_equivalence':passed,
        'assessment_kind':'retained-native-evidence-reassessment','assessed_on':assessed_on.isoformat(),
        'original_comparison_sha256':original['content_sha256'],'original_status':original['status'],
        'original_bounded_partial_invoicing_equivalence':original['bounded_partial_invoicing_equivalence'],
        'timestamp_decision_sha256':decision['content_sha256'],'timestamp_review_date':decision['review_date'],
        'native_context':context,'shipment_bindings':bindings,
        'newly_admitted_row_differences':accepted_rows,'newly_admitted_trace_differences':accepted_trace,
        'retained_prior_trace_differences':prior_trace,'unresolved_row_differences':unresolved_rows,
        'unresolved_trace_differences':unresolved_trace,'invoices':lanes['oracle']['invoices'],
        'new_model_calls':0,'new_native_executions':0,'application_equivalence':False,
        'schema_equivalence':False,'platform_qualification':False,'independently_attested':False})
