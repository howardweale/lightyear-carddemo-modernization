"""Reconcile the complete L1 mutation gate with bound current and historical XML."""
from collections import Counter
from hashlib import sha256
import json
import xml.etree.ElementTree as ET
from tools.carddemo_java_proof import summarize
from tools.carddemo_account_proof import GROUPS, verify_account_classes

HANDLERS = ('SignonService', 'MenuService', 'AccountViewService', 'AccountUpdateService',
            'AuthorizationListService', 'AuthorizationDetailService')
REPORT = 'work/carddemo-proof-artifacts/carddemo-proof-mutation/pit-reports/mutations.xml'
BASELINE = 'docs/modernization/carddemo-slice-1-evidence-2026-10-18/mutations.xml'
REMAINING = ['COACTVWC', 'COACTUPC', 'COPAUS0C', 'COPAUS1C']


def _nodes(raw):
    root = ET.fromstring(raw)
    if root.tag != 'mutations' or any(child.tag != 'mutation' for child in root):
        raise ValueError('account-mutation-xml')
    nodes = root.findall('mutation')
    if not nodes or any(not node.get('status') or not node.findtext('mutatedClass') for node in nodes):
        raise ValueError('account-mutation-empty-or-incomplete')
    return nodes


def verify_mutation_gate(raw_xml, historical_xml, gate):
    """Inputs must already be byte-bound; historical source provenance and full proof remain separate."""
    nodes = _nodes(raw_xml)
    old = _nodes(historical_xml)
    accounts = verify_account_classes(raw_xml, gate)
    counts = Counter(node.get('status') for node in nodes)
    total = len(nodes)
    killed = counts['KILLED']
    present = {node.findtext('mutatedClass').split('.')[-1].split('$')[0] for node in nodes}
    missing = sorted(set(HANDLERS) - present)
    signon = summarize(nodes, ('SignonService', 'SignonRules'))
    signon_passed = all(row['passed'] for row in signon.values())
    idiomatic = {
        'schema': 'carddemo-idiomatic-mutation/1', 'program': 'COSGN00C',
        'passed': signon_passed, 'threshold': 90,
        'denominator': 'all generated mutants per required class; KILLED only',
        'previous': {'report': BASELINE, 'sha256': sha256(historical_xml).hexdigest(),
                     'classes': summarize(old, ('SignonService',))},
        'current': signon, 'remaining_statement_engine_programs': REMAINING,
    }
    passed = 10 * killed >= 9 * total and not missing and signon_passed and all(row['passed'] for row in accounts.values())
    expected = {
        'passed': passed, 'killed': killed, 'total': total, 'percent': 100 * killed / total,
        'threshold': 90, 'missing_screen_handlers': missing, 'status_counts': dict(counts),
        'denominator': 'every PIT mutation in configured screen-handler/helper scope; timeout, no-coverage and errors are not counted killed',
        'report': {'path': REPORT, 'sha256': sha256(raw_xml).hexdigest()}, 'idiomatic_java': idiomatic,
        **{group: {name: accounts[name] for name in classes} for group, classes in GROUPS.items()},
    }
    if not passed or json.dumps(gate, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
        raise ValueError('account-mutation-gate-mismatch')
    return expected
