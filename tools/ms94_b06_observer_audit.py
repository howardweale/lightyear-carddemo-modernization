"""Bounded structural JDI diagnostics; never substitutes for provenance replay."""
from lightyear_calibration.contracts import canonical
from tools.ms94_b06_admission import check

POLICY = 'structural-jdi-v1'
POLICIES = (POLICY, 'structural-jdi-v2')
MAX_EVENTS = 500000
MAX_BYTES = 128 * 1024 * 1024


class Audit:
    def __init__(self, engineering_plan=None):
        self.max_events,self.max_bytes=MAX_EVENTS,MAX_BYTES
        if engineering_plan is not None:
            from tools.ms94_b06_observer_diagnostics import validate
            check(validate(engineering_plan) is not None,"observer-audit-engineering-plan")
            self.max_events=engineering_plan["engineering_limits"]["audit_records"]
            self.max_bytes=engineering_plan["engineering_limits"]["audit_bytes"]
        self.policy = None
        self.diagnostic_count = 0
        self.count = self.bytes = self.set_id = 0
        self.position = -1
        self.size = 0
        self.resume_requested = self.resumed = self.refused = False
        self.vm_started = False
        self.vm_died = False

    def metadata(self, event):
        from tools.ms94_b06_observer_format import java_json, FORMAT, diagnostic_wire
        wire = event; event = diagnostic_wire(event)
        check(event.get('observer_format') == FORMAT and event.get('checkpoint') is False and
              event['kind'] in ('breakpoint-lifecycle','watched-class-prepare','observer-heap-telemetry'),
              'observer-diagnostic-metadata')
        self.diagnostic_count += 1
        self.bytes += len(java_json(wire).encode('utf-8'))
        check(self.diagnostic_count <= self.max_events and self.bytes <= self.max_bytes, 'observer-audit-bound')

    def event(self, event):
        from tools.ms94_b06_observer_format import diagnostic_wire
        wire = event; event = diagnostic_wire(event)
        check(not self.refused, 'observer-audit-after-refusal')
        policy = event.get('policy')
        check(policy in POLICIES and self.policy in (None, policy), 'observer-audit-policy-change')
        self.policy = policy
        bounded = policy == 'structural-jdi-v2'
        check((event.get('observer_format') == 'bounded-observer-v1') if bounded else 'observer_format' not in event, 'observer-audit-format')
        check(event.get('checkpoint') is False,
              'observer-audit-policy')
        fields = {'kind','policy','checkpoint','sequence','audit_index', 'event_set_id','event_position','action','detail'}
        check(set(event) == fields | ({'observer_format'} if bounded else set()), 'observer-audit-fields')
        self.count += 1
        self.diagnostic_count += 1
        body = {k: v for k, v in event.items() if k not in ('sequence', 'checkpoint')}
        if bounded:
            from tools.ms94_b06_observer_format import java_json
            self.bytes += len(java_json(wire).encode('utf-8'))
        else:
            self.bytes += len(canonical(body))
        check(self.diagnostic_count <= self.max_events and self.bytes <= self.max_bytes, 'observer-audit-bound')
        check(event['audit_index'] == self.count, 'observer-audit-index')
        from tools.ms94_b06_observer_format import audit_detail
        action, detail = event['action'], audit_detail(event)['detail']
        if bounded and action == 'jdi-event' and event['event_set_id'] == self.set_id + 1:
            check(event['event_position'] == 0 and (self.set_id == 0 or self.resumed), 'observer-audit-set-order')
            check(type(detail.get('set_size')) is int and 0 < detail['set_size'] <= 10000 and detail.get('suspend_policy') in (0,1,2), 'observer-audit-set-shape')
            self.set_id += 1; self.position = -1; self.size = detail['set_size']
            self.resume_requested = self.resumed = False
        if action == 'event-set-open':
            check(event['event_set_id'] == self.set_id + 1 and event['event_position'] == -1 and
                  (self.set_id == 0 or self.resumed), 'observer-audit-set-order')
            check(type(detail['size']) is int and 0 < detail['size'] <= 10000 and
                  detail['suspend_policy'] in (0, 1, 2), 'observer-audit-set-shape')
            self.set_id += 1
            self.position = -1
            self.size = detail['size']
            self.resume_requested = self.resumed = False
            return
        check(event['event_set_id'] == self.set_id and self.set_id > 0 and not self.resumed,
              'observer-audit-set-mismatch')
        if action == 'jdi-event':
            check(not self.resume_requested and event['event_position'] == self.position + 1 and
                  event['event_position'] < self.size, 'observer-audit-position')
            self.position += 1
            check(detail['event_type'] in ('breakpoint','method-exit','exception','vm-start',
                  'vm-death','vm-disconnect','class-prepare','other') and
                  type(detail['request_id']) is int and detail['request_id'] >= 0,
                  'observer-audit-event-shape')
            if detail['event_type'] == 'vm-start':
                check(not self.vm_started, 'observer-audit-duplicate-start')
                self.vm_started = True
            if detail['event_type'] == 'vm-death': self.vm_died = True
            if 'thread_id' in detail:
                if bounded:
                    check(type(detail.get('pending_count')) is int and 0 <= detail['pending_count'] <= 256 and len(detail['pending']) == min(1,detail['pending_count']), 'observer-audit-pending-summary')
                check(type(detail['depth']) is int and detail['depth'] >= 0 and
                      len(detail['pending']) <= 256 and
                      len(detail['thread_name_sha256']) == 64, 'observer-audit-thread-shape')
                check(detail.get('exceptional_exit') is False if detail['event_type']=='method-exit'
                      else True, 'observer-audit-normal-exit')
            return
        check(event['event_position'] == self.position, 'observer-audit-state-position')
        if action in ('dispatch-completed', 'dispatch-refused'):
            check(not self.resume_requested and self.position >= 0, 'observer-audit-dispatch-order')
            if action == 'dispatch-refused':
                self.refused = True
            else:
                check(len(detail['pending_generation_ids']) <= 256, 'observer-audit-pending-bound')
        elif action == 'event-set-close':
            check(bounded and self.position == self.size - 1 and not self.resume_requested and
                  detail == {'dispatch_completed': self.size, 'resume_requested': 1, 'resume_completed': 1},
                  'observer-audit-close-counters')
            self.resume_requested = self.resumed = True
        elif action == 'resume-requested':
            check(self.position == self.size - 1 and not self.resume_requested,
                  'observer-audit-resume-before-dispatch')
            self.resume_requested = True
        elif action == 'resume-completed':
            check(self.resume_requested, 'observer-audit-unrequested-resume')
            self.resumed = True
        else:
            check(False, 'observer-audit-unknown-action')

    def complete(self):
        check(self.count > 0 and not self.refused and self.vm_started and self.vm_died and
              self.position == self.size - 1, 'observer-audit-incomplete')
