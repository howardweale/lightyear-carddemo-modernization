"""Explicit diagnostic exception; never synthesize generation provenance."""
from tools.ms94_b06_admission import check

POLICY = 'diagnostic-unmatched-return-v1'
SPEC = dict(policy=POLICY, empty_pending_only=True, observation_complete=False,
            qualification_credit=False, measurement_credit=False, stop_on_other_anomaly=True)
SCOPE = dict(purpose='capture-with-unmatched-return-exception', qualification_credit=False,
             measurement_credit=False, stop_at_first_anomaly=False, stop_at_first_other_anomaly=True,
             degradation_mode='unmatched-return-only', automatic_retry=False,
             minimum_full_plan_review_lead_seconds=0,
             review_lead_exception='Howard explicitly shortened review lead on 2026-10-10 for 12:30 PM–3:30 PM PDT.',
             unmatched_return=SPEC)

def enabled(spec):
    if 'unmatched_return' not in spec: return False
    check(spec['unmatched_return'] == SPEC and spec.get('observer_binding_v2', {}).get('policy') ==
          'observer-binding-v2', 'diagnostic-unmatched-return-policy')
    return True

def validate_scope(group):
    check(group.get('diagnostic_scope') == SCOPE and group.get('purpose') == 'observer-native-practice' and
          group.get('qualification_credit') is False and group.get('measurement_authorized') is False and
          group.get('model_calls') == 0 and group.get('journey') == 'J1' and group.get('slot_count') == 1,
          'diagnostic-unmatched-return-scope')
    from tools.ms94_b06_admission import utc
    w=group['docker_run_window']
    check(utc(w['not_before_utc']).isoformat() == '2026-10-10T19:30:00+00:00' and
          utc(w['deadline_utc']).isoformat() == '2026-10-10T22:30:00+00:00',
          'diagnostic-review-exception-window')

def validate_event(event, prior):
    check(event.get('policy') == POLICY and event.get('checkpoint') is False and
          event.get('observation_complete') is False and event.get('provenance_created') is False,
          'diagnostic-unmatched-return-event')
    d=prior.get('detail', {})
    check(prior.get('kind') == 'observer-audit' and prior.get('action') == 'jdi-event' and
          d.get('event_type') == 'breakpoint' and d.get('return_breakpoint') is True and
          d.get('selected_generation') is True and d.get('pending') == [] and 'arm' not in d and
          d.get('location') == d.get('top_location'), 'diagnostic-unmatched-return-audit')
    c=event.get('context', {});loc=d['location']
    check(c == dict(thread_id=d['thread_id'],depth=d['depth'],code_index=loc['code_index'],
                    method=loc['class']+'.'+loc['method']+loc['signature']),
          'diagnostic-unmatched-return-context')
