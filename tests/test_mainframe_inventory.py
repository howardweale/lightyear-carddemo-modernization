from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from lightyear_mainframe.inventory import coverage, inventory, scan
from lightyear_mainframe.source import Corpus, SourceError, tokenize


def cobol(*lines):
    return '\n'.join('       '+line for line in lines)+'\n'


def decisions(*lines):
    return scan(tokenize(cobol('PROCEDURE DIVISION.', *lines)), 'TEST')


class DecisionTests(unittest.TestCase):
    def test_nested_if_counts_false_even_without_else(self):
        found, issues, _ = decisions('IF A = 1', 'IF B = 2 CONTINUE ELSE CONTINUE END-IF', 'END-IF.')
        self.assertEqual([], issues)
        self.assertEqual(['if', 'if'], [d['kind'] for d in found])
        self.assertEqual(4, sum(len(d['outcomes']) for d in found))
        self.assertEqual(['true', 'false'], [o['label'] for o in found[0]['outcomes']])

    def test_literals_comments_identifiers_and_exec_do_not_inflate(self):
        text = cobol('PROCEDURE DIVISION.', "DISPLAY 'IF EVALUATE WHEN PERFORM'.", 'IF-NAME.',
                     'EXEC SQL SELECT CASE WHEN A = 1 THEN 2 END', 'END-EXEC.',
                     "IF X = 'a.b' CONTINUE END-IF. *> IF A CONTINUE")
        text += '      * IF B CONTINUE\n'
        found, issues, opaque = scan(tokenize(text), 'TEST')
        self.assertEqual(['if'], [d['kind'] for d in found])
        self.assertEqual([], issues)
        self.assertEqual('embedded-sql', opaque[0]['kind'])

    def test_nested_evaluate_and_implicit_no_match(self):
        found, issues, _ = decisions('EVALUATE A', 'WHEN 1 WHEN 2',
                                    'EVALUATE B WHEN 3 CONTINUE WHEN OTHER CONTINUE',
                                    'END-EVALUATE', 'END-EVALUATE.')
        self.assertEqual([], issues)
        self.assertEqual(['when-1', 'when-2', 'no-match'], [o['label'] for o in found[0]['outcomes']])
        self.assertEqual(['when-1', 'other'], [o['label'] for o in found[1]['outcomes']])

    def test_period_closes_evaluate(self):
        found, issues, _ = decisions('EVALUATE A WHEN 1 CONTINUE.', 'IF A CONTINUE END-IF.')
        self.assertEqual([], issues)
        self.assertEqual(2, len(found[0]['outcomes']))

    def test_loop_conditions_and_test_after(self):
        found, issues, _ = decisions('PERFORM WITH TEST AFTER UNTIL X > 9', 'CONTINUE END-PERFORM.',
                                    'PERFORM VARYING I FROM 1 BY 1 UNTIL I > 3',
                                    'AFTER J FROM 1 BY 1 UNTIL J > 4', 'CONTINUE END-PERFORM.',
                                    'PERFORM 3 TIMES CONTINUE END-PERFORM.', 'PERFORM PARA-1.')
        self.assertEqual([], issues)
        self.assertEqual(4, len(found))
        self.assertEqual('after', found[0]['test_position'])
        self.assertEqual('perform-times', found[-1]['kind'])

    def test_exception_pair_is_one_decision(self):
        found, issues, _ = decisions('READ ACCT INVALID KEY MOVE 1 TO FLAG',
                                    'NOT INVALID KEY MOVE 0 TO FLAG END-READ.',
                                    'READ NEXTFILE AT END CONTINUE END-READ.',
                                    'COMPUTE X = 3 ON SIZE ERROR CONTINUE',
                                    'NOT ON SIZE ERROR CONTINUE END-COMPUTE.')
        self.assertEqual([], issues)
        self.assertEqual(['invalid-key', 'at-end', 'on-size-error'], [d['kind'] for d in found])
        self.assertEqual([False, True], [h['negative'] for h in found[0]['handlers']])
        self.assertEqual(6, sum(len(d['outcomes']) for d in found))

    def test_optional_handler_words_and_nested_search_read(self):
        found, issues, _ = decisions('READ F END CONTINUE NOT END CONTINUE END-READ.',
                                    'ADD 1 TO X SIZE ERROR CONTINUE END-ADD.',
                                    'SEARCH T AT END CONTINUE',
                                    'WHEN A READ F AT END CONTINUE END-READ END-SEARCH.')
        self.assertEqual([], issues)
        self.assertEqual(['at-end', 'on-size-error', 'search', 'at-end'], [d['kind'] for d in found])
        self.assertEqual(2, len(found[0]['handlers']))

    def test_search_declared_selection_and_exhaustion(self):
        found, issues, _ = decisions('SEARCH ALL T AT END CONTINUE', 'WHEN T(I) = A CONTINUE END-SEARCH.')
        self.assertEqual([], issues)
        self.assertEqual(1, len(found))
        self.assertEqual(['when-1', 'exhausted'], [o['label'] for o in found[0]['outcomes']])

    def test_alter_union_and_go_depending_fallthrough(self):
        found, issues, _ = decisions('ALTER DISPATCH TO PROCEED TO SECOND.',
                                    'DISPATCH.', 'GO TO FIRST.', 'GO TO FIRST SECOND DEPENDING ON IDX.')
        self.assertEqual([], issues)
        self.assertEqual(['altered-go', 'go-depending'], [d['kind'] for d in found])
        self.assertEqual(['target:FIRST', 'target:SECOND'], [o['label'] for o in found[0]['outcomes']])
        self.assertEqual(3, len(found[1]['outcomes']))

    def test_physical_location_and_sequence_columns(self):
        text = cobol('PROCEDURE DIVISION.')+'000200     IF A CONTINUE END-IF.'.ljust(72)+'IF BAD\n'
        found, _, _ = scan(tokenize(text, 'example.cbl'), 'TEST')
        self.assertEqual(1, len(found))
        self.assertEqual((2, 12, 'example.cbl'), (found[0]['line'], found[0]['column'], found[0]['path']))

    def test_literal_continuation_and_doubled_quotes(self):
        text = cobol('PROCEDURE DIVISION.', "DISPLAY 'IF ''WHEN''")+'      -    \' EVALUATE\'.\n'+cobol('IF A CONTINUE END-IF.')
        found, _, _ = scan(tokenize(text), 'TEST')
        self.assertEqual(1, len(found))

    def test_unsupported_format_and_unclosed_selection_are_visible(self):
        for text in ['      D    IF X CONTINUE\n', cobol('>>SOURCE FORMAT FREE'), cobol("DISPLAY 'bad")]:
            with self.assertRaises(SourceError): tokenize(text)
        _, issues, _ = decisions('EVALUATE A WHEN 1 CONTINUE')
        self.assertEqual('unterminated-selection', issues[0]['cause'])


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_copy_occurrences_keep_inclusion_and_replacements(self):
        (self.root/'MAIN.CBL').write_text(cobol('PROCEDURE DIVISION.',
            'COPY BRANCH REPLACING ==FLAG== BY ==A==.', 'COPY BRANCH REPLACING ==FLAG== BY ==B==.'))
        (self.root/'BRANCH.cpy').write_text(cobol('IF FLAG CONTINUE END-IF'))
        report = inventory(self.root)
        self.assertEqual({'if': 2}, report['summary']['by_kind'])
        a, b = report['decisions']
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual('BRANCH.cpy', a['path'])
        self.assertEqual('IF A', a['text'])
        self.assertEqual(['MAIN.CBL:2:8'], a['inclusion'])
        self.assertEqual(report, inventory(self.root))

    def test_missing_ambiguous_and_recursive_copy_are_reported(self):
        (self.root/'MAIN.cbl').write_text(cobol('PROCEDURE DIVISION.', 'COPY UNKNOWN.', 'IF A CONTINUE END-IF.'))
        report = inventory(self.root)
        self.assertEqual(1, report['summary']['decisions'])
        self.assertEqual({'missing-copybook': 1}, report['summary']['issues_by_cause'])
        (self.root/'A.cpy').write_text(cobol('COPY A.'))
        (self.root/'MAIN.cbl').write_text(cobol('PROCEDURE DIVISION.', 'COPY A.'))
        self.assertIn('recursive COPY', inventory(self.root)['issues'][0]['detail'])
        (self.root/'sub').mkdir(); (self.root/'sub/A.cpy').write_text(cobol('CONTINUE'))
        self.assertIn('ambiguous-copybook', inventory(self.root)['summary']['issues_by_cause'])

    def test_source_edit_changes_manifest_and_rejects_stale_coverage(self):
        path = self.root/'TEST.cbl';path.write_text(cobol('PROCEDURE DIVISION.', 'IF A CONTINUE END-IF.'))
        first = inventory(self.root)
        receipt = dict(inventory_sha256=first['inventory_sha256'], evidence_class='simulated',
                       outcome_ids=[first['decisions'][0]['outcomes'][0]['id']]*2)
        measured = coverage(first, receipt)
        self.assertEqual(50, measured['coverage_percent'])
        self.assertEqual(1, measured['observed_outcomes'])
        self.assertIsNone(measured['native_coverage_percent'])
        tampered = copy.deepcopy(first)
        tampered['summary']['outcomes'] = 1
        with self.assertRaises(ValueError): coverage(tampered, receipt)
        baseline = coverage(first)
        self.assertIsNone(baseline['observed_outcomes'])
        self.assertIsNone(baseline['coverage_percent'])
        path.write_text(cobol('PROCEDURE DIVISION.', 'IF B CONTINUE END-IF.'))
        with self.assertRaises(ValueError): coverage(inventory(self.root), receipt)
        for change in [dict(evidence_class='zos_observed'), dict(outcome_ids=['invented'])]:
            with self.assertRaises(ValueError): coverage(first, {**receipt, **change})
