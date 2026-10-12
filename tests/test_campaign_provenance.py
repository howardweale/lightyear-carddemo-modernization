import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lightyear_mainframe import campaign_provenance as cp
from lightyear_mainframe.legacy_twin import SOURCE_COMMIT


class CampaignProvenanceTests(unittest.TestCase):
 def fixture(self,folder):
  binding={'head':'a'*40,'files':{'source.cbl':'b'*64,'generator.py':'c'*64,'register.json':'d'*64}}
  with patch.object(cp,'current_binding',return_value=binding):cp.begin(folder,'INTCALC')
  for name in cp.RECORDS:(folder/name).write_text('{}')
  after=folder/'public/case/after';after.mkdir(parents=True);(after/'ACCTFILE').write_bytes(b'public baseline output')
  build=folder/'baseline';build.mkdir();(build/'bin').mkdir();(build/'bin/twin').write_bytes(b'public synthetic compiled stand-in')
  receipt=cp.sealed({'source_commit':SOURCE_COMMIT,'run_class':'engineering','files':{'bin/twin':cp.hashlib.sha256((build/'bin/twin').read_bytes()).hexdigest()}})
  (build/'build-receipt.json').write_text(json.dumps(receipt))
  with patch.object(cp,'current_binding',return_value=binding):cp.finish(folder,'INTCALC')
  return binding
 def test_exact_head_and_generator_register_binding_refuse_old_campaign(self):
  with tempfile.TemporaryDirectory() as t:
   folder=Path(t);binding=self.fixture(folder)
   with patch.object(cp,'current_binding',return_value=binding):self.assertEqual('a'*40,cp.validate(folder,'INTCALC')['binding']['head'])
   for changed in ({**binding,'head':'e'*40},{**binding,'files':{**binding['files'],'generator.py':'e'*64}},{**binding,'files':{**binding['files'],'register.json':'e'*64}}):
    with patch.object(cp,'current_binding',return_value=changed):
     with self.assertRaisesRegex(ValueError,'stale-head-or-inputs'):cp.validate(folder,'INTCALC')
   with patch.object(cp,'current_binding',return_value=binding):
    with self.assertRaisesRegex(ValueError,'schema-or-job'):cp.validate(folder,'POSTTRAN')
 def test_retained_results_and_actual_build_bytes_are_revalidated(self):
  with tempfile.TemporaryDirectory() as t:
   folder=Path(t);binding=self.fixture(folder)
   with patch.object(cp,'current_binding',return_value=binding):
    (folder/'mutation-results.json').write_text('[]')
    with self.assertRaisesRegex(ValueError,'retained-artifact-mismatch'):cp.validate(folder,'INTCALC')
    (folder/'mutation-results.json').write_text('{}');(folder/'baseline/bin/twin').write_bytes(b'changed')
    with self.assertRaisesRegex(ValueError,'build artifact mismatch'):cp.validate(folder,'INTCALC')
 def test_diversity_output_tamper_addition_and_removal_are_refused(self):
  with tempfile.TemporaryDirectory() as t:
   folder=Path(t);binding=self.fixture(folder);path=folder/'public/case/after/ACCTFILE';original=path.read_bytes()
   with patch.object(cp,'current_binding',return_value=binding):
    path.write_bytes(b'changed observed value')
    with self.assertRaisesRegex(ValueError,'baseline-output-inventory-mismatch'):cp.validate(folder,'INTCALC')
    path.write_bytes(original);extra=folder/'cases/added/after/ACCTFILE';extra.parent.mkdir(parents=True);extra.write_bytes(b'new observed value')
    with self.assertRaisesRegex(ValueError,'baseline-output-inventory-mismatch'):cp.validate(folder,'INTCALC')
    extra.unlink();path.unlink()
    with self.assertRaisesRegex(ValueError,'baseline-output-inventory-empty'):cp.validate(folder,'INTCALC')
    path.write_bytes(original);self.assertEqual('a'*40,cp.validate(folder,'INTCALC')['binding']['head'])
 def test_followup_refuses_before_creating_outputs_or_invoking_compiler(self):
  from tools.check_equivalence_followup import check
  with tempfile.TemporaryDirectory() as t,patch('tools.check_equivalence_followup.validate_campaign',side_effect=ValueError('campaign-stale-head-or-inputs')),patch('tools.check_equivalence_followup.compiler_output') as compiler:
   with self.assertRaisesRegex(ValueError,'stale-head-or-inputs'):check(Path(t),'INTCALC')
   self.assertFalse((Path(t)/'equivalence-followup').exists());compiler.assert_not_called()

if __name__=='__main__':unittest.main()
