"""CI-only strict profile and paired mutation comparison refusal fixtures."""
from pathlib import Path
import shutil
import tempfile
import unittest
from tools import carddemo_proof_profiles as profiles

ROOT = Path(__file__).resolve().parents[1]


class ProofProfileTests(unittest.TestCase):
    def test_all_four_profiles_keep_threshold_and_nonempty_gate(self):
        for group in profiles.GROUPS:
            text = profiles.profile_pom(ROOT, group)
            self.assertIn('<mutationThreshold>90</mutationThreshold>', text)
            self.assertIn('<failWhenNoMutations>true</failWhenNoMutations>', text)
            self.assertIn('supplemental-tests/' + group + '/java', text)
            self.assertNotIn('<profiles>', text)

    def test_default_build_extra_pom_unknown_profile_and_activation_refuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); service = root / profiles.SERVICE; service.mkdir(parents=True)
            original = (ROOT / profiles.SERVICE / 'pom.xml').read_text(encoding='utf-8')
            path = service / 'pom.xml'
            for text in (original.replace('<java.version>21', '<java.version>17', 1),
                         original.replace('<id>proof-map</id>', '<id>unreviewed</id>', 1),
                         original.replace('<id>proof-map</id>', '<id>proof-map</id><activation/>', 1)):
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError):profiles.baseline_pom(root)
            path.write_text(original, encoding='utf-8')
            (service / 'other-proof.pom.xml').write_text('<project/>', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'separate-proof-pom'):
                profiles.baseline_pom(root)

    def test_inheritance_cannot_be_silently_merged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); service = root / profiles.SERVICE; service.mkdir(parents=True)
            text = (ROOT / profiles.SERVICE / 'pom.xml').read_text(encoding='utf-8')
            (service / 'pom.xml').write_text(text.replace(' combine.self="override"', '', 1), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'inheritance'):
                profiles.profile_pom(root, 'map')

    def test_counts_detect_class_status_and_denominator_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); old = root / 'old.xml'; new = root / 'new.xml'
            row = '<mutation status="KILLED"><mutatedClass>A</mutatedClass></mutation>'
            old.write_text('<mutations>' + row + '</mutations>', encoding='utf-8')
            expected = profiles.mutation_counts(old)
            for content in (row.replace('KILLED', 'TIMED_OUT'), row.replace('>A<', '>B<'), row + row):
                new.write_text('<mutations>' + content + '</mutations>', encoding='utf-8')
                self.assertNotEqual(expected, profiles.mutation_counts(new))
            new.write_text('<mutations/>', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'empty'):
                profiles.mutation_counts(new)

    def test_effective_configuration_change_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); old = root / 'old.xml'; new = root / 'new.xml'
            xml = '<project xmlns="http://maven.apache.org/POM/4.0.0"><build><plugins><plugin><artifactId>pitest-maven</artifactId><configuration><mutationThreshold>90</mutationThreshold></configuration></plugin></plugins></build></project>'
            old.write_text(xml, encoding='utf-8'); new.write_text(xml.replace('>90<', '>89<'), encoding='utf-8')
            self.assertNotEqual(profiles.effective_build(old, root), profiles.effective_build(new, root))
