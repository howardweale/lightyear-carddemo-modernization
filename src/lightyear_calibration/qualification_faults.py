"""Private native mutation equipment. Never mounted in the builder sandbox.

Mutates isolated qualification databases AFTER a successful reference, BEFORE
independent capture. Identical faults on both lanes test correctness, not merely
cross-engine agreement. The rollback case models a leaked committed draft; it
does not claim to disable the engine's rollback implementation.
"""
from pathlib import Path
import json,re,sys,uuid
from .contracts import read_json, require, seal
from .application_journey import read_trace
from .journey_worker import connect

FAULTS=('wrong-quantity','missing-posting','incorrect-link','rollback-leaked-row')


def inject(spec):
    plan=read_json(Path('/output/plan.json'))
    require(plan.get('qualification_only') is True and plan.get('model_calls')==0,
            'Fault injection requires a qualification-only plan')
    fault=spec['fault'];require(fault in FAULTS and plan['fault']==fault,'Undeclared fault')
    lane=spec['lane'];require(lane in ('oracle','postgresql'),'Unknown lane')
    trace,_=read_trace(Path('/output/cases/operations/1/execution')/lane/'journey.xml')
    require(trace['status']=='completed-and-committed','Reference execution did not complete')
    bind=lambda n: ':'+str(n) if lane=='oracle' else '%s'
    with connect(lane,spec['password']) as connection:
        with connection.cursor() as cursor:
            if fault=='wrong-quantity':
                cursor.execute('UPDATE C_OrderLine SET QtyOrdered=QtyOrdered+1 WHERE C_Order_ID='+bind(1),[int(trace['order.id'])])
            elif fault=='missing-posting':
                cursor.execute('DELETE FROM Fact_Acct WHERE AD_Table_ID=318 AND Record_ID='+bind(1),[int(trace['invoice.id'])])
            elif fault=='incorrect-link':
                cursor.execute('UPDATE C_Payment SET C_Invoice_ID='+bind(1)+' WHERE C_Payment_ID='+bind(2),
                               [int(trace['credit.id']),int(trace['payment.id'])])
            else:
                cursor.execute('SELECT * FROM C_BPartner WHERE C_BPartner_ID='+bind(1),[int(trace['recoveryCustomer.id'])])
                row=cursor.fetchone();require(row is not None,'Missing native recovery row')
                columns=[x[0].lower() for x in cursor.description];values=list(row)
                require(all(re.fullmatch('[a-z][a-z0-9_]*',x) for x in columns),'Unsafe native column identifier')
                values[columns.index('c_bpartner_id')]=int(trace['recovery.rolledBackId'])
                values[columns.index('c_bpartner_uu')]=str(uuid.uuid4())
                values[columns.index('value')]='LY-QUALIFICATION-LEAK'
                cursor.execute('INSERT INTO C_BPartner ('+','.join(columns)+') VALUES ('+
                               ','.join(bind(i+1) for i in range(len(values)))+')',values)
            count=cursor.rowcount;require(count>0,'Mutation changed no native rows')
        connection.commit()
    return seal({'artifact_type':'private-native-qualification-mutation','lane':lane,'fault':fault,
                 'affected_rows':count,'committed':True,'qualification_only':True,'not_agent_generated':True})


if __name__=='__main__':
    value=inject(json.load(sys.stdin));print(json.dumps(value))
