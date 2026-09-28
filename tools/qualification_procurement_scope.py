"""Development-only investigation of purchase costing effects. Not an admission rule.

This deliberately does not change the old judge or whitelist. It checks whether
additional captured rows belong to the declared journey before proposing rules.
"""
from collections import Counter
from decimal import Decimal
from pathlib import Path
from lightyear_calibration.contracts import require,canonical,seal,read_json
from lightyear_calibration.native_reconciliation import state,rows
from lightyear_calibration.application_journey import read_trace,number

EXTRA=('m_costqueue','m_costhistory','t_fact_acct_history')


def validate(records, before, trace):
    product=int(trace['product.id']);vendor=int(trace['vendor.id'])
    def only(table,**where):
        selected=[r for r in records[table] if all(r[k]==v for k,v in where.items())]
        require(len(selected)==1,'Ambiguous procurement scope relationship: '+table)
        return selected[0]
    orderline=only('c_orderline',c_order_id=int(trace['purchaseOrder.id']))
    receiptline=only('m_inoutline',m_inout_id=int(trace['receipt.id']))
    invoiceline=only('c_invoiceline',c_invoice_id=int(trace['vendorInvoice.id']))
    require(orderline['m_product_id']==receiptline['m_product_id']==invoiceline['m_product_id']==product,
            'Costing scope has mismatched product')
    require(receiptline['c_orderline_id']==orderline['c_orderline_id'] and
            invoiceline['m_inoutline_id']==receiptline['m_inoutline_id'],'Costing scope has broken document chain')
    client=orderline['ad_client_id'];org=orderline['ad_org_id']
    schemas={r['c_acctschema_id'] for r in records['c_acctschema'] if r['ad_client_id']==client}
    matches={r['m_matchinv_id']:r for r in records['m_matchinv']
             if r['c_invoiceline_id']==invoiceline['c_invoiceline_id'] and r['m_inoutline_id']==receiptline['m_inoutline_id']}
    details={r['m_costdetail_id']:r for r in records['m_costdetail'] if r['m_product_id']==product}
    require(matches and details,'Missing journey matching/cost records')
    for r in details.values():
        require(r['ad_client_id']==client and r['ad_org_id']==org and r['c_acctschema_id'] in schemas,
                'Cost detail escaped client/organization/schema')
        require((r.get('c_orderline_id')==orderline['c_orderline_id'] and r.get('c_invoiceline_id') is None)
                or (r.get('c_invoiceline_id')==invoiceline['c_invoiceline_id'] and r.get('c_orderline_id') is None),
                'Cost detail has unrelated document link')
    additions={}
    for table in EXTRA:
        old=Counter(canonical(r) for r in before[table]);new=Counter(canonical(r) for r in records[table])
        require(not old-new,'Existing costing/history row changed or disappeared: '+table)
        remaining=new-old;added=[]
        for row in records[table]:
            key=canonical(row)
            if remaining[key]:added.append(row);remaining[key]-=1
        additions[table]=added
        for r in added:
            require(r['ad_client_id']==client and r['m_product_id']==product,'Side effect escaped journey product/client')
            require(r['ad_org_id'] in (0,org) if table!='t_fact_acct_history' else r['ad_org_id']==org,
                    'Side effect escaped organization')
            if table=='m_costhistory':
                require(r['m_costdetail_id'] in details,'History references unrelated cost detail')
                detail=details[r['m_costdetail_id']]
                require(r['m_attributesetinstance_id']==detail['m_attributesetinstance_id'], 'History attribute set differs')
            else:
                require(r['c_acctschema_id'] in schemas,'Side effect escaped accounting schema')
            if table=='m_costqueue':
                require(any(d['c_acctschema_id']==r['c_acctschema_id'] and
                            d['m_attributesetinstance_id']==r['m_attributesetinstance_id'] for d in details.values()),
                        'Queue has no matching journey cost detail')
            if table=='t_fact_acct_history':
                require(r['ad_table_id']==472 and r['record_id'] in matches and r['c_bpartner_id']==vendor,
                        'Reposting history references unrelated document/vendor')
    groups={}
    for r in additions['t_fact_acct_history']:
        key=tuple(r[c] for c in ('record_id','c_acctschema_id','c_currency_id'))
        a,b=groups.get(key,(Decimal(0),Decimal(0)))
        groups[key]=(a+number(r['amtacctdr'])-number(r['amtacctcr']),b+number(r['amtsourcedr'])-number(r['amtsourcecr']))
    require(all(v==(0,0) for v in groups.values()),'Reposting history is unbalanced')
    identities=[r['fact_acct_id'] for r in records['t_fact_acct_history']]
    require(len(identities)==len(set(identities)),'History cannot align by unique captured Fact_Acct_ID')
    return {'scoped_rows':{t:len(v) for t,v in additions.items()},'balanced_history_groups':len(groups),
            'captured_history_ids_unique':True,'admission_granted':False}


def inspect(run):
    folder=Path(run)/'cases/operations/1';out={}
    tables=set(EXTRA)|{'c_orderline','m_inoutline','c_invoiceline','c_acctschema','m_matchinv','m_costdetail'}
    for lane in ('oracle','postgresql'):
        current=folder/'after'/lane;old=folder/'baseline'/lane/'entry'
        a=state(current,lane);b=state(old,lane)
        records={t:rows(current,a['tables'][t]) for t in tables}
        before={t:rows(old,b['tables'][t]) for t in EXTRA}
        trace,_=read_trace(folder/'execution'/lane/'journey.xml')
        out[lane]=validate(records,before,trace)
    return seal({'artifact_type':'procurement-side-effect-scope-check','run':Path(run).name,
                 'lanes':out,'admission_granted':False,'purpose':'Development investigation only'})
