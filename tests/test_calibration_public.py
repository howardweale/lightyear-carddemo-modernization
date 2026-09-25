"""Retained measurement integrity plus opt-in full pinned source reproduction."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from lightyear_calibration.adapters import gate_identity,scan
from lightyear_calibration.contracts import verify,read_json
from lightyear_calibration.instrument import build_report

ROOT=Path(__file__).resolve().parents[1]


class CalibrationPublicationTests(unittest.TestCase):
    def test_published_counts_are_bound_to_current_gate_and_retained_baseline(self):
        m=read_json(ROOT/'docs/calibration/idempiere/measurement.json');verify(m)
        baseline=read_json(ROOT/'factory/idempiere-divergence-audit/stage2-comparison.json')
        self.assertEqual(baseline['content_sha256'],m['retained_report_sha256'])
        self.assertEqual(gate_identity('oracle-postgresql-sql'),m['gate'])
        self.assertEqual(baseline['statistics']['coverage_combined'],m['counts']['before'])
        self.assertEqual(111293,m['counts']['after']['sql_units'])
        self.assertEqual(780,m['counts']['after']['parsed-and-compared'])
        self.assertEqual(1405,m['counts']['after']['unparsed'])
        self.assertEqual(4,len(m['changed_decisions']))
        self.assertEqual([],m['lost_decisions_or_divergences'])
        self.assertEqual(115420,sum(t['units'] for t in m['unit_transitions']))
        self.assertFalse(m['native_execution']);self.assertFalse(m['application_equivalence'])
        self.assertEqual(0,m['schema_session_inventory']['verified_sessions'])

    def test_synthetic_context_lift_keeps_a_mismatch_and_an_unknown(self):
        base=ROOT/'spec/calibration/context';manifest=read_json(base/'corpus.json')
        before=build_report(scan(manifest,base))
        after=build_report(scan(manifest,base,context=read_json(base/'baseline.json')))
        self.assertEqual((0,4),(before['summary']['decided_units'],after['summary']['decided_units']))
        self.assertEqual({'equivalent','divergent','indeterminate'},{c['verdict'] for c in after['cases']})

    def test_replay_rejects_wrong_source_before_publishing(self):
        from lightyear_calibration.replay import replay_idempiere
        from lightyear_calibration.contracts import CalibrationError
        manifest=read_json(ROOT/'factory/idempiere-divergence-audit/pairing-manifest.json')
        retained=read_json(ROOT/'factory/idempiere-divergence-audit/stage2-comparison.json')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'source';root.mkdir()
            first=sorted(manifest['pairs'],key=lambda p:p['pair_id'])[0]
            path=root/first['oracle']['path'];path.parent.mkdir(parents=True);path.write_text('SELECT wrong_source;')
            out=Path(temp)/'out'
            with self.assertRaisesRegex(CalibrationError,'Pinned source hash mismatch'):
                replay_idempiere(root,retained,manifest,out)
            self.assertFalse(out.exists())

    @unittest.skipUnless(os.environ.get('IDEMPIERE_SOURCE'),'set IDEMPIERE_SOURCE to replay the pinned corpus')
    def test_full_pinned_replay_reproduces_published_measurement(self):
        from lightyear_calibration.replay import replay_idempiere
        with tempfile.TemporaryDirectory() as temp:
            actual=replay_idempiere(Path(os.environ['IDEMPIERE_SOURCE']),
                read_json(ROOT/'factory/idempiere-divergence-audit/stage2-comparison.json'),
                read_json(ROOT/'factory/idempiere-divergence-audit/pairing-manifest.json'),Path(temp)/'out')
        self.assertEqual(read_json(ROOT/'docs/calibration/idempiere/measurement.json'),actual)
