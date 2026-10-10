"""Bounded structural JDI diagnostics; never substitutes for provenance replay."""
from lightyear_calibration.contracts import canonical
from tools.ms94_b06_admission import check

POLICY = 'structural-jdi-v1'
MAX_EVENTS = 500000
MAX_BYTES = 128 * 1024 * 1024


class Audit:
    def __init__(self):
        self.count = self.bytes = self.set_id = 0
        self.position = -1
        self.size = 0
        self.resume_requested = self.resumed = self.refused = False
        self.vm_started = False
        self.vm_died = False

    def event(self, event):
        check(not self.refused, 'observer-audit-after-refusal')
        check(event.get('policy') == POLICY and event.get('checkpoint') is False,
              'observer-audit-policy')
        check(set(event) == {'kind','policy','checkpoint','sequence','audit_index',
                            'event_set_id','event_position','action','detail'}, 'observer-audit-fields')
        self.count += 1
        body = {k: v for k, v in event.items() if k not in ('sequence', 'checkpoint')}
        self.bytes += len(canonical(body))
        check(self.count <= MAX_EVENTS and self.bytes <= MAX_BYTES, 'observer-audit-bound')
        check(event['audit_index'] == self.count, 'observer-audit-index')
        action, detail = event['action'], event['detail']
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
