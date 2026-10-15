import hashlib
import json
from pathlib import Path
import unittest
from lightyear_control_tower.factory_policy import validate_contract
DATE = '2026-10-14'  # Immutable historical packet under test.
DECISIONS = ['equivalence-operator-acceptance-2026-10-12.json', 'intcalc-duplicate-category-approval-2026-10-12.json',
    'posttran-phase1-rerun-authorization-2026-10-12.json', 'b06-afternoon-preparation-2026-10-13.json', 'merge-hold-lift-2026-10-14.json']

ROOT=Path(__file__).resolve().parents[1]


class ReleasePacketTests(unittest.TestCase):
    def test_backfill_retains_every_selected_dated_decision_verbatim(self):
        folder=ROOT/'docs/factory'
        old=json.loads((folder/'tower-backfill-request-2026-10-12.json').read_bytes())
        current=json.loads((folder/f'tower-backfill-request-{DATE}.json').read_bytes())
        validate_contract(current)
        self.assertEqual(old['details']['records'],current['details']['records'][:len(old['details']['records'])])
        additions=current['details']['records'][len(old['details']['records']):]
        self.assertEqual(set(DECISIONS),{Path(r['path']).name for r in additions})
        discovered=set()
        for path in folder.glob('*.json'):
            if not any(date in path.name for date in ('2026-10-12','2026-10-13','2026-10-14')):continue
            record=json.loads(path.read_bytes())
            if record.get('schema') in ('factory-scoped-operator-review/1','factory-human-chat-record/1','posttran-phase1-compile-authorization/1') or record.get('decision_id')=='INTCALC-DUPLICATE-CATEGORY-LOADER-DOMAIN' and record.get('approved') is True or 'template_binding_exception' in record:discovered.add(path.name)
        self.assertEqual(discovered,set(DECISIONS))
        for r in additions:self.assertEqual(json.loads((ROOT/r['path']).read_bytes()),r['record'])
        self.assertEqual('signed-factory-decisions-only',current['details']['activation'])
        for source in current['sources']:
            self.assertEqual(source['sha256'],hashlib.sha256((ROOT/source['path']).read_bytes()).hexdigest())

    def test_unsigned_requests_and_no_phase2_claim(self):
        for name in ('intcalc-io-exception-request','scenario-threshold-effective-request'):
            value=json.loads((ROOT/f'docs/factory/{name}-{DATE}.json').read_bytes())
            validate_contract(value);self.assertNotIn('signature',value)
        record=json.loads((ROOT/f'docs/factory/intcalc-releasability-{DATE}.json').read_bytes())
        self.assertFalse(record['release_authorized']);self.assertFalse(record['effective'])
        self.assertEqual(113,len(record['remaining_evidence_gaps']))
        self.assertEqual(3,len(record['programs']['INTCALC']['varying_fields']))
        self.assertEqual(9,len(record['programs']['POSTTRAN']['varying_fields']))
        self.assertEqual([],record['programs']['INTCALC']['incomplete_targets'])
        self.assertEqual([],record['programs']['POSTTRAN']['incomplete_targets'])


if __name__=='__main__':unittest.main()
