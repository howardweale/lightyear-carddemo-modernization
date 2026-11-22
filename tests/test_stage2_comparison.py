import unittest
from unittest.mock import Mock, patch

from tools import intcalc_stage2_comparison as b


def case(i=0,abend=False):
    return dict(sequence=i,inputs={k:"0123" for k in b.receiver.writer.FIELDS},
                timestamp="2030-01-01-12.00.00.910000",processing_date="2030010100",
                outputs=dict(ACCTFILE="" if abend else "ab",TRANSACT="",stdout="42",stderr=""),
                exit=12 if abend else 0,compare_output_files=not abend)


def output():
    return dict(ACCTFILE=b"\xab",TRANSACT=b"",stdout=b"B",stderr=b"",exit=0,timed_out=False,output_capped=False)


class ComparatorTests(unittest.TestCase):
    def run_cases(self,rows,worker):
        return b.compare_all([b.receiver.writer.canonical(r) for r in rows],worker,2,clock=lambda:1)

    def test_complete_match_returns_only_status(self):
        run=Mock(return_value=output())
        self.assertEqual(b.aggregate(self.run_cases([case()],run)),{"status":"PASS"})
        inputs,stamp,date,end=run.call_args.args
        self.assertEqual(inputs,{k:b"\x01#" for k in b.receiver.writer.FIELDS})
        self.assertEqual((stamp,date,end),(case()["timestamp"],case()["processing_date"],2))

    def test_all_cases_run_after_first_difference(self):
        run=Mock(side_effect=[dict(output(),stdout=b"WRONG"),output(),output()])
        self.assertEqual(b.aggregate(self.run_cases([case(i) for i in range(3)],run)),{"status":"FAIL"})
        self.assertEqual(run.call_count,3)

    def test_missing_is_different_from_empty(self):
        self.assertFalse(b.matches(dict(output(),TRANSACT=None),case()))

    def test_abend_compares_only_streams_and_exit(self):
        obs=dict(output(),ACCTFILE=None,TRANSACT=b"uncommitted",exit=12)
        self.assertTrue(b.matches(obs,case(abend=True)))
        for replacement in (dict(stderr=b"unexpected"),dict(exit=0),dict(stdout=b"")):
            self.assertFalse(b.matches(dict(obs,**replacement),case(abend=True)))

    def test_timeout_and_cap_are_candidate_failure(self):
        for key in ("timed_out","output_capped"):
            self.assertFalse(b.matches(dict(output(),**{key:True}),case()))

    def test_infrastructure_fault_after_mismatch_refuses(self):
        run=Mock(side_effect=[dict(output(),exit=3),RuntimeError("PRIVATE CANARY")])
        with self.assertRaisesRegex(b.Refused,"^stage2-comparison-refused$"):
            self.run_cases([case(),case(1)],run)

    def test_extra_field_and_noninteger_exit_refuse(self):
        for obs in (dict(output(),log="private"),dict(output(),exit=False),dict(output(),stdout=None),
                    dict(output(),stderr=b"a"*(b.OUTPUT_BYTES+1))):
            with self.assertRaises(ValueError):
                b.matches(obs,case())

    def test_validate_entire_order_before_first_case(self):
        run=Mock()
        with self.assertRaises(ValueError):
            self.run_cases([case(),case(0)],run)
        run.assert_not_called()

    def test_no_case_or_expired_deadline_refuses(self):
        run=Mock()
        for rows in ([],[b.receiver.writer.canonical(case())]):
            with self.assertRaises(ValueError):
                b.compare_all(rows,run,1,clock=lambda:1)
        run.assert_not_called()

    def test_public_receipt_rejects_truthy_status(self):
        for v in (1,"PASS",{},None):
            with self.assertRaises(ValueError):
                b.aggregate(v)

    def test_production_refuses_before_admission_and_decryption(self):
        with patch.object(b.admission,"run_once") as once:
            for call in (lambda:b.evaluate_private(None,None,None,None,None),
                         lambda:b.PrivateEvaluator().preflight(None),
                         lambda:b.PrivateEvaluator().compare([],None,1)):
                with self.assertRaisesRegex(b.Refused,"^stage2-private-clock-route-unqualified$"):
                    call()
            once.assert_not_called()
