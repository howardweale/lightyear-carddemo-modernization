"""Complete native comparison after separate ownership admission; J1 is untouched."""
from datetime import date
from decimal import Decimal

from lightyear_calibration.contracts import canonical, read_json, seal, verify
from lightyear_calibration.native_reconciliation import HISTORY_POLICY, keyed, reconcile, valid_uuid
from lightyear_calibration.ms94_v3_journey_verify import rebound_prior
from lightyear_calibration.ms94_v3_errors import business_require
from tools.ms94_v3_purchasing import NativeCells, admit_finding, compare_traces
from tools.ms94_v3_effects import audit_rule, utc
from tools.ms94_v3_register import validate_register
from tools.ms94_b06_admission import check, LANES


def materials_rule(table, column, values, *, new_row, unique_uuid, windows):
    # Only these new J3 tables need rules beyond the inherited audit policy.
    if table not in {'m_locator', 'm_movement', 'm_movementline', 'm_movementlinema'}:
        return None
    if new_row and column == table + '_uu' and unique_uuid and all(valid_uuid(v) for v in values.values()):
        return 'fresh-unique-application-uuid'
    if column in {'created', 'updated'} and new_row and all(
            utc(windows[l]['started_at']).replace(microsecond=0) <= utc(v) <= utc(windows[l]['finished_at'])
            for l, v in values.items()):
        return 'application-clock-within-native-execution'
    if new_row and table == 'm_movement' and column == 'processedon':
        try:
            if all(Decimal(str(utc(windows[l]['started_at']).timestamp())) * 1000 <= Decimal(str(v)) <=
                   Decimal(str(utc(windows[l]['finished_at']).timestamp())) * 1000 for l, v in values.items()):
                return 'processed-epoch-milliseconds-within-native-execution'
        except (ValueError, TypeError, ArithmeticError):
            return None
    return None


def compare(run, before_rows, after_rows, executions, lanes, locator):
    """No row absence, unexplained value or unregistered column gets normalized."""
    plan = read_json(run / 'plan.json')
    folder = run / 'cases/operations/1'
    before = {l: folder / 'baseline' / l / 'entry' for l in LANES}
    after = {l: folder / 'after' / l for l in LANES}
    keys = read_json(run / 'inputs/primary-keys.json')
    for l in LANES:
        ids = [r['fact_acct_id'] for r in after_rows[l]['t_fact_acct_history']]
        business_require(len(ids) == len(set(ids)), 'history-identity-not-unique')
        keys[l]['t_fact_acct_history'] = ['fact_acct_id']
    prior = rebound_prior(run, before)
    base = reconcile(after, keys, before=before, prior=prior, policy=HISTORY_POLICY)
    inventory = read_json(run / 'inputs/datatype-inventory.json')
    register = read_json(run / 'inputs/comparison-register.json')
    verify(register)
    check(register['content_sha256'] == plan['comparison_register_sha256'], 'comparison-register-changed')
    rules = validate_register(register, inventory, date.fromisoformat(plan['assessed_on']))
    cells = NativeCells(after, inventory, keys)
    count = cells.scan_numeric()
    windows = {l: {'started_at': executions[l]['native_clock_before']['value'],
                   'finished_at': executions[l]['native_clock_after']['value']} for l in LANES}
    facts = {l: executions[l]['runtime_facts'] for l in LANES}
    indexes = {}
    def index(lane, table, old):
        key = (lane, table, old)
        if key not in indexes:
            indexes[key] = keyed((before_rows if old else after_rows)[lane][table], keys[lane][table])
        return indexes[key]
    allowed, blocked = [], []
    for finding in [*base['allowed_differences'], *base['unresolved_differences']]:
        rule = admit_finding(finding, cells, rules, finding.get('rule'))
        if not rule and all(k in finding for k in ('table', 'column', 'key', *LANES)):
            table, column, key = (finding[k] for k in ('table', 'column', 'key'))
            values = {l: finding[l] for l in LANES}
            current = {l: index(l, table, False) for l in LANES}
            old = {l: index(l, table, True) for l in LANES}
            check(all(key in current[l] and canonical(current[l][key][column]) == canonical(values[l])
                      for l in LANES), 'comparison-not-native-cell')
            new = all(key not in old[l] for l in LANES)
            unique = all(sum(r.get(column) == values[l] for r in current[l].values()) == 1 and
                         not any(r.get(column) == values[l] for r in old[l].values()) for l in LANES)
            candidate = audit_rule(table, column, values, new_row=new, unique_uuid=unique,
                                   windows=windows, runtime_facts=facts,
                                   previous={l: old[l].get(key, {}) for l in LANES})
            if plan['journey'] == 'J3' and not candidate:
                candidate = materials_rule(table, column, values, new_row=new, unique_uuid=unique, windows=windows)
            if candidate in rules and [table, column] in rules[candidate]['columns']:
                rule = candidate
        (allowed if rule else blocked).append({**finding, 'rule': rule})
    trace_allowed, trace_blocked = compare_traces(lanes, cells, rules, allowed, locator)
    return seal({'artifact_type': 'ms94-b06-all-table-comparison/1', 'passed': not blocked and not trace_blocked,
                 'base_sha256': base['content_sha256'], 'accepted_differences': allowed,
                 'unresolved_differences': blocked, 'accepted_trace_differences': trace_allowed,
                 'unresolved_trace_differences': trace_blocked, 'numeric_observations_checked': count})
