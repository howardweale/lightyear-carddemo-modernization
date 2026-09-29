"""Private, declared native mutations, never part of builder inputs.

Twelve faults, three fresh paired executions each. Lock-duration and duplicate-retry
invoice mutants are not included; these remain explicit unqualified limits.
"""
import json, sys, uuid, re
from pathlib import Path
from .contracts import read_json, require, seal
from .application_journey import read_trace
from .journey_worker import connect
from .qualification_faults import inject as legacy

FAULTS = {
 'wrong-quantity': 'Quantity outcome differs',
 'one-cent-amount': 'Monetary outcomes differ',
 'wrong-tax': 'Operations business boundary failed',
 'wrong-rounding': 'Order net amount differs',
 'missing-posting': 'Missing accounting entries',
 'incorrect-link': 'Journey document links differ',
 'missing-reversal': 'Missing reciprocal credit reversal',
 'outside-footprint': 'Write outside declared footprint or new application issue',
 'costing-wrong-organization': 'Cost detail escaped client/organization/schema',
 'rollback-leaked-row': 'Rolled-back record survived',
 'duplicate-invoice-line': 'Missing or ambiguous committed application record: c_invoiceline',
 'timestamp-outside-scope': 'unresolved-c_order-dateordered',
}


def inject(spec):
    fault=spec['fault']; lane=spec['lane']
    plan=read_json(Path('/output/plan.json'))
    require(plan.get('qualification_only') is True and plan.get('model_calls') == 0
            and plan['fault'] == fault and fault in FAULTS, 'Undeclared qualification mutation')
    if fault in ('wrong-quantity','missing-posting','incorrect-link','rollback-leaked-row'):
        return legacy(spec)
    require(lane in ('oracle','postgresql'), 'Unknown lane')
    trace,_=read_trace(Path('/output/cases/operations/1/execution')/lane/'journey.xml')
    require(trace['status']=='completed-and-committed','Reference did not complete')
    bind=lambda n: ':'+str(n) if lane=='oracle' else '%s'
    with connect(lane,spec['password']) as connection:
        with connection.cursor() as cursor:
            def update(table, expression, key, value):
                cursor.execute('UPDATE '+table+' SET '+expression+' WHERE '+key+'='+bind(1),[int(value)])
            if fault=='one-cent-amount':
                update('C_Payment','PayAmt=PayAmt+0.01','C_Payment_ID',trace['payment.id'])
            elif fault=='wrong-tax':
                update('C_InvoiceTax','TaxAmt=TaxAmt+0.01','C_Invoice_ID',trace['invoice.id'])
            elif fault=='wrong-rounding':
                # This input's HALF_UP net is one cent greater than truncation.
                update('C_Order','TotalLines=TotalLines-0.01','C_Order_ID',trace['order.id'])
            elif fault=='missing-reversal':
                update('C_Invoice','Reversal_ID=NULL','C_Invoice_ID',trace['credit.id'])
            elif fault=='outside-footprint':
                cursor.execute("UPDATE AD_Ref_List SET Name=Name || '-MS94-FAULT' WHERE AD_Ref_List_ID=(SELECT MIN(AD_Ref_List_ID) FROM AD_Ref_List)")
            elif fault=='costing-wrong-organization':
                update('M_CostDetail','AD_Org_ID=0','M_Product_ID',trace['product.id'])
            elif fault=='timestamp-outside-scope':
                # Different second offsets on BOTH engines, outside shipdate scope.
                delta=('1/86400' if lane=='oracle' else "INTERVAL '2 seconds'")
                update('C_Order','DateOrdered=DateOrdered+'+delta,'C_Order_ID',trace['order.id'])
            elif fault=='duplicate-invoice-line':
                cursor.execute('SELECT * FROM C_InvoiceLine WHERE C_Invoice_ID='+bind(1),[int(trace['invoice.id'])])
                row=cursor.fetchone();require(row is not None,'Missing native invoice line')
                columns=[x[0].lower() for x in cursor.description];values=list(row)
                require(all(re.fullmatch('[a-z][a-z0-9_]*',x) for x in columns),'Unsafe identifier')
                cursor.execute('SELECT MAX(C_InvoiceLine_ID)+1 FROM C_InvoiceLine')
                values[columns.index('c_invoiceline_id')]=int(cursor.fetchone()[0])
                values[columns.index('c_invoiceline_uu')]=str(uuid.uuid4())
                values[columns.index('line')]=int(values[columns.index('line')])+10000
                cursor.execute('INSERT INTO C_InvoiceLine ('+','.join(columns)+') VALUES ('+
                               ','.join(bind(i+1) for i in range(len(values)))+')',values)
            count=cursor.rowcount;require(count>0,'Mutation changed no rows')
        connection.commit()
    return seal({'artifact_type':'private-native-qualification-mutation','lane':lane,'fault':fault,
                 'affected_rows':count,'committed':True,'qualification_only':True,'not_agent_generated':True})


if __name__=='__main__': print(json.dumps(inject(json.load(sys.stdin))))
