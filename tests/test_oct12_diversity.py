import unittest
from lightyear_mainframe.scenario_generation import case
from lightyear_mainframe.legacy_twin import runtime_clock
from lightyear_mainframe.posttran_invariants import records, require_collation_independent

class OctoberDiversity(unittest.TestCase):
    def test_all_timestamp_cases_satisfy_runtime_clock(self):
        for job in ('INTCALC','POSTTRAN'):
            clocks=set()
            for i in range(200):
                _,meta,_,_=case(f'b1-target:{job}:timestamp:{i:03d}')
                clocks.add(runtime_clock(job,meta)['COB_CURRENT_DATE'])
            self.assertGreater(len(clocks),100)
    def test_runtime_still_refuses_unrepresentable_fraction(self):
        with self.assertRaisesRegex(ValueError,'unsupported deterministic timestamp'):
            runtime_clock('POSTTRAN',{'candidate_timestamp':'2022-06-01-00.00.00.010000'})
    def test_posted_and_rejected_inputs_vary_without_invalid_keys(self):
        for prefix in ('diversity','diversity-reject'):
            rows=[];clock=[]
            for i in (0,1):
                _,meta,images,_=case(f'posttran-{prefix}-{i}')
                require_collation_independent(images)
                rows.append(records(images,'DALYTRAN')[0]);clock.append(runtime_clock('POSTTRAN',meta))
            for field in ('DALYTRAN-CAT-CD','DALYTRAN-MERCHANT-ID','DALYTRAN-PROC-TS','DALYTRAN-SOURCE','DALYTRAN-TYPE-CD'):
                self.assertNotEqual(rows[0][field],rows[1][field],field)
            self.assertNotEqual(clock[0],clock[1])
    def test_account_flags_and_group_inputs_vary(self):
        for job in ('intcalc','posttran'):
            images=[case(f'{job}-diversity-{i}')[2] for i in (0,1)]
            rows=[records(x,'ACCTFILE')[0] for x in images]
            self.assertNotEqual(rows[0]['ACCT-ACTIVE-STATUS'],rows[1]['ACCT-ACTIVE-STATUS'])
            if job=='posttran':self.assertNotEqual(rows[0]['ACCT-GROUP-ID'],rows[1]['ACCT-GROUP-ID'])
