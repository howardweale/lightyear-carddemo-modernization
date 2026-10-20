"""Reconcile the complete account publication scenario denominator from retained proof."""
from collections import Counter
import json
import re

PROGRAMS = frozenset(('COSGN00C', 'COMEN01C', 'COACTVWC', 'COACTUPC', 'COPAUS0C', 'COPAUS1C'))
MODES = ('api-reference', 'browser-reference', 'mutation-reference')


def _equal(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def _programs(value):
    return isinstance(value, list) and len(value) == 6 and all(isinstance(p, str) for p in value) and set(value) == PROGRAMS


def _number(value, expected):
    return type(value) is int and value == expected


def _reference(summary, rows, gate, tested_commit):
    if (not isinstance(summary, dict) or not isinstance(rows, list) or not isinstance(gate, dict)
        or summary.get('schema') != 'carddemo-six-screen-proof/1'
        or summary.get('head') != tested_commit or summary.get('passed') is not True
        or summary.get('full_slice_screen_equivalence') is not True or summary.get('remaining') != []
        or not _programs(summary.get('programs_compared')) or not _programs(summary.get('required_programs'))
        or summary.get('case_denominator_status') != 'complete generated suite'
        or not _number(summary.get('completed_case_count'), 120)
        or not _number(summary.get('planned_case_count'), 120)
        or not _number(summary.get('interactions_compared'), 678) or len(rows) != 678):
        raise ValueError('account-scenario-denominator')
    cases = summary.get('cases')
    if not isinstance(cases, list) or len(cases) != 120:
        raise ValueError('account-scenario-cases')
    counts = {}
    reserved = {'account-update-inventory', 'update-conflict-reader', 'update-conflict-writer'}
    for case in cases:
        if (not isinstance(case, dict) or set(case) != {'id', 'status', 'interactions'}
            or not isinstance(case['id'], str) or not case['id'] or case['id'] in counts
            or case['id'] in reserved or case['status'] != 'passed'
            or type(case['interactions']) is not int or case['interactions'] <= 0):
            raise ValueError('account-scenario-case')
        counts[case['id']] = case['interactions']
    if sum(counts.values()) != 674 or counts.get('update-conflict') != 14:
        raise ValueError('account-scenario-case-total')
    if any(not isinstance(row, dict) or not isinstance(row.get('case'), str) for row in rows):
        raise ValueError('account-scenario-row')
    actual = Counter(row['case'] for row in rows)
    expected = dict(counts); del expected['update-conflict']
    expected.update({'update-conflict-reader': 7, 'update-conflict-writer': 7, 'account-update-inventory': 4})
    if dict(actual) != expected:
        raise ValueError('account-scenario-row-groups')
    expected_gate = dict(passed=True, planned_cases=120, completed_cases=120, interactions=678,
        programs_compared=6, programs_required=6, cases=cases,
        bms_interactions=summary.get('bms_interactions_compared'),
        case_denominator_status='complete generated suite', validated_fields=summary.get('validated_fields'))
    if (not _number(summary.get('bms_interactions_compared'), 666)
        or not isinstance(summary.get('validated_fields'), list) or not summary['validated_fields']
        or not _equal(gate, expected_gate)):
        raise ValueError('account-scenario-gate')
    return counts


def verify_scenarios(gates, references, browser, tested_commit):
    """Inputs must already be hash-bound; this checks counts, not replay equivalence."""
    if (not isinstance(tested_commit, str) or not re.fullmatch('[0-9a-f]{40}', tested_commit)
        or not isinstance(gates, dict) or not isinstance(references, dict) or set(references) != set(MODES)):
        raise ValueError('account-scenario-shape')
    inventories = []
    for mode in MODES:
        item = references[mode]
        if not isinstance(item, dict) or set(item) != {'summary', 'rows'}:
            raise ValueError('account-scenario-reference')
        inventories.append(_reference(item['summary'], item['rows'], gates.get(mode), tested_commit))
    if any(inventory != inventories[0] for inventory in inventories[1:]):
        raise ValueError('account-scenario-mode-inventory')
    if (not isinstance(browser, dict) or browser.get('schema') != 'carddemo-browser-proof/1'
        or browser.get('head') != tested_commit or browser.get('passed') is not True
        or browser.get('full_slice_screen_equivalence') is not True
        or not _programs(browser.get('programs_compared'))
        or not _number(browser.get('interactions_compared'), 678)
        or not _number(browser.get('interactions_required'), 678)
        or not _equal(gates.get('browser'), dict(passed=True, interactions=678, required=678))):
        raise ValueError('account-scenario-browser')
    return dict(journeys=120, interactions=678, named_case_interactions=674,
        setup_interactions=4, conflict_reader_interactions=7, conflict_writer_interactions=7)
