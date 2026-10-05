"""B06 deterministic controller core; native/model adapters are not admitted yet.

There is deliberately no model-launch entry point. This core owns immutable
slot ordering and budgets, and uses the real Tower boundary for authority. A
later executable freeze must bind and qualify the worker and admission adapters.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from lightyear_calibration.contracts import canonical, read_json, require, verify
from lightyear_control_tower.b06 import atomic_new
from tools.ms94_b06_design import LIMITS, TRIAL_LIMITS, calendar_guard, schedule
from tools.ms94_b05_supervisor import HARD_SECONDS, RESERVE_SECONDS

ADMISSIONS = frozenset(('interpreter', 'packages', 'codex_binary', 'tool_runtime', 'client',
                       'snapshot', 'template', 'journey_sections', 'qualifications',
                       'attribution_qualification', 'preflight', 'docker_cleanup'))


class Controller:
    def __init__(self, directory, tower, plan, sign, *, monotonic):
        verify(plan)
        require(plan['schedule'] == schedule(plan['schedule']['seed']), 'B06 schedule differs')
        require(plan['limits'] == LIMITS and plan['trial_limits'] == TRIAL_LIMITS,
                'B06 budget differs')
        require(tower.value['bindings']['plan'] == hashlib.sha256(canonical(plan)).hexdigest(),
                'Tower authorization must bind this exact plan file')
        require(all(tower.value['calendar'][k] == plan['calendar'][k] for k in
                    ('clock_mode','period_end_exclusive_utc','latest_launch_utc')), 'Tower calendar differs')
        require(HARD_SECONDS == TRIAL_LIMITS['seconds'] and RESERVE_SECONDS == 600,
                'B05 finalization-inclusive timing changed')
        self.directory = Path(directory)
        self.tower, self.plan, self.sign, self.monotonic = tower, deepcopy(plan), sign, monotonic
        self.started = None
        self.started_monotonic = None
        self.active = None
        self.finished = []
        self.interruptions = []
        self.retries = 0
        self.void_journeys = {}
        self.calls = self.compilations = 0
        self.next_index = 0
        self.terminal_fault = None

    def event(self, kind, payload):
        folder = self.directory / 'events'
        folder.mkdir(parents=True, exist_ok=True)
        prior = sorted(folder.glob('*.json'))
        require([p.name for p in prior] == [f'{i:06d}.json' for i in range(1,len(prior)+1)],
                'Controller event gap')
        index = len(prior) + 1
        previous = read_json(prior[-1])['content_sha256'] if prior else '0'*64
        atomic_new(folder / f'{index:06d}.json', self.sign({
            'artifact_type': 'ms94-b06-controller-event/1', 'sequence': index,
            'plan_sha256': self.plan['content_sha256'], 'previous_sha256': previous,
            'kind': kind, **payload}))

    def launch(self, proof, key, bound, head, now, admissions, *, builder_context=None):
        require(not (self.directory/'started.json').exists() and self.started is None,
                'B06 cannot restart')
        require(set(admissions) == ADMISSIONS, 'Incomplete launch admissions')
        calendar_guard(self.plan['calendar'], now)
        results = {}
        for name in sorted(ADMISSIONS):
            results[name] = admissions[name]()
            require(results[name] is True, 'B06 admission failed: ' + name)
        from tools.ms94_b06_measurement_admission import builder_gate
        # This direct gate cannot be replaced by a callback returning True.
        results['builder_os_probe'] = builder_gate(self.plan, builder_context)
        # The Tower checks signatures, exact launch bindings and its calendar.
        # No started record exists during interpreter/package/CLI/client checks.
        self.tower.launch(proof, key, bound, head, now, lambda: True)
        self.directory.mkdir(parents=True, exist_ok=True)
        began = self.monotonic()
        atomic_new(self.directory/'started.json', self.sign({
            'artifact_type': 'ms94-b06-controller-start/1', 'at_utc': now.isoformat(),
            'plan_sha256': self.plan['content_sha256'], 'admissions': results,
            'monotonic_start': began, 'maximum_seconds': LIMITS['seconds']}))
        self.started, self.started_monotonic = now, began

    def guard(self, now):
        require(self.terminal_fault is None, 'Controller finalization failed; no next slot')
        require(self.started is not None, 'B06 not admitted')
        calendar_guard(self.plan['calendar'], now, started=self.started)
        require(0 <= self.monotonic()-self.started_monotonic < LIMITS['seconds'],
                'B06 monotonic hard deadline, including pauses')
        self.tower.guard(now)

    def start_next(self, now):
        self.guard(now)
        require(self.active is None and self.tower.value['state'] == 'running', 'Next slot paused or active')
        slots = self.plan['schedule']['slots']
        while self.next_index < len(slots) and slots[self.next_index]['journey'] in self.void_journeys:
            slot = slots[self.next_index]
            self.event('unstarted-void-journey', {'slot': slot, 'decision': self.void_journeys[slot['journey']]})
            self.next_index += 1
        if self.next_index == len(slots): return None
        require(self.calls < LIMITS['calls'] and self.compilations < LIMITS['compilations'], 'No B06 budget')
        remaining = LIMITS['seconds'] - (self.monotonic()-self.started_monotonic)
        require(remaining > RESERVE_SECONDS + 1, 'No trial finalization reserve')
        slot = deepcopy(slots[self.next_index])
        limit = min(HARD_SECONDS, remaining-1)
        self.active = {'slot': slot, 'calls': 0, 'compilations': 0, 'candidate_evaluated': False,
                       'deadline': self.monotonic()+limit, 'work_deadline': self.monotonic()+limit-RESERVE_SECONDS,
                       'provider_attempt': 1}
        self.tower.start_trial({k: slot[k] for k in ('id','journey','phase')}, now)
        self.event('slot-started', self.active)
        return deepcopy(self.active)

    def charge(self, *, calls=0, compilations=0, now):
        self.guard(now)
        require(self.active is not None and self.tower.value['state'] == 'running', 'No live trial')
        require(self.monotonic() < self.active['work_deadline'], 'Finalization reserve reached')
        require(type(calls) is int and type(compilations) is int and calls >= 0 and compilations >= 0,
                'Invalid usage delta')
        require(self.active['calls']+calls <= 5 and self.active['compilations']+compilations <= 3 and
                self.calls+calls <= LIMITS['calls'] and self.compilations+compilations <= LIMITS['compilations'],
                'B06 call or compilation cap')
        self.calls += calls; self.compilations += compilations
        self.active['calls'] += calls; self.active['compilations'] += compilations
        self.event('usage', {'slot_id': self.active['slot']['id'], 'calls': self.calls, 'compilations': self.compilations})
        self.tower.record_usage(self.calls, self.compilations, now)

    def mark_evaluated(self, now):
        self.guard(now)
        require(self.active is not None and self.tower.value['state'] == 'running', 'No live trial')
        require(self.monotonic() < self.active['work_deadline'], 'No time to evaluate candidate')
        self.active['candidate_evaluated'] = True
        self.event('candidate-evaluation-started', {'slot_id': self.active['slot']['id']})

    def provider_interruption(self, now, *, receipt_sha256, review_root, artifacts):
        self.guard(now)
        require(self.active is not None and self.tower.value['state'] == 'running', 'No live provider invocation')
        require(self.monotonic() < self.active['deadline'], 'Interrupted trial hard deadline')
        eligible = not self.active['candidate_evaluated'] and self.retries < 3
        self.active['retry_eligible'] = eligible
        value = {'slot_id': self.active['slot']['id'], 'provider_attempt': self.active['provider_attempt'],
                 'receipt_sha256': receipt_sha256, 'retry_eligible': eligible,
                 'candidate_failure': False, 'verdict': None}
        self.interruptions.append(value)
        self.event('provider-unavailable', value)
        self.tower.request_pause(review_root, artifacts, ['provider-unavailable'], now)
        return eligible

    def retry_provider(self, now):
        # Only a verified Tower continue can put the boundary back in running.
        self.guard(now)
        require(self.tower.value['state'] == 'running' and self.active and
                self.active.get('retry_eligible') is True and self.retries < 3,
                'Provider retry not authorized or exhausted')
        require(self.monotonic() < self.active['work_deadline'], 'Retry cannot reset trial deadline')
        self.retries += 1
        self.active['provider_attempt'] += 1
        self.active['retry_eligible'] = False
        self.event('provider-retry', {'slot_id': self.active['slot']['id'], 'retry_count': self.retries,
                                    'original_deadline': self.active['deadline']})
        return deepcopy(self.active)

    def finish(self, row, now, *, review_root, artifacts):
        self.guard(now)
        require(self.active and self.monotonic() < self.active['deadline'],
                'Trial deadline includes cleanup, signatures, archive and replay')
        require({k: row[k] for k in ('id','journey','phase')} ==
                {k: self.active['slot'][k] for k in ('id','journey','phase')}, 'Wrong terminal trial')
        require(row['state'] != 'provider-unavailable', 'Provider interruption is not a candidate verdict')
        try:
            self.event('trial-finalized', {'trial': row})
            result = self.tower.finish_and_review(row, review_root, artifacts, now)
            # Export/signing/pause publication is part of finalization as well.
            # Retain any already-written verdict on failure, but admit no next slot.
            require(self.monotonic() < self.active['deadline'], 'Finalization exceeded trial deadline')
            self.guard(now)
        except Exception as exc:
            self.terminal_fault = type(exc).__name__
            raise
        self.finished.append(deepcopy(row))
        self.active = None
        self.next_index += 1
        return result

    def void_journey(self, journey, decision_sha256, *, verify_operator_decision):
        require(journey in ('J1','J2','J3') and journey not in self.void_journeys,
                'Invalid journey void')
        require(self.active is None and self.tower.value['state'] == 'paused', 'Void requires between-slot pause')
        require(verify_operator_decision(journey, decision_sha256) is True, 'Unverified journey-void decision')
        self.void_journeys[journey] = decision_sha256
        self.event('journey-void', {'journey': journey, 'decision_sha256': decision_sha256,
                                  'prior_verdicts_rewritten': False, 'other_journeys_void': False})
