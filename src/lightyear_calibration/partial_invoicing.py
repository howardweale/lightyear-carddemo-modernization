"""Independent native readback for the bounded partial-invoicing extension."""
from decimal import Decimal
from pathlib import Path
from .contracts import require, seal, verify
from .native_reconciliation import state, rows, valid_uuid
from .application_journey import read_trace, number
from .boundary_contract import INPUT
from .journey_order import file_hash

STAGES={'customer':'c_bpartner','customerLocation':'c_bpartner_location','product':'m_product',
        'productPrice':'m_productprice','openingInventory':'m_inventory','order':'c_order',
        'firstShipment':'m_inout','shipment':'m_inout','firstInvoice':'c_invoice','invoice':'c_invoice',
        'firstPayment':'c_payment','payment':'c_payment'}
EXPECTED=((Decimal('1'),Decimal('18.00'),Decimal('1.35'),Decimal('19.35')),
          (Decimal('2'),Decimal('35.99'),Decimal('2.70'),Decimal('38.69')))


def verify_lane(folder, trace_path, execution, harness):
    verify(execution);lane=execution['lane']
    require(lane in ('oracle','postgresql') and execution['exit_code']==0,'Native execution failed')
    require(execution['application_source_commit']=='731515dcdd5278b843db33b9d3109d155b881951','Application source differs')
    require(execution['harness_sha256']==file_hash(harness),'Generated harness differs')
    trace,trace_hash=read_trace(trace_path)
    require(trace.get('database')==lane and trace.get('status')=='completed-and-committed','Missing native completion')
    require(trace.get('newIssueCount')=='0','Application issue was reported')
    snapshot=state(folder,lane);require(snapshot['evidence_class']=='native-database-observation','Readback is not native')
    cache={}
    def table(name):
        if name not in cache:cache[name]=rows(folder,snapshot['tables'][name])
        return cache[name]
    def only(name,**criteria):
        matched=[r for r in table(name) if all(r.get(k)==v for k,v in criteria.items())]
        require(len(matched)==1,'Missing or ambiguous '+name);return matched[0]
    observed={}
    for stage,name in STAGES.items():
        row=only(name,**{name+'_id':int(trace[stage+'.id'])})
        require(trace[stage+'.saved']=='true' and valid_uuid(trace[stage+'.uuid']) and row[name+'_uu']==trace[stage+'.uuid'],'Stage readback differs: '+stage)
        if name in ('m_inventory','c_order','m_inout','c_invoice','c_payment'):
            require(row['docstatus']==trace[stage+'.status']=='CO','Document not completed: '+stage)
        observed[stage]=row
    customer,location,product,order=(observed[k] for k in ('customer','customerLocation','product','order'))
    customer_id=customer['c_bpartner_id'];product_id=product['m_product_id'];order_id=order['c_order_id']
    require(customer['value']==product['value']=='LY-PARTIAL-INVOICE','Wrong logical business key')
    require(customer['name']==INPUT['customer_name'] and customer['description'] is None,'Unicode/empty field contract differs')
    require(trace['customer.name.input']==customer['name'] and trace['customer.description.input']=='empty-string','Wrong declared text input')
    require(location['c_bpartner_id']==customer_id and order['c_bpartner_location_id']==location['c_bpartner_location_id'],'Customer location differs')
    require(customer['iscustomer']=='Y' and product['issold']==product['isstocked']=='Y','Wrong customer/product role')
    price=observed['productPrice'];require(price['m_product_id']==product_id and number(price['pricelist'])==Decimal('19.995') and number(price['pricestd'])==Decimal('17.9955'),'Price setup differs')
    ol=only('c_orderline',c_order_id=order_id)
    require(ol['m_product_id']==product_id and all(number(ol[k])==3 for k in ('qtyordered','qtydelivered','qtyinvoiced')) and number(ol['qtyreserved'])==0,'Final fulfillment differs')
    require(number(ol['pricelist'])==Decimal('19.995') and number(ol['priceactual'])==Decimal('17.9955') and number(ol['discount'])==10,'Discount/precision differs')
    require(number(order['totallines'])==Decimal('53.99') and number(order['grandtotal'])==Decimal('58.04'),'Order totals differ')
    ot=only('c_ordertax',c_order_id=order_id)
    require(number(ot['taxamt'])==Decimal('4.05') and ot['c_tax_id']==ol['c_tax_id']==107 and number(only('c_tax',c_tax_id=107)['rate'])==Decimal('7.5'),'Tax setup differs')
    inventory=observed['openingInventory'];il=only('m_inventoryline',m_inventory_id=inventory['m_inventory_id'])
    require(il['m_product_id']==product_id and number(il['qtycount'])==10,'Opening inventory differs')
    require(number(trace['invoicing.afterFirst'])==1 and number(trace['invoicing.final'])==3,'Partial invoicing checkpoints differ')
    invoices=[r for r in table('c_invoice') if r['c_order_id']==order_id]
    payments=[r for r in table('c_payment') if r['c_bpartner_id']==customer_id]
    require(len(invoices)==len(payments)==2,'Extra or missing invoice/payment')
    accounting_keys=set();summary=[]
    for stages,expected in zip((('firstShipment','firstInvoice','firstPayment'),('shipment','invoice','payment')),EXPECTED):
        shipment,invoice,payment=(observed[k] for k in stages);qty,net,tax,gross=expected
        require(all(r['c_bpartner_id']==customer_id for r in (shipment,invoice,payment)),'Cross-customer documents')
        require(shipment['c_order_id']==invoice['c_order_id']==order_id,'Documents are not linked to order')
        sl=only('m_inoutline',m_inout_id=shipment['m_inout_id']);line=only('c_invoiceline',c_invoice_id=invoice['c_invoice_id'])
        require(sl['m_product_id']==line['m_product_id']==product_id and sl['c_orderline_id']==line['c_orderline_id']==ol['c_orderline_id'],'Split document line links differ')
        require(number(sl['movementqty'])==number(line['qtyinvoiced'])==qty,'Split quantities differ')
        require(number(invoice['totallines'])==number(line['linenetamt'])==net and number(invoice['grandtotal'])==gross,'Invoice rounding differs')
        it=only('c_invoicetax',c_invoice_id=invoice['c_invoice_id']);require(number(it['taxamt'])==tax and it['c_tax_id']==107,'Invoice tax differs')
        require(payment['c_invoice_id']==invoice['c_invoice_id'] and number(payment['payamt'])==gross and invoice['ispaid']=='Y','Split invoice not fully paid')
        for key,value in ((stages[1]+'.net',net),(stages[1]+'.total',gross),(stages[2]+'.amount',gross)):
            require(number(trace[key])==value,'Trace differs from native money: '+key)
        allocations=[r for r in table('c_allocationline') if r['c_invoice_id']==invoice['c_invoice_id'] and r['c_payment_id']==payment['c_payment_id']]
        require(allocations and sum(number(r['amount']) for r in allocations)==gross,'Payment allocation differs')
        accounting_keys.update(((318,invoice['c_invoice_id']),(335,payment['c_payment_id'])))
        for allocation in allocations:
            header=only('c_allocationhdr',c_allocationhdr_id=allocation['c_allocationhdr_id'])
            require(header['docstatus']=='CO','Allocation not completed');accounting_keys.add((735,header['c_allocationhdr_id']))
        summary.append({'quantity':str(qty),'net':str(net),'tax':str(tax),'gross':str(gross),'paid':True})
    require(sum(number(r['grandtotal']) for r in invoices)==number(order['grandtotal']),'Split invoice total differs from order')
    facts=[r for r in table('fact_acct') if (r['ad_table_id'],r['record_id']) in accounting_keys]
    require({(r['ad_table_id'],r['record_id']) for r in facts}==accounting_keys,'Missing document accounting')
    balances={}
    for row in facts:
        key=(row['ad_table_id'],row['record_id'],row['c_acctschema_id'],row['c_currency_id'])
        previous=balances.get(key,(Decimal(0),Decimal(0)))
        balances[key]=(previous[0]+number(row['amtacctdr'])-number(row['amtacctcr']),previous[1]+number(row['amtsourcedr'])-number(row['amtsourcecr']))
    require(all(v==(0,0) for v in balances.values()),'Unbalanced accounting')
    stock=[r for r in table('m_storageonhand') if r['m_product_id']==product_id]
    require(stock and sum(number(r['qtyonhand']) for r in stock)==number(trace['inventory.onHand'])==7,'Closing stock differs')
    moves=[r for r in table('m_transaction') if r['m_product_id']==product_id]
    require(len(moves)==3 and sorted(number(r['movementqty']) for r in moves)==[Decimal(-2),Decimal(-1),Decimal(10)],'Inventory movements differ')
    return seal({'artifact_type':'lightyear-native-partial-invoicing-lane','lane':lane,'evidence_class':'native-application-and-database-observation',
      'trace':trace,'trace_sha256':trace_hash,'state_sha256':snapshot['content_sha256'],'execution_sha256':execution['content_sha256'],
      'harness_sha256':execution['harness_sha256'],'invoices':summary,'balanced_accounting_groups':len(balances),
      'accounting_entries_verified':len(facts),'status':'passed-bounded-partial-invoicing-readback','independently_attested':False})


def compare_lanes(lanes,effects):
    require(set(lanes)=={'oracle','postgresql'},'Both native lanes required');verify(effects)
    for lane,value in lanes.items():
        verify(value);require(value['lane']==lane and value['evidence_class']=='native-application-and-database-observation','Invalid native lane')
        require(value['state_sha256']==effects['state_sha256'][lane],'Effects/readback mismatch')
    require(lanes['oracle']['harness_sha256']==lanes['postgresql']['harness_sha256'],'Harness differs across lanes')
    require(lanes['oracle']['invoices']==lanes['postgresql']['invoices'],'Invoice outcomes differ')
    a,b=(lanes[l]['trace'] for l in ('oracle','postgresql'));require(set(a)==set(b),'Trace fields differ')
    numeric={'firstInvoice.total','firstInvoice.net','invoice.total','invoice.net','firstPayment.amount','payment.amount',
             'invoicing.afterFirst','invoicing.final','inventory.onHand','order.total','order.net','openingInventory.quantity'}
    differences=[]
    for field in a:
        if a[field]==b[field]:continue
        rule=None
        if field=='database' and a[field]=='oracle' and b[field]=='postgresql':rule='expected-engine-identity'
        elif field.endswith('.uuid') and valid_uuid(a[field]) and valid_uuid(b[field]):rule='validated-generated-uuid'
        elif field in numeric and number(a[field])==number(b[field]):rule='exact-decimal-value'
        differences.append({'field':field,'oracle':a[field],'postgresql':b[field],'rule':rule})
    equivalent=effects['admitted_for_selected_journeys'] and not effects['unresolved_differences'] and all(d['rule'] for d in differences)
    return seal({'artifact_type':'lightyear-native-partial-invoicing-comparison','status':'passed-bounded-partial-invoicing-equivalence' if equivalent else 'partial-invoicing-review-required',
      'bounded_partial_invoicing_equivalence':bool(equivalent),'invoices':lanes['oracle']['invoices'],'raw_trace_differences':differences,
      'unresolved_row_difference_count':len(effects['unresolved_differences']),'effect_checkpoint_sha256':effects['content_sha256'],
      'lane_receipt_sha256':{k:v['content_sha256'] for k,v in lanes.items()},'application_equivalence':False,'schema_equivalence':False,'platform_qualification':False,'independently_attested':False})


# The controller below reuses MS87's native lifecycle. It is separate from the
# builder transport: the builder never receives credentials or gate artifacts.
def prerequisite_replays(root,base,key):
    from .contracts import read_json
    from .journey_order import RUNS
    from lightyear_control_tower.decisions import verify_envelope
    previous=[]
    for path in (root/RUNS).glob('journey-*/receipt.json'):
        value=read_json(path)
        if verify_envelope(value,key) and value.get('unattended_run') and value.get('known_findings_reproduced') and value.get('executed_cases')==list(('boundary','diagnostic-first-only','operations')) and value.get('declaration_sha256')==base['declaration_sha256'] and value.get('plan_sha256')==base['content_sha256']:
            previous.append({'run_id':value['run_id'],'receipt_sha256':value['content_sha256'],'plan_sha256':value['plan_sha256']})
    require(len(previous)>=2,'MS88 native execution requires two admitted MS87 replays')
    return sorted(previous,key=lambda x:x['run_id'])


def extension_plan(root, build):
    from .journey_order import make_plan, save
    from .journey_runtime import JourneySigner, read_local, inventory, RUNS
    from .journey_builder import ORDER
    from .contracts import read_json
    from lightyear_control_tower.decisions import verify_envelope
    base=make_plan(root,read_local(root),inventory(root));key=JourneySigner(root).public
    declaration=read_json(root/ORDER);builder=read_json(build/'receipt.json')
    require(verify_envelope(builder,key) and builder['declaration_sha256']==file_hash(root/ORDER),'Builder declaration/signature differs')
    require(builder['harness_sha256']==file_hash(build/'workspace/LightyearPartialInvoiceTest.java'),'Generated code differs from builder receipt')
    for name,field in [('prompt.json','prompt_sha256'),('proposal.json','proposal_sha256'),('events.jsonl','events_sha256')]:
        require(file_hash(build/name)==builder[field],'Builder provenance differs')
    previous=prerequisite_replays(root,base,key)
    plan={k:v for k,v in base.items() if k!='content_sha256'}
    plan.update(mode='extend',cases=['partial-invoicing'],extension_declaration=declaration,
                extension_declaration_sha256=file_hash(root/ORDER),builder_receipt_sha256=builder['content_sha256'],
                builder_directory=build.relative_to(root).as_posix(),harness_sha256=builder['harness_sha256'],
                prerequisite_replays=sorted(previous,key=lambda x:x['run_id']),model_calls=builder['provider_invocations'])
    plan['implementation_sha256']['src/lightyear_calibration/partial_invoicing.py']=file_hash(Path(__file__))
    plan['implementation_sha256']['src/lightyear_calibration/journey_builder.py']=file_hash(root/'src/lightyear_calibration/journey_builder.py')
    return seal(plan)


def verify_run(run):
    from .contracts import read_json
    from .journey_order import LANES, RUNS, save
    from .journey_verify import entries, footprint, rebound_prior
    from .native_reconciliation import reconcile, HISTORY_POLICY
    from .application_effects import admit
    from lightyear_control_tower.decisions import verify_envelope
    run=Path(run).resolve();plan=read_json(run/'plan.json');verify(plan)
    root=run.parents[len(RUNS.parts)]
    key=(root/'work/ms87/operator/authority.public.pem').read_bytes()
    auth=read_json(run/'authorization.json')
    require(plan['mode']=='extend' and plan['cases']==['partial-invoicing'],'Unexpected extension scope')
    require(verify_envelope(auth,key) and auth['run_id']==run.name and auth['plan']['plan_sha256']==plan['content_sha256'],'Gate authorization differs')
    require((run/'authority.public.pem').read_bytes()==key,'Run public key differs from trust anchor')
    for name,expected in plan['inputs_sha256'].items():
        require('/' not in name and '\\' not in name and file_hash(run/'inputs'/name)==expected,'Gate input differs from pinned plan')
    require(file_hash(run/'inputs/partial-invoicing.java')==plan['harness_sha256'],'Generated gate input differs')
    selected=read_json(run/'selected-attempts.json')
    require(set(selected)=={'partial-invoicing'},'Unexpected selected case')
    attempt=selected['partial-invoicing']
    require(type(attempt) is int and 1<=attempt<=2,'Invalid selected native attempt')
    folder=run/'cases/partial-invoicing'/str(attempt)
    entry=entries(run,{'partial-invoicing':folder});writes=footprint({'partial-invoicing':folder})
    before={l:folder/'baseline'/l/'entry' for l in LANES};after={l:folder/'after'/l for l in LANES}
    prior=rebound_prior(run,before);keys=read_json(run/'inputs/primary-keys.json')
    executions={l:read_json(folder/'execution'/l/'execution.json') for l in LANES}
    base=reconcile(after,keys,before=before,prior=prior,policy=HISTORY_POLICY)
    effects=admit(base,after,before,keys,executions,prior_checkpoint=prior)
    lanes={l:verify_lane(after[l],folder/'execution'/l/'journey.xml',executions[l],folder/'execution'/l/'harness.java') for l in LANES}
    for lane in LANES:
        require(executions[lane]['harness_sha256']==plan['harness_sha256'],'Native execution did not use approved generated harness')
        save(folder/'verified'/(lane+'.json'),lanes[lane])
    comparison=compare_lanes(lanes,effects)
    for name,value in [('base',base),('effects',effects),('comparison',comparison)]:save(folder/'verified'/(name+'.json'),value)
    return seal({'artifact_type':'lightyear-partial-invoicing-gate','plan_sha256':plan['content_sha256'],
                 'passed':comparison['bounded_partial_invoicing_equivalence'],'entry':entry,'footprint':writes,
                 'comparison_sha256':comparison['content_sha256'],'comparison':comparison})


def bounded_gate(runner):
    """Run deterministic readback under the declared time and cancellation limits."""
    import os
    import subprocess
    import sys
    import time
    from .contracts import read_json
    from .journey_runtime import JourneyAbort
    definition=runner.plan['extension_declaration']['acceptance']['gates'][0]
    require(definition['command']==['python','-m','lightyear_calibration.partial_invoicing','verify','--run','{run}'],'Unexpected extension gate command')
    output=runner.run/'gate-logs/verify-partial-invoicing.log';output.parent.mkdir(exist_ok=True)
    args=[sys.executable,'-m','lightyear_calibration.partial_invoicing','verify','--run',str(runner.run)]
    with output.open('wb') as stream:
        process=subprocess.Popen(args,cwd=runner.root,stdout=stream,stderr=subprocess.STDOUT,
            env={**os.environ,'PYTHONPATH':str(runner.root/'src'),'PYTHONUTF8':'1'})
        started=time.monotonic()
        try:
            while process.poll() is None:
                runner.check_cancel()
                if time.monotonic()-started>=definition['timeout_seconds']:raise JourneyAbort('timeout')
                try:process.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
        finally:
            if process.poll() is None:process.kill();process.wait()
    require(process.returncode==0,'Partial-invoicing readback gate failed')
    result=read_json(runner.run/'gate.json');verify(result)
    require(result['plan_sha256']==runner.plan['content_sha256'],'Gate result belongs to another plan')
    return result


def execute_run(root, run):
    import gzip
    from .contracts import read_json, canonical
    from .journey_order import save, classify, UNCLAIMED
    from .journey_runtime import JourneySigner, LocalRunner, JourneyAbort, append_decision
    from lightyear_control_tower.decisions import verify_envelope
    from lightyear_workflow.campaign_journals import signed_append,check
    from lightyear_workflow.run_store import RunStore
    from lightyear_workflow.run_index import RunIndex
    from lightyear_workflow.convergence import INDEX_RELATIVE
    import signal
    plan=read_json(run/'plan.json');verify(plan);signer=JourneySigner(root);auth=read_json(run/'authorization.json')
    require(verify_envelope(auth,signer.public) and auth['run_id']==run.name and auth['plan']['plan_sha256']==plan['content_sha256'],'Invalid extension authorization')
    require(extension_plan(root,root/plan['builder_directory'])==plan,'Stale extension plan')
    store=RunStore(run/'journal');require(not store.events(),'Extension already started')
    def emit(kind,payload):return signed_append(store,signer,auth,kind,{k:v for k,v in payload.items() if k not in ('signature','content_sha256')},'journey')
    runner=LocalRunner(root,run,plan,emit);error=None;requests=[];gate=None;status='failed'
    def interrupted(*_):raise JourneyAbort('cancelled')
    handlers={sig:signal.signal(sig,interrupted) for sig in (signal.SIGINT,signal.SIGTERM)}
    emit('started',{'mode':'extend','builder_receipt_sha256':plan['builder_receipt_sha256'],'model_calls':plan['model_calls']})
    try:
        for attempt in range(1,3):
            try:
                emit('round',{'case':'partial-invoicing','attempt':attempt})
                folder=runner.prepare('partial-invoicing',attempt)
                for lane in ('oracle','postgresql'):
                    runner.checkpoint('execute-lane:partial-invoicing:'+lane)
                    value=runner.worker('execute',{'lane':lane,'output':runner.inside(folder/'execution'/lane),
                       'harness':'/output/inputs/partial-invoicing.java','harness_sha256':plan['harness_sha256'],
                       'test':'LightyearPartialInvoiceTest','source_commit':plan['declaration']['application']['source_commit'],'timeout_seconds':1200},timeout=1250)
                    emit('native-execution',{'case':'partial-invoicing','lane':lane,'exit_code':value['exit_code'],'execution_sha256':value['content_sha256']})
                    if value['exit_code']:raise JourneyAbort('timeout' if value['exit_code']==124 else 'harness-exception')
                    runner.worker('capture',{'lane':lane,'output':runner.inside(folder/'after'/lane)},timeout=1800)
                save(run/'selected-attempts.json',{'partial-invoicing':attempt})
                cleaned=runner.cleanup();emit('pair-cleanup',cleaned);require(cleaned['complete'],'Cleanup failure')
                runner.checkpoint('verify')
                gate=bounded_gate(runner)
                emit('gate',{'command':'verify-partial-invoicing','passed':gate['passed'],'receipt_sha256':gate['content_sha256']})
                if not gate['passed']:raise JourneyAbort('unknown-difference')
                emit('result',{'case':'partial-invoicing','boundary':{'model_calls':plan['model_calls']}})
                status='passed-bounded-partial-invoicing-equivalence';break
            except Exception as exc:
                code=exc.code if isinstance(exc,JourneyAbort) else 'gate-failed'
                emit('attempt-exception',{'classification':code,'exception_type':type(exc).__name__,'diagnostic':str(exc)[-1500:]})
                cleaned=runner.cleanup(retain=True);emit('pair-cleanup',cleaned);require(cleaned['complete'],'Cleanup failure')
                if not classify(code)['retryable'] or attempt==2:raise
    except Exception as exc:
        code=exc.code if isinstance(exc,JourneyAbort) else 'gate-failed';error={'classification':code,'exception_type':type(exc).__name__}
        emit('exception',error)
        if code=='unknown-difference':
            requests.append(append_decision(root,{**plan,'declaration_sha256':plan['extension_declaration_sha256']},'propose-normalization','Unexplained partial-invoicing difference',['partial-invoicing'],run.name));status='halted-for-decision'
    finally:
        cleaned=runner.cleanup(retain=error is not None)
        cleanup=signer.sign({'artifact_type':'lightyear-journey-cleanup','run_id':run.name,'plan_sha256':plan['content_sha256'],**cleaned})
        save(run/'cleanup.json',cleanup);emit('cleanup',cleanup)
        if not cleaned['complete']:status='failed';error={'classification':'cleanup-failure'}
        for request in requests:emit('blocked',{'reason':'human-decision-required','request':request})
        receipt=signer.sign({'artifact_type':'lightyear-native-journey-run','run_id':run.name,'mode':'extend',
          'plan_sha256':plan['content_sha256'],'declaration_sha256':plan['extension_declaration_sha256'],'status':status,'reason':status,
          'builder_receipt_sha256':plan['builder_receipt_sha256'],'agent_generated':True,'model_calls':plan['model_calls'],
          'known_findings_reproduced':False,'bounded_operations_equivalence':False,'bounded_partial_invoicing_equivalence':bool(gate and gate['passed'] and error is None),
          'executed_cases':['partial-invoicing'],'inherited_cases':[],'human_interventions_outside_designed_stops':sum(e['type']=='intervention' for e in store.events()),
          'unattended_run':False,'unattended_extension':error is None and cleaned['complete'],
          'cleanup_sha256':cleanup['content_sha256'],'requests':[r['id'] for r in requests],'error':error,'cloud_resources_started':False,**UNCLAIMED})
        emit('halted',receipt);save(run/'receipt.json',receipt)
        try:events=check(store.events(),auth,signer.public,'journey')
        finally:store.close()
        archive=run/(run.name+'.json.gz');archive.write_bytes(gzip.compress(canonical({'events':events}),mtime=0))
        RunIndex(root/INDEX_RELATIVE).record(run.name,'idempiere','ms88-partial-invoicing',events,archive)
        save(run/'journal.json',events)
        for sig,handler in handlers.items():signal.signal(sig,handler)
    return receipt


def main():
    import argparse
    import json
    import shutil
    import uuid
    from .contracts import read_json
    from .journey_order import RUNS, archived, save
    from .journey_runtime import JourneySigner, run_folder
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['plan','run','verify','factory-run'])
    parser.add_argument('--root',type=Path,default=Path('.'));parser.add_argument('--build',type=Path);parser.add_argument('--run',type=Path);parser.add_argument('--plan-sha256')
    parser.add_argument('--executable',type=Path);parser.add_argument('--prompt',type=Path)
    a=parser.parse_args();root=a.root.resolve()
    if a.command=='factory-run':
        from .journey_builder import build
        from .journey_order import make_plan
        from .journey_runtime import read_local, inventory
        require(a.executable and a.prompt and a.build,'Factory run requires the reviewed prompt, executable and build output path')
        prerequisite_replays(root,make_plan(root,read_local(root),inventory(root)),JourneySigner(root).public)
        build(root,a.build.resolve(),a.executable.resolve(),a.prompt.resolve())
    if a.command=='verify':
        result=verify_run(a.run.resolve());save(a.run.resolve()/'gate.json',result)
    else:
        plan=extension_plan(root,a.build.resolve());save(root/'work/ms88/plan.json',plan)
        if a.command=='plan':result={'plan_sha256':plan['content_sha256'],'mode':'extend','cloud_resources':False}
        else:
            require(a.command=='factory-run' or a.plan_sha256==plan['content_sha256'],'Stale extension plan')
            for path in (root/RUNS).glob('journey-*'):
                require((path/'receipt.json').exists() and read_json(path/'cleanup.json')['complete'],'An existing native run is active or needs recovery')
            run=run_folder(root,'journey-'+uuid.uuid4().hex);run.mkdir(parents=True)
            signer=JourneySigner(root);save(run/'plan.json',plan);(run/'authority.public.pem').write_bytes(signer.public)
            inputs=archived(root)
            inputs['partial-invoicing.java']=(a.build/'workspace/LightyearPartialInvoiceTest.java').read_bytes()
            for h in plan['declaration']['application']['harnesses']:inputs[h['id']+'.java']=(root/h['file']).read_bytes()
            (run/'inputs').mkdir()
            for name,data in inputs.items():(run/'inputs'/name).write_bytes(data)
            auth=signer.sign({'record_type':'native-journey-authorization','run_id':run.name,'plan':{'plan_sha256':plan['content_sha256']},
                 'operator_authorization':'User requested agent-built partial invoicing for MS88 and local execution; no semantic acceptance or claim promotion.'})
            save(run/'authorization.json',auth)
            print(json.dumps({'run_id':run.name,'status':'started'}),flush=True)
            import os,sys,subprocess
            kwargs={'cwd':root,'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,
                    'env':{**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONUTF8':'1'}}
            if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS
            else:kwargs['start_new_session']=True
            subprocess.Popen([sys.executable,'-m','lightyear_calibration.journey_runtime','watch',str(root),str(run),str(os.getpid())],**kwargs)
            try:result=execute_run(root,run)
            except BaseException:
                from .journey_runtime import recover
                recover(root,run,manual=False)
                raise
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
