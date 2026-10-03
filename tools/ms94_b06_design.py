"""Prospective B06 schedule, calendar and analysis; never invokes a model."""
import hashlib
import re
from datetime import datetime, timedelta, timezone

from lightyear_calibration.contracts import canonical, require, seal, verify
from lightyear_control_tower.campaign_observer import wilson

JOURNEYS = ('J1', 'J2', 'J3')
LIMITS = {'calls': 390, 'compilations': 234, 'seconds': 96 * 3600}
TRIAL_LIMITS = {'calls': 5, 'compilations': 3, 'seconds': 7190}


def schedule(seed):
    """Hash-sort each block, avoiding dependence on Python's RNG version."""
    require(isinstance(seed, str) and re.fullmatch('[0-9a-f]{64}', seed), 'Invalid B06 seed')
    rows = [{'id': f'{j.lower()}-pilot-{n:02d}', 'journey': j, 'phase': 'pilot',
             'block': None, 'number': n}
            for n in (1, 2) for j in JOURNEYS]
    for block in range(1, 25):
        order = sorted(JOURNEYS, key=lambda j: hashlib.sha256(
            canonical({'seed': seed, 'block': block, 'journey': j})).digest())
        rows.extend({'id': f'{j.lower()}-cohort-{block:02d}', 'journey': j,
                     'phase': 'cohort', 'block': block, 'number': block} for j in order)
    return seal({'artifact_type': 'ms94-b06-schedule/1', 'seed': seed,
                 'algorithm': 'sha256-canonical-seed-block-journey-sort-v1', 'slots': rows})


def calendar(now, scenario_date):
    require(now.tzinfo is not None, 'Timezone required')
    now = now.astimezone(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    scenario = datetime.strptime(scenario_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    require(start <= scenario < end, 'J1 scenario dates must remain in this accounting period')
    value = seal({'artifact_type': 'ms94-b06-calendar/1', 'clock_mode': 'unmodified-real-time',
                  'frozen_at_utc': now.isoformat(), 'scenario_date': scenario_date,
                  'period_start_utc': start.isoformat(), 'period_end_exclusive_utc': end.isoformat(),
                  'maximum_seconds': LIMITS['seconds'],
                  'latest_launch_utc': (end - timedelta(seconds=LIMITS['seconds'] + 1)).isoformat(),
                  'j1_work_order_unchanged': True})
    calendar_guard(value, now)
    return value


def calendar_guard(value, now, started=None):
    verify(value)
    require(now.tzinfo is not None, 'Timezone required')
    now = now.astimezone(timezone.utc)
    require(value['clock_mode'] == 'unmodified-real-time' and value['maximum_seconds'] == LIMITS['seconds'],
            'B06 calendar policy differs')
    end = datetime.fromisoformat(value['period_end_exclusive_utc'])
    require(datetime.fromisoformat(value['frozen_at_utc']) <= now < end, 'Outside frozen UTC period')
    if started is None:
        require(now <= datetime.fromisoformat(value['latest_launch_utc']) and
                now + timedelta(seconds=LIMITS['seconds']) < end, 'Latest B06 launch exceeded')
    else:
        require(started.tzinfo is not None and started <= now, 'Invalid campaign start')
        require(started <= datetime.fromisoformat(value['latest_launch_utc']) and
                started + timedelta(seconds=LIMITS['seconds']) < end, 'Unsafe original launch')
        require((now - started).total_seconds() < LIMITS['seconds'], 'B06 hard deadline including pauses')


def analysis(rows, *, void_journeys=()):
    """Only complete 24-slot journeys can support the preregistered headline."""
    require(set(void_journeys) <= set(JOURNEYS), 'Unknown void journey')
    require(len({r['id'] for r in rows}) == len(rows), 'Duplicate trial')
    for row in rows:
        require(row['journey'] in JOURNEYS and row['phase'] in ('pilot', 'cohort') and
                type(row['passed']) is bool and type(row['first_try_passed']) is bool and
                (not row['first_try_passed'] or row['passed']), 'Invalid verdict')
        require(row['number'] in range(1, 3 if row['phase'] == 'pilot' else 25), 'Invalid trial number')
        require(row['id'] == f"{row['journey'].lower()}-{row['phase']}-{row['number']:02d}", 'Trial identity differs')
    output = {}
    for journey in JOURNEYS:
        cohort = [r for r in rows if r['journey'] == journey and r['phase'] == 'cohort']
        passed = sum(r['passed'] for r in cohort)
        first = sum(r['first_try_passed'] for r in cohort)
        void = journey in void_journeys
        output[journey] = {'completed': len(cohort), 'planned': 24, 'final_passes': passed,
                           'first_try_passes': first, 'void': void,
                           'final_rate': passed / len(cohort) if cohort and not void else None,
                           'wilson_95': wilson(passed, len(cohort)) if cohort and not void else None,
                           'first_try_wilson_95': wilson(first, len(cohort)) if cohort and not void else None,
                           'interim': len(cohort) != 24}
    complete = all(v['completed'] == 24 and not v['void'] for v in output.values())
    successes = sum(v['final_passes'] for v in output.values())
    return seal({'artifact_type': 'ms94-b06-primary-analysis/1', 'journeys': output,
                 'headline_supported': complete and all(v['final_passes'] >= 21 for v in output.values()),
                 'headline_threshold': 'Every journey at least 21/24; 69.0% is the rounded Wilson lower bound.',
                 'j3_always_counts': True, 'pilots_excluded': True, 'pooling': False,
                 'comparison_with_b03_b05': 'descriptive only',
                 'combined': {'label': 'combined, equal weight by design',
                              'rate': successes / 72 if complete else None,
                              'wilson_95': wilson(successes, 72) if complete else None},
                 'review': 'Operator review; not independent'})
