"""New evidence runs independently; existing qualifier remains authoritative."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.ci import p5_drills as drills
from tools.ci import p5_additional_controller_drills as additional


class AdditionalCollectionTests(unittest.TestCase):
    def test_both_collectors_must_pass_and_old_failure_does_not_skip_new_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'public'
            for first,second in ((False,True),(True,False),(False,False),(True,True)):
                with self.subTest(first=first,second=second), patch.dict('os.environ',{'GITHUB_ACTIONS':'true'}), patch('sys.argv',['p5_drills','--output',str(output)]), patch.object(drills,'collect',return_value=first) as old, patch.object(additional,'collect',return_value=second) as new:
                    self.assertEqual(drills.main(),0 if first and second else 1)
                    old.assert_called_once_with(Path.cwd(),output)
                    new.assert_called_once_with(Path.cwd(),output/'additional-controller')

    def test_qualification_neither_collects_nor_substitutes_additional_result(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'public'
            with patch.dict('os.environ',{'GITHUB_ACTIONS':'true'}), patch('sys.argv',['p5_drills','--output',str(output),'--qualify']), patch.object(drills,'qualify',return_value=False) as qualify, patch.object(drills,'collect') as old, patch.object(additional,'collect') as new:
                self.assertEqual(drills.main(),1)
                qualify.assert_called_once_with(output)
                old.assert_not_called();new.assert_not_called()
