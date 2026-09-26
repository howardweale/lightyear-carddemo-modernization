"""Narrow application audit rules applied to the complete native row comparison.

Business values stay exact. UUID, clock, elapsed-time and decimal rendering
rules retain both observations and cannot admit missing or extra rows.
"""
from datetime import datetime, timezone
from decimal import Decimal
import re

from .contracts import canonical, digest, require, seal, verify
from .native_reconciliation import HISTORY_POLICY, keyed, rows, state, valid_uuid

TABLES = frozenset('''ad_pinstance ad_sequence ad_system c_acctschema ad_treenodebp ad_treenodepr
ad_wf_activity ad_wf_eventaudit ad_wf_process c_allocationhdr c_allocationline c_bp_customer_acct
c_bp_vendor_acct c_bpartner c_bpartner_location c_invoice c_invoiceline c_invoicetax c_order
c_orderline c_ordertax c_payment fact_acct m_cost m_inout m_inoutline m_inoutlinema m_inventory
m_inventoryline m_inventorylinema m_product m_product_acct m_product_trl m_productprice
m_storageonhand m_storagereservation m_storagereservationlog m_transaction'''.split())
DOCUMENTS = frozenset(('c_allocationhdr', 'c_invoice', 'c_order', 'c_payment', 'm_inout', 'm_inventory'))
WORKFLOW = frozenset(('ad_wf_activity', 'ad_wf_eventaudit', 'ad_wf_process'))
POLICY_VERSION = 'idempiere-six-journey-audit-v1'


def utc(value):
    result = datetime.fromisoformat(value)
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def decimal_text_equal(left, right):
    if not isinstance(left, str) or not isinstance(right, str): return False
    pattern = r'(?<![\w.])([+-]?\d+(?:\.\d+)?)(?![\w.])'
    a, b = re.split(pattern, left), re.split(pattern, right)
    return len(a) == len(b) and len(a) > 1 and all(
        x == y if i % 2 == 0 else Decimal(x) == Decimal(y) for i, (x, y) in enumerate(zip(a, b)))


def audit_rule(table, column, values, *, new_row, unique_uuid, windows, runtime_facts, previous):
    if table not in TABLES: return None
    if column == table+'_uu' and new_row and unique_uuid and all(valid_uuid(v) for v in values.values()):
        return 'fresh-unique-application-uuid'
    if column in ('created', 'updated') and (new_row or column == 'updated'):
        if all(utc(windows[lane]['started_at']).replace(microsecond=0) <= utc(value) <= utc(windows[lane]['finished_at'])
               for lane, value in values.items()):
            return 'application-clock-within-native-execution'
    if new_row and column == 'processedon' and table in DOCUMENTS:
        try:
            stamps = {lane: Decimal(v['decimal'] if isinstance(v, dict) else str(v)) for lane, v in values.items()}
            if all(Decimal(str(utc(windows[lane]['started_at']).timestamp()))*1000 <= v <=
                   Decimal(str(utc(windows[lane]['finished_at']).timestamp()))*1000 for lane, v in stamps.items()):
                return 'processed-epoch-milliseconds-within-native-execution'
        except (ValueError, TypeError, KeyError, ArithmeticError): pass
    if new_row and table == 'ad_wf_eventaudit' and column == 'elapsedtimems':
        if all(type(value) is int and 0 <= value <= (utc(windows[lane]['finished_at'])-utc(windows[lane]['started_at'])).total_seconds()*1000
               for lane, value in values.items()):
            return 'nonnegative-workflow-duration-bounded-by-execution'
    if new_row and table in WORKFLOW and column == 'textmsg' and decimal_text_equal(values['oracle'], values['postgresql']):
        return 'workflow-text-identical-with-exact-decimal-rendering'
    if table == 'ad_system' and column == 'dbaddress' and all(
            values[lane] == runtime_facts[lane]['expected_database_address'] for lane in values):
        return 'pinned-driver-address-matches-isolated-native-target'
    if table == 'ad_system' and column == 'dbinstance' and (
            values['oracle'] == runtime_facts['oracle']['native_database_instance'] and
            values['postgresql'] == previous.get('postgresql', {}).get(column)):
        return 'oracle-native-database-name-and-unchanged-postgresql-seed-metadata'
    return None


def admit(base_checkpoint, folders, before, primary_keys, executions, *, prior_checkpoint):
    verify(base_checkpoint)
    verify(prior_checkpoint)
    require(prior_checkpoint['admitted'] and prior_checkpoint['policy_sha256'] == digest(HISTORY_POLICY), 'Invalid historical baseline checkpoint')
    require(base_checkpoint['policy_sha256'] == digest(HISTORY_POLICY), 'Unexpected base reconciliation policy')
    require(set(folders) == set(before) == set(executions) == {'oracle', 'postgresql'}, 'Both native application lanes required')
    snapshots = {lane: state(folder, lane) for lane, folder in folders.items()}
    originals = {lane: state(folder, lane) for lane, folder in before.items()}
    require(base_checkpoint['state_sha256'] == {lane: value['content_sha256'] for lane, value in snapshots.items()}, 'Effects refer to different readbacks')
    windows = {}; facts = {}
    for lane, execution in executions.items():
        verify(execution)
        require(execution['lane'] == lane and execution['exit_code'] == 0, 'Unsuccessful application execution')
        windows[lane] = {'started_at': execution['native_clock_before']['value'], 'finished_at': execution['native_clock_after']['value']}
        require(utc(windows[lane]['started_at']) <= utc(windows[lane]['finished_at']), 'Invalid native clock window')
        facts[lane] = execution['runtime_facts']
    require(executions['oracle']['harness_sha256'] == executions['postgresql']['harness_sha256'], 'Different application scenarios')
    cache = {}
    def records(lane, table, old=False):
        key = (lane, table, old)
        if key not in cache:
            snapshot, folder = (originals[lane], before[lane]) if old else (snapshots[lane], folders[lane])
            cache[key] = keyed(rows(folder, snapshot['tables'][table]), primary_keys[lane][table])
        return cache[key]
    allowed = []; blocked = []
    for finding in base_checkpoint['unresolved_differences']:
        table, column, key = finding.get('table'), finding.get('column'), finding.get('key')
        if not column or table not in TABLES or not key:
            blocked.append(finding); continue
        current = {lane: records(lane, table) for lane in folders}
        old = {lane: records(lane, table, True) for lane in folders}
        require(all(key in value for value in current.values()), 'Missing row for application difference')
        require(all(canonical(current[lane][key][column]) == canonical(finding[lane]) for lane in folders), 'Difference does not match native readback')
        values = {lane: finding[lane] for lane in folders}
        new = all(key not in value for value in old.values())
        unique = all(sum(row.get(column) == values[lane] for row in current[lane].values()) == 1 and
                     all(row.get(column) != values[lane] for row in old[lane].values()) for lane in folders)
        rule = audit_rule(table, column, values, new_row=new, unique_uuid=unique, windows=windows,
                          runtime_facts=facts, previous={lane: value.get(key, {}) for lane, value in old.items()})
        if rule: allowed.append({**finding, 'rule': rule})
        else: blocked.append(finding)
    # Neither a zero difference count nor matching diagnostics can hide a new issue.
    for lane in folders:
        require(set(snapshots[lane]['tables']) == set(originals[lane]['tables']), 'Application changed the table inventory')
        for table in snapshots[lane]['tables'].keys() - TABLES - {'ad_issue'}:
            if snapshots[lane]['tables'][table]['row_multiset'] != originals[lane]['tables'][table]['row_multiset']:
                blocked.append({'lane': lane, 'table': table, 'reason': 'change-outside-declared-journey-tables'})
        if snapshots[lane]['tables']['ad_issue']['row_multiset'] != originals[lane]['tables']['ad_issue']['row_multiset']:
            blocked.append({'lane': lane, 'table': 'ad_issue', 'reason': 'new-or-changed-application-issue'})
    def identity(item):
        return canonical([item['table'], item['key'], item['column'], item['oracle'], item['postgresql']])
    previous_witnesses = {identity(x) for x in prior_checkpoint['allowed_differences']}
    retained = [x for x in base_checkpoint['allowed_differences'] if identity(x) in previous_witnesses]
    newly_allowed = [x for x in base_checkpoint['allowed_differences'] if identity(x) not in previous_witnesses]
    return seal({'artifact_type': 'lightyear-bounded-application-effects', 'policy': POLICY_VERSION,
                 'base_checkpoint_sha256': base_checkpoint['content_sha256'],
                 'prior_checkpoint_sha256': prior_checkpoint['content_sha256'],
                 'state_sha256': base_checkpoint['state_sha256'],
                 'before_state_sha256': {lane: x['content_sha256'] for lane, x in originals.items()},
                 'execution_sha256': {lane: x['content_sha256'] for lane, x in executions.items()},
                 'retained_prior_allowed_count': len(retained),
                 'base_rules_newly_allowed_differences': newly_allowed,
                 'new_application_allowed_count': len(allowed)+len(newly_allowed),
                 'application_allowed_differences': allowed, 'unresolved_differences': blocked,
                 'admitted_for_selected_journeys': not blocked,
                 'schema_equivalence': False, 'application_equivalence': False, 'platform_qualification': False})
