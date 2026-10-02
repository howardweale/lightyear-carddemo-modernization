"""B05 preregistration checks only. This module cannot call a model or launch a trial."""
from datetime import datetime, timedelta, timezone
from lightyear_calibration.contracts import require, verify

MAX_SECONDS = 26 * 3600
PERIOD_START = datetime(2026, 10, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 11, 1, tzinfo=timezone.utc)


def period_guard(now, *, launching=False):
    require(now.tzinfo is not None, 'Real UTC timestamp required')
    now = now.astimezone(timezone.utc)
    require(PERIOD_START <= now < PERIOD_END, 'Outside October accounting period')
    # Preserve the qualified rolling full-duration check, with B05's 26-hour cap.
    require(now + timedelta(seconds=MAX_SECONDS) < PERIOD_END,
            'Full declared campaign duration could cross period boundary')
    if launching:
        # Leave 26 hours before the rolling guard itself can stop continuation.
        require(now + timedelta(seconds=2 * MAX_SECONDS) < PERIOD_END,
                'Full campaign duration could encounter the rolling guard cutoff')
    return now


def check_plan(plan):
    verify(plan)
    require(plan['measurement']=='B05' and plan['b04_status']=='VOID', 'Wrong measurement')
    require([(s['phase'],s['index']) for s in plan['slots']] ==
            [('pilot',i) for i in range(1,4)]+[('cohort',i) for i in range(1,21)], 'Wrong fixed slots')
    require(plan['limits']=={'client_invocations':115,'compilations':69,'elapsed_seconds':MAX_SECONDS,
                            'per_trial_client_invocations':5,'per_trial_compilations':3,'per_trial_elapsed_seconds':7200,
                            'per_client_timeout_seconds':1800}, 'Budgets changed')
    require(plan['calendar']['scenario_date']=='2026-10-01' and
            plan['calendar']['clock_mode']=='unmodified-real-time', 'Calendar policy changed')
    require(plan['analysis']['primary']['denominator']==20 and plan['analysis']['pilots_excluded']
            and plan['analysis']['pool_with_b03'] is False, 'Analysis changed')
    require(plan['model_calls_authorized'] is False and plan['execution_authorized'] is False,
            'Preregistration must not authorize execution')
    return plan


def require_launch_authorization(plan, authorization=None):
    check_plan(plan)
    # There is deliberately no model-calling B05 runtime or authorization path here.
    # A later approved exact execution freeze must be verified before this gate is replaced.
    raise ValueError('B05 is preregistered only: fresh user approval and a separately verified public execution freeze are required')
