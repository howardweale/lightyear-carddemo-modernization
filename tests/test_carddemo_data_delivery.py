"""Verify that the published bounded review still describes its measured code."""
from hashlib import sha256
import json
from pathlib import Path
import unittest
import subprocess
import tempfile
import copy

MEASURED_BASE="bbec70cf3cb5115faf5059d3eb6b1d326f7a6c11"

from lightyear_control_tower.factory_policy import validate_contract
from lightyear_data.carddemo.plan import build, export

ROOT=Path(__file__).resolve().parents[1]
BASELINE=ROOT/'docs/modernization/carddemo-mapping-baseline-2026-10-18'


def generated_texts(root):
    # CI runs on Windows too: only host newline translation is normalized.
    return {p.relative_to(root).as_posix():p.read_text(encoding='utf-8')
            for p in root.rglob('*') if p.is_file() and p.name!='provenance.json'}


def require_mapping_baseline(plan, baseline=BASELINE):
    with tempfile.TemporaryDirectory() as folder:
        out=Path(folder);export(plan,out)
        expected,actual=generated_texts(baseline),generated_texts(out)
        changed=sorted(k for k in set(expected)|set(actual) if expected.get(k)!=actual.get(k))
        if changed:raise ValueError('generated-mapping-drift:'+','.join(changed))



class DeliveryTests(unittest.TestCase):
    def test_review_request_binds_summary_and_measured_implementation(self):
        request=json.loads((ROOT/'docs/factory/carddemo-data-review-request-2026-10-15.json').read_bytes())
        validate_contract(request)
        source=request['sources'][0];raw=(ROOT/source['path']).read_bytes()
        self.assertEqual(source['sha256'],sha256(raw).hexdigest())
        self.assertEqual(request['details']['packet_sha256'],source['sha256'])
        evidence=json.loads(raw);binding=evidence['summary']
        raw=(ROOT/binding['path']).read_bytes()
        self.assertEqual(binding['sha256'],sha256(raw).hexdigest())
        summary=json.loads(raw);digest=summary.pop('content_sha256')
        self.assertEqual(digest,sha256(json.dumps(summary,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.assertFalse(summary['release_authorized'])
        self.assertEqual('indeterminate',summary['measured']['verdict'])
        for path,digest in summary['measured']['implementation_files'].items():
            self.assertEqual(digest,sha256(subprocess.check_output(['git','show',MEASURED_BASE+':'+path],cwd=ROOT)).hexdigest(),path)
        binding=summary['evidence_index']
        self.assertEqual(binding['sha256'],sha256((ROOT/binding['path']).read_bytes()).hexdigest())

    def test_committed_generated_mapping_matches_pinned_source(self):
        plan,_=build(ROOT/'spec/modernization/carddemo-data')
        retained=json.loads((ROOT/'docs/modernization/carddemo-data-2026-10-15/plan.json').read_bytes())
        historical=subprocess.check_output(['git','show',MEASURED_BASE+':docs/modernization/carddemo-data-2026-10-15/plan.json'],cwd=ROOT)
        self.assertEqual(retained,json.loads(historical))
        self.assertEqual(plan['upstream'],retained['upstream'])
        self.assertEqual([m['table'] for m in plan['mappings']],[m['table'] for m in retained['mappings']])
        self.assertNotEqual(plan['content_sha256'],retained['content_sha256'])
        self.assertIn('field_policy_sha256',plan)
        require_mapping_baseline(plan)

    def test_baseline_archive_members_retain_exact_bytes(self):
        manifest=json.loads((BASELINE/'provenance.json').read_bytes())
        self.assertEqual(set(manifest['files']),set(generated_texts(BASELINE)))
        for name,binding in manifest['files'].items():
            raw=(BASELINE/name).read_bytes()
            self.assertEqual(binding['sha256'],sha256(raw).hexdigest(),name)
            self.assertEqual(binding['bytes'],len(raw),name)

    def test_mapping_guard_catches_field_change_with_same_table_inventory(self):
        plan=json.loads((BASELINE/'plan.json').read_bytes())
        changed=copy.deepcopy(plan)
        # A field property changes while every table name and upstream pin stays fixed.
        changed['mappings'][0]['fields'][0]['length'] += 1
        with self.assertRaisesRegex(ValueError,'generated-mapping-drift:'):
            require_mapping_baseline(changed)

    def test_mapping_guard_catches_changed_ddl_and_missing_mapping(self):
        plan=json.loads((BASELINE/'plan.json').read_bytes())
        import shutil
        with tempfile.TemporaryDirectory() as folder:
            baseline=Path(folder)/'baseline';shutil.copytree(BASELINE,baseline)
            target=baseline/'mapping/acctdata.sql'
            target.write_text(target.read_text()+'-- changed schema\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'mapping/acctdata.sql'):
                require_mapping_baseline(plan,baseline)
            target.write_bytes((BASELINE/'mapping/acctdata.sql').read_bytes())
            (baseline/'mapping/custdata.json').unlink()
            with self.assertRaisesRegex(ValueError,'mapping/custdata.json'):
                require_mapping_baseline(plan,baseline)


if __name__=='__main__':unittest.main()
