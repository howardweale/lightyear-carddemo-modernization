from datetime import datetime, timedelta, timezone
import unittest
from tools.ms94_b05_plan import period_guard, PERIOD_END, MAX_SECONDS, check_plan, require_launch_authorization
from lightyear_calibration.contracts import seal


def prospective_plan(**updates):
    return seal({'measurement':'B05','b04_status':'VOID',
        'slots':[{'phase':p,'index':i} for p,n in [('pilot',3),('cohort',20)] for i in range(1,n+1)],
        'limits':{'client_invocations':115,'compilations':69,'elapsed_seconds':93600,
                  'per_trial_client_invocations':5,'per_trial_compilations':3,'per_trial_elapsed_seconds':7200,'per_client_timeout_seconds':1800},
        'calendar':{'scenario_date':'2026-10-01','clock_mode':'unmodified-real-time'},
        'analysis':{'primary':{'denominator':20},'pilots_excluded':True,'pool_with_b03':False},
        'model_calls_authorized':False,'execution_authorized':False,**updates})


class PeriodGuardTests(unittest.TestCase):
    def test_current_period_launch_fits(self):
        period_guard(datetime(2026,10,2,tzinfo=timezone.utc),launching=True)

    def test_full_duration_launch_boundary(self):
        cutoff=PERIOD_END-timedelta(seconds=2*MAX_SECONDS)
        period_guard(cutoff-timedelta(seconds=1),launching=True)
        with self.assertRaises(ValueError):period_guard(cutoff,launching=True)

    def test_continuation_boundary(self):
        cutoff=PERIOD_END-timedelta(seconds=MAX_SECONDS)
        period_guard(cutoff-timedelta(seconds=1))
        with self.assertRaises(ValueError):period_guard(cutoff)

    def test_entire_latest_campaign_retains_guard_margin(self):
        latest=PERIOD_END-timedelta(seconds=2*MAX_SECONDS+1)
        for hours in range(27):period_guard(latest+timedelta(hours=hours))

    def test_real_timezone_normalized(self):
        period_guard(datetime(2026,10,29,12,59,59,tzinfo=timezone(timedelta(hours=-7))),launching=True)
        with self.assertRaises(ValueError):
            period_guard(datetime(2026,10,29,13,tzinfo=timezone(timedelta(hours=-7))),launching=True)

    def test_outside_period_or_naive_rejected(self):
        for value in (datetime(2026,9,30,tzinfo=timezone.utc),PERIOD_END,datetime(2026,10,2)):
            with self.assertRaises(ValueError):period_guard(value)

    def test_preregistration_never_launches_even_with_supplied_approval(self):
        plan=prospective_plan();check_plan(plan)
        for approval in (None,{'execution_authorized':True,'operator_approval':'approved'}):
            with self.assertRaises(ValueError):require_launch_authorization(plan,approval)

    def test_plan_cannot_authorize_models_or_pool_results(self):
        for changes in ({'model_calls_authorized':True},{'execution_authorized':True},
                        {'analysis':{'primary':{'denominator':20},'pilots_excluded':True,'pool_with_b03':True}}):
            with self.assertRaises(ValueError):check_plan(prospective_plan(**changes))


if __name__=='__main__':unittest.main()
