"""Owned-row extension of the preserved MS93 purchasing investigation.

Every delta in a purchasing-added table is checked, including identical writes
on both engines. The native reference supplies frozen history bounds separately.
"""
from collections import Counter
from lightyear_calibration.contracts import canonical, require
from lightyear_calibration.ms94_v3_errors import business_require as check
from tools.ms94_v3_scope_base import validate as base_validate, EXTRA

PURCHASING = (*EXTRA, 'm_matchinv', 'm_matchpo', 'm_costdetail', 'm_product_po')
VENDOR_UPDATE = frozenset(('pricelastpo','pricelastinv','priceeffective','updated','updatedby'))


def delta(before, after):
    old = Counter(canonical(r) for r in before)
    new = Counter(canonical(r) for r in after)
    def selected(records, counts):
        result=[]
        for row in records:
            key=canonical(row)
            if counts[key]:result.append(row);counts[key]-=1
        return result
    return selected(before, old-new), selected(after, new-old)


def validate(records, before, trace, bounds):
    result=base_validate(records,before,trace)
    product=int(trace['product.id']);vendor=int(trace['vendor.id'])
    def one(table, field, value):
        selected=[r for r in records[table] if r.get(field)==value]
        check(len(selected)==1, 'Ambiguous owned procurement relationship: '+table)
        return selected[0]
    order=one('c_orderline','c_order_id',int(trace['purchaseOrder.id']))
    receipt=one('m_inoutline','m_inout_id',int(trace['receipt.id']))
    invoice=one('c_invoiceline','c_invoice_id',int(trace['vendorInvoice.id']))
    client=order['ad_client_id'];org=order['ad_org_id']
    schemas={r['c_acctschema_id'] for r in records['c_acctschema'] if r['ad_client_id']==client}
    counts={}
    for table in PURCHASING:
        removed, added=delta(before[table],records[table]);counts[table]=len(added)
        for row in removed+added:
            check(row.get('ad_client_id')==client and row.get('m_product_id')==product,
                  'Purchasing delta escaped journey product/client: '+table)
            check(row.get('ad_org_id') in ((0,org) if table in ('m_costqueue','m_costhistory','m_product_po') else (org,)),
                  'Purchasing delta escaped journey organization: '+table)
            if table=='m_matchinv':
                check(row.get('c_invoiceline_id')==invoice['c_invoiceline_id'] and row.get('m_inoutline_id')==receipt['m_inoutline_id'],
                      'Invoice match escaped journey links')
            elif table=='m_matchpo':
                check(row.get('c_orderline_id')==order['c_orderline_id'] and row.get('m_inoutline_id')==receipt['m_inoutline_id']
                      and row.get('c_invoiceline_id') in (None,0,invoice['c_invoiceline_id']), 'Order match escaped journey links')
            elif table=='m_costdetail':
                check(row.get('c_acctschema_id') in schemas, 'Cost detail escaped accounting schema')
                check((row.get('c_orderline_id')==order['c_orderline_id'] and row.get('c_invoiceline_id') in (None,0)) or
                      (row.get('c_invoiceline_id')==invoice['c_invoiceline_id'] and row.get('c_orderline_id') in (None,0)),
                      'Cost detail escaped journey links')
            elif table=='m_product_po':
                check(row.get('c_bpartner_id')==vendor,'Vendor-product row escaped journey vendor')
        if table=='m_product_po':
            index={(r['m_product_id'],r['c_bpartner_id']):r for r in added}
            for old in removed:
                current=index.get((old['m_product_id'],old['c_bpartner_id']))
                check(current is not None,'Vendor-product row deleted')
                check(set(old)==set(current) and {k for k in old if old[k]!=current[k]} <= VENDOR_UPDATE,
                      'Vendor-product update changed undeclared columns')
        elif removed:
            # These are new-journey rows. Existing seed rows have no valid reason
            # to change even when a generated trace claims their product identity.
            check(False,'Existing purchasing row changed or disappeared: '+table)
    require(bounds.get('status')=='measured-reference-bound' and bounds.get('source_run_sha256'),
            'Missing measured native history bound')
    history=delta(before['t_fact_acct_history'],records['t_fact_acct_history'])[1]
    grouped=Counter((r['record_id'],r['c_acctschema_id'],r['c_currency_id'],r['account_id']) for r in history)
    check(all(n<=bounds['maximum_rows_per_document_schema_currency_account'] for n in grouped.values()),
          'Reposting history exceeds measured native generation bound')
    check(len(history)<=bounds['maximum_history_rows'], 'Reposting history exceeds measured native row bound')
    result.update(owned_delta_counts=counts, history_bound_sha256=bounds['content_sha256'])
    return result


def accounting_cache(records, before, trace):
    """Only MPeriod's native period-cache update may touch accounting schemas."""
    old={r['c_acctschema_id']:r for r in before['c_acctschema']}
    new={r['c_acctschema_id']:r for r in records['c_acctschema']}
    check(set(old)==set(new),'Accounting schema inventory changed')
    stages={'vendorInvoice':318,'vendorPayment':335,'invoice':318,'payment':335,
            'credit':318,'creditReversal':318,'openingInventory':321,'shipment':319,'firstShipment':319}
    identities={(table,int(trace[stage+'.id'])) for stage,table in stages.items() if stage+'.id' in trace}
    facts=[r for r in records['fact_acct'] if (r['ad_table_id'],r['record_id']) in identities]
    changed=[]
    for identity,row in new.items():
        prior=old[identity];columns={k for k in set(row)|set(prior) if row.get(k)!=prior.get(k)}
        if not columns:continue
        check(columns <= {'c_period_id','updated','updatedby'},'Accounting configuration changed beyond period cache')
        matching=[r for r in facts if r['c_acctschema_id']==identity]
        check(matching and row['c_period_id'] in {r['c_period_id'] for r in matching}
              and all(r['ad_client_id']==row['ad_client_id'] for r in matching)
              and row['updatedby'] in {r['createdby'] for r in matching},
              'Accounting period cache is not bound to journey postings')
        changed.append({'schema_id':identity,'columns':sorted(columns)})
    return changed


def inspect(run):
    from pathlib import Path
    from lightyear_calibration.contracts import read_json, seal, verify
    from lightyear_calibration.native_reconciliation import state, rows
    from lightyear_calibration.application_journey import read_trace
    run=Path(run);folder=run/'cases/operations/1';out={}
    bounds=read_json(run/'inputs/history-bound.json');verify(bounds)
    names=set(PURCHASING)|{'c_orderline','m_inoutline','c_invoiceline','c_acctschema','fact_acct'}
    for lane in ('oracle','postgresql'):
        current=folder/'after'/lane;old=folder/'baseline'/lane/'entry'
        a=state(current,lane);b=state(old,lane)
        records={t:rows(current,a['tables'][t]) for t in names}
        before={t:rows(old,b['tables'][t]) for t in names}
        trace,_=read_trace(folder/'execution'/lane/'journey.xml')
        out[lane]=validate(records,before,trace,bounds)
        out[lane]['accounting_period_cache']=accounting_cache(records,before,trace)
    return seal({'artifact_type':'procurement-owned-effects-v3','lanes':out,
                 'history_bound_sha256':bounds['content_sha256'],'admission_granted':False})


def inspect_accounting_cache(run):
    from pathlib import Path
    from lightyear_calibration.native_reconciliation import state,rows
    from lightyear_calibration.application_journey import read_trace
    folder=Path(run)/'cases/operations/1';result={}
    for lane in ('oracle','postgresql'):
        after=folder/'after'/lane;before=folder/'baseline'/lane/'entry'
        a=state(after,lane);b=state(before,lane)
        current={t:rows(after,a['tables'][t]) for t in ('c_acctschema','fact_acct')}
        old={'c_acctschema':rows(before,b['tables']['c_acctschema'])}
        trace,_=read_trace(folder/'execution'/lane/'journey.xml')
        result[lane]=accounting_cache(current,old,trace)
    return result
