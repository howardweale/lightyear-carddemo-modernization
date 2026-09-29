"""Predeclared v3 operations judge; old verdicts and implementations stay intact.

Column types confer numeric eligibility. A trace binding is provenance, not a
numeric field allowlist: the binding must resolve to an independently read cell.
Unbound intermediate traces are exact strings, never silently normalized.
"""
from datetime import date
from pathlib import Path

from lightyear_calibration.contracts import read_json, require, seal, verify
from lightyear_calibration.ms94_v3_errors import business_require
from lightyear_calibration.declared_rules import (NUMERIC, STAMP, decimal_value, exact_decimal,
                             inventory_columns, numeric_columns)
from tools.ms94_v3_register import validate_register
from lightyear_calibration.journey_judge_v2 import same_second
from lightyear_calibration.journey_order import file_hash, save, RUNS
from lightyear_calibration.native_reconciliation import state, rows, keyed, HISTORY_POLICY, reconcile
from lightyear_calibration.ms94_v3_journey_verify import entries, footprint, rebound_prior
from lightyear_calibration.application_effects import admit
from lightyear_calibration.ms94_v3_operations import verify_lane, STAGES, AUXILIARY
from lightyear_control_tower.decisions import verify_envelope
from lightyear_calibration import ms94_v3_procurement as procurement_journey
from tools import ms94_v3_effects as procurement_effects
from lightyear_calibration.qualification_observer import verify_capture
VERSION='idempiere-purchasing-combined-v2-typed-ms94-development'


class NativeCells:
    def __init__(self, folders, inventory, primary_keys):
        self.folders = folders
        self.snapshots = {lane: state(folder, lane) for lane, folder in folders.items()}
        self.columns = inventory_columns(inventory)
        self.numeric = set(map(tuple, numeric_columns(inventory)))
        self.keys = primary_keys
        self.cache = {}
        self.indexed = {}
        for lane, snapshot in self.snapshots.items():
            native = {(c['table_name'].lower(), c['column_name'].lower()): c
                      for c in snapshot['structure']['columns']}
            for key, row in self.columns.items():
                require(key in native and native[key]['data_type'].lower() ==
                        row['native_declarations'][lane]['data_type'].lower(), 'Frozen column datatype changed')

    def table(self, lane, table):
        key = lane, table
        if key not in self.cache:
            self.cache[key] = rows(self.folders[lane], self.snapshots[lane]['tables'][table])
        return self.cache[key]

    def finding(self, value):
        table, column, key = value['table'], value['column'], value['key']
        for lane in self.folders:
            index = lane, table
            if index not in self.indexed: self.indexed[index] = keyed(self.table(lane, table), self.keys[lane][table])
            records = self.indexed[index]
            require(key in records and records[key][column] == value[lane], 'Difference is not a captured cell')

    def scan_numeric(self):
        """Equal exponent/NaN strings cannot evade the rule by comparing equal."""
        count = 0
        by_table = {}
        for table, column in self.numeric:
            by_table.setdefault(table, []).append(column)
        for lane in self.folders:
            for table, columns in by_table.items():
                for row in self.table(lane, table):
                    for column in columns:
                        if row[column] is not None:
                            decimal_value(row[column]); count += 1
        return count

    def bind(self, lane, table, column, conditions):
        aggregate = conditions.get('$aggregate')
        matches = [row for row in self.table(lane, table)
                   if all(row.get(k) == v for k, v in conditions.items() if k != '$aggregate')]
        if aggregate:
            from decimal import Decimal, localcontext
            require(aggregate=='sum' and (table,column) in self.numeric and matches, 'Invalid numeric aggregate binding')
            with localcontext() as context:
                context.prec=4096
                return format(sum((decimal_value(row[column]) for row in matches),Decimal(0)),'f')
        business_require(len(matches) == 1 and (table, column) in self.columns, 'Missing or ambiguous native trace binding')
        return matches[0][column]


def admit_finding(finding, cells, rules, prior_rule=None):
    """Legacy predicates are rerun first; every resulting admission needs a current register entry."""
    if not all(k in finding for k in ('table', 'column', 'key', 'oracle', 'postgresql')):
        return None
    cells.finding(finding)
    key = finding['table'], finding['column']
    if key in cells.numeric and exact_decimal(finding['oracle'], finding['postgresql']):
        return NUMERIC
    if key == ('m_inout', 'shipdate') and same_second(finding['oracle'], finding['postgresql']):
        return STAMP
    if prior_rule == 'exact-native-decimal-value':
        return None  # No legacy untyped decimal fallback.
    if prior_rule in rules and list(key) in rules[prior_rule]['columns']:
        return prior_rule
    return None


def bindings(trace):
    """Cell locators; eligibility is ALWAYS derived from the native datatype inventory."""
    result = {}
    stages = {**STAGES, **AUXILIARY, 'credit': 'c_invoice', 'creditReversal': 'c_invoice',
              'recoveryCustomer': 'c_bpartner'}
    for stage, table in stages.items():
        if stage + '.id' in trace:
            conditions = {table + '_id': int(trace[stage + '.id'])}
            result[stage + '.uuid'] = (table, table + '_uu', conditions)
    for field, stage, table, column, join in [
        ('order.total','order','c_order','grandtotal','c_order_id'),
        ('order.net','order','c_order','totallines','c_order_id'),
        ('invoice.total','invoice','c_invoice','grandtotal','c_invoice_id'),
        ('payment.amount','payment','c_payment','payamt','c_payment_id'),
        ('order.priceList','order','c_orderline','pricelist','c_order_id'),
        ('order.priceActual','order','c_orderline','priceactual','c_order_id'),
        ('order.discount','order','c_orderline','discount','c_order_id'),
        ('shipment.delivered','order','c_orderline','qtydelivered','c_order_id'),
        ('openingInventory.quantity','openingInventory','m_inventoryline','qtycount','m_inventory_id'),
        ('credit.net','credit','c_invoice','totallines','c_invoice_id'),
        ('credit.total','credit','c_invoice','grandtotal','c_invoice_id'),
        ('creditReversal.total','creditReversal','c_invoice','grandtotal','c_invoice_id'),
        ('concurrency.finalCreditLimit','customer','c_bpartner','so_creditlimit','c_bpartner_id'),
        ('firstShipment.shipDate.readback','firstShipment','m_inout','shipdate','m_inout_id'),
        ('shipment.shipDate.readback','shipment','m_inout','shipdate','m_inout_id')]:
        if field in trace:
            result[field] = table, column, {join: int(trace[stage + '.id'])}
    if 'inventory.onHand' in trace:
        result['inventory.onHand'] = 'm_storageonhand', 'qtyonhand', {'m_product_id':int(trace['product.id']), '$aggregate':'sum'}
    if 'order.taxRate' in trace:
        result['order.taxRate'] = 'c_tax', 'rate', {'c_tax_id': int(trace['order.taxId'])}
    return result


def compare_traces(lanes, cells, rules, accepted_rows, locator=bindings):
    traces = {k: v['trace'] for k, v in lanes.items()}
    business_require(set(traces['oracle']) == set(traces['postgresql']), 'Trace fields differ')
    locators = {lane: locator(trace) for lane, trace in traces.items()}
    allowed, blocked = [], []
    for field, left in traces['oracle'].items():
        right = traces['postgresql'][field]
        bound = field in locators['oracle'] and field in locators['postgresql']
        rule = None; table = column = None
        if bound:
            table, column, _ = locators['oracle'][field]
            values = {}
            for lane in lanes:
                t, c, where = locators[lane][field]
                require((t,c) == (table,column), 'Trace column binding differs across lanes')
                values[lane] = cells.bind(lane,t,c,where)
                if (t,c) in cells.numeric:
                    business_require(exact_decimal(traces[lane][field], values[lane]), 'Trace is not exact native numeric cell')
                elif c == 'shipdate':
                    from lightyear_calibration.journey_judge_v2 import timestamp
                    business_require(timestamp(traces[lane][field]) == timestamp(values[lane]), 'Timestamp trace differs from native cell')
                else:
                    business_require(traces[lane][field] == values[lane], 'Trace differs from native cell')
            if (table,column) in cells.numeric and exact_decimal(left,right): rule = NUMERIC
            elif (table,column) == ('m_inout','shipdate') and same_second(left,right): rule = STAMP
            else:
                witness = next((w for w in accepted_rows if (w['table'],w['column']) == (table,column)
                                and w['oracle'] == values['oracle'] and w['postgresql'] == values['postgresql']),None)
                if witness: rule = witness['rule']
        if left == right: continue
        if field == 'database' and (left,right) == ('oracle','postgresql'):
            # Engine identity is an explicit metadata contract, not a data difference.
            rule = 'declared-lane-identity'
        finding = {'field':field,'oracle':left,'postgresql':right,'table':table,'column':column,'rule':rule}
        (allowed if rule else blocked).append(finding)
    return allowed, blocked


def verify_run(run, *, proposed_register=None, review_output=None):
    run = Path(run).resolve(); plan = read_json(run/'plan.json'); verify(plan)
    root = run.parents[len(RUNS.parts)]
    key = (root/'work/ms87/operator/authority.public.pem').read_bytes()
    auth = read_json(run/'authorization.json')
    require(verify_envelope(auth,key) and auth['run_id'] == run.name
            and auth['plan']['plan_sha256'] == plan['content_sha256'], 'Gate authorization differs')
    for name, expected in plan['inputs_sha256'].items():
        require('/' not in name and '\\' not in name and file_hash(run/'inputs'/name) == expected, 'Pinned input changed')
    require(file_hash(run/'inputs/operations.java') == plan['harness_sha256'], 'Generated harness changed')
    require(proposed_register is None or (review_output is not None and not Path(review_output).exists()
            and not Path(review_output).resolve().is_relative_to(run)), 'Retrospective development review needs a new output directory')
    register = read_json(proposed_register or run/'inputs/comparison-register.json')
    inventory = read_json(run/'inputs/datatype-inventory.json')
    if proposed_register is None:
        require(register['content_sha256'] == plan['comparison_register_sha256'], 'Rule register changed')
    require(verify_envelope(register['timestamp_decision'],key), 'Timestamp decision signature differs')
    rules = validate_register(register, inventory, date.fromisoformat(plan['assessed_on']))
    folder = run/'cases/operations/1'
    entry = entries(run,{'operations':folder})
    scenario=plan['scenario'];require(scenario=='procure-to-pay','Purchasing development judge only')
    from tools.ms94_v3_scope import inspect
    purchasing_scope=inspect(run)
    if scenario=='operations':writes=footprint({'operations':folder})
    else:
        writes=[]
        for lane in ('oracle','postgresql'):
            original=state(folder/'baseline'/lane/'entry',lane);final=state(folder/'after'/lane,lane)
            require(set(original['tables'])==set(final['tables']),'Procurement table inventory changed')
            changed=[t for t in original['tables'] if original['tables'][t]['row_multiset']!=final['tables'][t]['row_multiset']]
            business_require(not set(changed)-procurement_effects.TABLES,'Write outside declared procurement footprint')
            writes.append({'lane':lane,'changed_tables':changed})
    from lightyear_calibration.datatype_mappings import assess
    from lightyear_calibration.native_catalog import read_capture
    catalogs = {lane:read_capture(folder/'baseline'/lane/'catalog.json') for lane in ('oracle','postgresql')}
    oracle_tz = catalogs['oracle']['results']['identity']['rows']
    postgres_tz = [r for r in catalogs['postgresql']['results']['settings']['rows'] if r['name']=='TimeZone']
    require(len(oracle_tz)==len(postgres_tz)==1 and oracle_tz[0]['time_zone']=='UTC'
            and postgres_tz[0]['setting']=='UTC', 'Timestamp admission requires verified UTC capture sessions')
    fresh = assess(catalogs)
    require(fresh['columns'] == inventory['columns'], 'Runtime catalog differs from frozen datatype inventory')
    before = {lane:folder/'baseline'/lane/'entry' for lane in ('oracle','postgresql')}
    after = {lane:folder/'after'/lane for lane in before}
    prior = rebound_prior(run,before); keys = read_json(run/'inputs/primary-keys.json')
    # Not a claimed database primary key. Scope check has verified uniqueness in
    # these complete captures, unchanged old rows, and journey ownership.
    for lane in keys:keys[lane]['t_fact_acct_history']=['fact_acct_id']
    executions = {lane:read_json(folder/'execution'/lane/'execution.json') for lane in before}
    base = reconcile(after,keys,before=before,prior=prior,policy=HISTORY_POLICY)
    effects = (admit if scenario=='operations' else procurement_effects.admit)(base,after,before,keys,executions,prior_checkpoint=prior)
    lanes = {}
    for lane in before:
        where = folder/'execution'/lane
        require(executions[lane]['harness_sha256'] == plan['harness_sha256'], 'Native candidate differs')
        lanes[lane] = (verify_lane if scenario=='operations' else procurement_journey.verify_lane)(after[lane],where/'journey.xml',executions[lane],(where/'harness.java').read_bytes())
    cells = NativeCells(after,inventory,keys)
    numeric_count = cells.scan_numeric()
    allowed, blocked = [], []
    for finding in [*base['allowed_differences'],*effects['application_allowed_differences'],*effects['unresolved_differences']]:
        rule = admit_finding(finding,cells,rules,finding.get('rule'))
        (allowed if rule else blocked).append({**finding,'rule':rule})
    trace_allowed, trace_blocked = compare_traces(lanes,cells,rules,allowed,bindings if scenario=='operations' else procurement_journey.bindings)
    observers={lane:verify_capture(folder/'observers'/lane) for lane in before} if scenario=='operations' else {}
    observed_pass=all(x['passed'] for x in observers.values()) if scenario=='operations' else True
    result = seal({'scenario':scenario,'database_observers':observers,'artifact_type':'lightyear-declared-operations-gate','judge_version':VERSION,
        'purchasing_scope':purchasing_scope,'history_alignment':'unique-captured-fact-acct-id-not-schema-primary-key',
        'plan_sha256':plan['content_sha256'],'comparison_register_sha256':register['content_sha256'],
        'passed':not blocked and not trace_blocked and observed_pass,'entry':entry,'footprint':writes,
        'numeric_column_count':len(cells.numeric),'numeric_observations_validated':numeric_count,
        'accepted_difference_ledger':allowed,'accepted_trace_differences':trace_allowed,
        'rule_register':register,
        'unresolved_row_differences':blocked,'unresolved_trace_differences':trace_blocked,
        'lane_receipt_sha256':{lane:value['content_sha256'] for lane,value in lanes.items()},
        'transient_evidence_limit':'Operations require engine-side waits and rollback activity on the business-partner table; no per-row undo-history or crash-recovery claim. Procurement makes no transient-event claim.',
        'development_reassessment':proposed_register is not None,'native_qualification':False,
        'application_equivalence':False,'schema_equivalence':False,'platform_qualification':False,'independently_attested':False})
    for name,value in [('base',base),('effects',effects),*lanes.items(),('comparison',result)]:
        save((Path(review_output) if proposed_register is not None else folder/'verified')/(name+'.json'),value)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--run',type=Path,required=True)
    args = parser.parse_args(); save(args.run/'gate.json',verify_run(args.run))
