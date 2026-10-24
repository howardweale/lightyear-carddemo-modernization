"""Synthetic parser/policy tests; the workflow separately runs real scanners."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from tools import java_analysis as analysis


class JavaAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = 'factory/carddemo-web/service/src/main/java/demo/Rule.java'
        self.sources = {self.path: 'a' * 64}
        self.finding = {'path': self.path, 'rule': 'ExampleRule', 'line': 2}
        self.baseline = {'status': 'reviewed', 'versions': analysis.VERSIONS,
                         'findings': {t: [self.finding] for t in ('checkstyle', 'errorprone', 'spotbugs')}}
        self.reports = {t: {'tool': t, 'versions': analysis.VERSIONS, 'complete': True,
                           'negative_control': True, 'checkout': 'b' * 40, 'findings': [self.finding]}
                        for t in self.baseline['findings']}

    def checkstyle(self, files):
        root = ET.Element('checkstyle')
        for name, errors in files:
            file = ET.SubElement(root, 'file', name=name)
            for rule, line in errors:
                ET.SubElement(file, 'error', source=rule, line=str(line))
        ET.ElementTree(root).write(self.root / 'checkstyle.xml')

    def test_checkstyle_retains_multiplicity_and_requires_every_source(self):
        self.checkstyle([('/checkout/' + self.path, [('ExampleRule', 2), ('ExampleRule', 2)])])
        self.assertEqual([self.finding, self.finding], analysis.parse('checkstyle', self.root, self.sources))
        with self.assertRaisesRegex(ValueError, 'coverage'):
            analysis.parse('checkstyle', self.root, {**self.sources, 'missing.java': 'c' * 64})

    def test_checkstyle_refuses_unknown_and_duplicate_sources(self):
        self.checkstyle([('/outside/Rule.java', [])])
        with self.assertRaisesRegex(ValueError, 'unknown'):
            analysis.parse('checkstyle', self.root, self.sources)
        self.checkstyle([(self.path, []), (self.path, [])])
        with self.assertRaisesRegex(ValueError, 'coverage'):
            analysis.parse('checkstyle', self.root, self.sources)

    def test_errorprone_locations_deduplicate_only_identical_diagnostics(self):
        line = '[WARNING] /checkout/' + self.path + ':[2,7] [ExampleRule] description\n'
        (self.root / 'maven.log').write_text('Compiling 1 source file\n' + line * 2 + 'BUILD SUCCESS\n', encoding='utf-8')
        self.assertEqual([self.finding], analysis.parse('errorprone', self.root, self.sources))
        (self.root / 'maven.log').write_text('BUILD FAILURE\n' + line, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            analysis.parse('errorprone', self.root, self.sources)

    def test_errorprone_clean_report_still_requires_compilation(self):
        (self.root / 'maven.log').write_text('BUILD SUCCESS\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'not-observed'):
            analysis.parse('errorprone', self.root, self.sources)

    def test_spotbugs_refuses_missing_classes_and_missing_locations(self):
        good = '<BugCollection><FindBugsSummary/><BugInstance type="ExampleRule"><SourceLine primary="true" sourcepath="demo/Rule.java" start="2"/></BugInstance></BugCollection>'
        (self.root / 'spotbugs.xml').write_text(good, encoding='utf-8')
        self.assertEqual([self.finding], analysis.parse('spotbugs', self.root, self.sources))
        (self.root / 'spotbugs.xml').write_text(good.replace('<FindBugsSummary/>', '<FindBugsSummary/><MissingClass>Unresolved</MissingClass>'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            analysis.parse('spotbugs', self.root, self.sources)
        (self.root / 'spotbugs.xml').write_text('<BugCollection><FindBugsSummary/><BugInstance type="X"/></BugCollection>', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'missing-location'):
            analysis.parse('spotbugs', self.root, self.sources)

    def test_pending_baseline_is_not_an_empty_approval(self):
        baseline = copy.deepcopy(self.baseline)
        baseline['status'] = 'pending-ci-review'
        with self.assertRaisesRegex(ValueError, 'awaits-review'):
            analysis.gate(self.reports, baseline, {'status': 'absent'})

    def test_reviewed_baseline_allows_removal_but_not_new_or_duplicate_findings(self):
        analysis.gate(self.reports, self.baseline, self.baseline)
        self.reports['checkstyle']['findings'] = []
        analysis.gate(self.reports, self.baseline, self.baseline)
        self.reports['checkstyle']['findings'] = [self.finding] * 2
        with self.assertRaisesRegex(ValueError, 'new-java'):
            analysis.gate(self.reports, self.baseline, self.baseline)

    def test_baseline_cannot_expand_to_absorb_new_findings(self):
        baseline = copy.deepcopy(self.baseline)
        baseline['findings']['spotbugs'].append({**self.finding, 'line': 3})
        with self.assertRaisesRegex(ValueError, 'baseline-expanded'):
            analysis.gate(self.reports, baseline, self.baseline)

    def test_missing_tools_controls_incomplete_or_mixed_checkout_refuse(self):
        bad = copy.deepcopy(self.reports)
        bad.pop('spotbugs')
        with self.assertRaisesRegex(ValueError, 'coverage'):
            analysis.gate(bad, self.baseline, self.baseline)
        for key, value in [('negative_control', False), ('complete', False), ('checkout', 'd' * 40)]:
            with self.subTest(key=key):
                bad = copy.deepcopy(self.reports)
                bad['errorprone'][key] = value
                with self.assertRaises(ValueError):
                    analysis.gate(bad, self.baseline, self.baseline)

    def test_pom_is_disposable_and_keeps_original_configuration(self):
        raw = ('<project xmlns="' + analysis.NS + '"><modelVersion>4.0.0</modelVersion><properties><java.version>21</java.version></properties><build><plugins><plugin><artifactId>original-proof</artifactId><configuration><mutationThreshold>90</mutationThreshold></configuration></plugin></plugins></build></project>').encode()
        original = ET.fromstring(raw)
        for tool in ('checkstyle', 'errorprone', 'spotbugs'):
            with self.subTest(tool=tool):
                tree = ET.fromstring(analysis.analysis_pom(raw, tool, self.root))
                q = lambda name: '{' + analysis.NS + '}' + name
                self.assertEqual(ET.tostring(original.find(q('properties'))), ET.tostring(tree.find(q('properties'))))
                self.assertEqual(ET.tostring(original.find('.//' + q('plugin'))), ET.tostring(tree.find('.//' + q('plugin'))))
                self.assertEqual('90', tree.findtext('.//' + q('mutationThreshold')))
        tree = ET.fromstring(analysis.analysis_pom(raw, 'errorprone', self.root))
        args = [x.text for x in tree.iter('{' + analysis.NS + '}arg')]
        self.assertIn('-Xplugin:ErrorProne -XepAllErrorsAsWarnings', args)
        self.assertFalse(any('Disable' in arg or ':OFF' in arg for arg in args))


if __name__ == '__main__':
    unittest.main()
