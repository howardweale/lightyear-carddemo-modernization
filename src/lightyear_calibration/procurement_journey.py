"""Independent procure-to-pay readback; inputs fixed before any generation."""
from decimal import Decimal
import hashlib
from pathlib import Path
from .contracts import require,seal,verify
from .application_journey import read_trace,number
from .native_reconciliation import state,rows,valid_uuid
from .operations_journey import SOURCE_COMMIT
from .boundary_contract import expected,INPUT

STAGES={'vendor':'c_bpartner','vendorLocation':'c_bpartner_location','product':'m_product',
        'productPrice':'m_productprice','purchaseOrder':'c_order','receipt':'m_inout',
        'vendorInvoice':'c_invoice','vendorPayment':'c_payment'}
EXTRA_TABLES=frozenset(('m_matchinv','m_matchpo','m_costdetail','m_product_po'))


def bindings(trace):
    result={}
    for stage,table in STAGES.items():
        result[stage+'.uuid']=(table,table+'_uu',{table+'_id':int(trace[stage+'.id'])})
    for field,stage,table,column,join in (
        ('purchaseOrder.net','purchaseOrder','c_order','totallines','c_order_id'),
        ('purchaseOrder.total','purchaseOrder','c_order','grandtotal','c_order_id'),
        ('purchaseOrder.priceActual','purchaseOrder','c_orderline','priceactual','c_order_id'),
        ('purchaseOrder.discount','purchaseOrder','c_orderline','discount','c_order_id'),
        ('receipt.quantity','receipt','m_inoutline','movementqty','m_inout_id'),
        ('vendorInvoice.total','vendorInvoice','c_invoice','grandtotal','c_invoice_id'),
        ('vendorPayment.amount','vendorPayment','c_payment','payamt','c_payment_id')):
        result[field]=(table,column,{join:int(trace[stage+'.id'])})
    result['inventory.onHand']=('m_storageonhand','qtyonhand',{'m_product_id':int(trace['product.id']),'$aggregate':'sum'})
    return result


def verify_lane(folder,trace_path,execution,harness_bytes):
    verify(execution);lane=execution['lane'];trace,trace_hash=read_trace(trace_path)
    require(lane in ('oracle','postgresql') and execution['exit_code']==0,'Procurement process failed')
    require(execution['application_source_commit']==SOURCE_COMMIT and execution['harness_sha256']==hashlib.sha256(harness_bytes).hexdigest(),'Procurement source identity differs')
    require(trace.get('status')=='completed-and-committed' and trace.get('database')==lane and trace.get('newIssueCount')=='0','Missing clean procurement completion')
    snapshot=state(Path(folder),lane);require(snapshot['evidence_class']=='native-database-observation','Non-native procurement readback')
    cache={}
    def table(name):
        if name not in cache:cache[name]=rows(Path(folder),snapshot['tables'][name])
        return cache[name]
    def only(name,**where):
        values=[r for r in table(name) if all(r.get(k)==v for k,v in where.items())]
        require(len(values)==1,'Missing or ambiguous procurement row: '+name);return values[0]
    observed={}
    for stage,name in STAGES.items():
        row=only(name,**{name+'_id':int(trace[stage+'.id'])})
        require(trace.get(stage+'.saved')=='true' and valid_uuid(trace[stage+'.uuid']) and row[name+'_uu']==trace[stage+'.uuid'],'Procurement stage identity differs')
        if stage in ('purchaseOrder','receipt','vendorInvoice','vendorPayment'):
            require(trace[stage+'.status']==row['docstatus']=='CO','Procurement document incomplete')
        observed[stage]=row
    v,loc,p,price,order,receipt,invoice,payment=(observed[x] for x in STAGES)
    require(v['isvendor']=='Y' and v['name']==INPUT['customer_name'] and v['description'] in (None,''),'Vendor role or text differs')
    require(p['ispurchased']==p['isstocked']=='Y','Product is not purchased stock')
    require(loc['c_bpartner_id']==v['c_bpartner_id'] and price['m_product_id']==p['m_product_id'],'Procurement setup links differ')
    for doc in (order,receipt,invoice,payment):require(doc['c_bpartner_id']==v['c_bpartner_id'],'Vendor document link differs')
    for doc in (order,receipt,invoice):
        require(doc['issotrx']=='N' and doc['c_bpartner_location_id']==loc['c_bpartner_location_id'],'Sales document substituted for purchasing')
    require(payment['isreceipt']=='N' and payment['c_invoice_id']==invoice['c_invoice_id'],'Payment must be outbound and settle this vendor invoice')
    require(receipt['c_order_id']==order['c_order_id'],'Receipt not linked to purchase order')
    ol=only('c_orderline',c_order_id=order['c_order_id']);rl=only('m_inoutline',m_inout_id=receipt['m_inout_id']);il=only('c_invoiceline',c_invoice_id=invoice['c_invoice_id'])
    for line in (ol,rl,il):require(line['m_product_id']==p['m_product_id'],'Procurement product links differ')
    require(rl['c_orderline_id']==ol['c_orderline_id'] and il['m_inoutline_id']==rl['m_inoutline_id'],'Purchase order, receipt and invoice line links differ')
    require(number(ol['qtyordered'])==number(ol['qtydelivered'])==number(ol['qtyinvoiced'])==number(rl['movementqty'])==number(il['qtyinvoiced'])==3,'Procurement quantities differ')
    require(number(ol['priceactual'])==Decimal('17.9955') and number(ol['pricelist'])==Decimal('19.995'),'Procurement fractional prices differ')
    require(number(ol['discount'])==Decimal(INPUT['discount_percent']),'Procurement discount differs')
    require(number(ol['linenetamt'])==number(il['linenetamt'])==expected()['net'],'Procurement line net differs')
    require(number(il['priceactual'])==expected()['actual_price'],'Vendor invoice price differs')
    require(number(order['totallines'])==number(invoice['totallines'])==expected()['net'],'Procurement net differs')
    require(number(order['grandtotal'])==number(invoice['grandtotal'])==number(payment['payamt'])==expected()['gross'],'Procurement gross or payment differs')
    require(invoice['ispaid']=='Y' and trace['vendorInvoice.paid']=='true','Vendor invoice unpaid')
    ot=only('c_ordertax',c_order_id=order['c_order_id']);it=only('c_invoicetax',c_invoice_id=invoice['c_invoice_id'])
    require(ot['c_tax_id']==it['c_tax_id']==ol['c_tax_id']==107,'Procurement tax fixture differs')
    require(number(ot['taxamt'])==number(it['taxamt'])==expected()['tax'],'Procurement tax or rounding differs')
    require(number(ot['taxbaseamt'])==number(it['taxbaseamt'])==expected()['net'],'Procurement tax base differs')
    stock=[r for r in table('m_storageonhand') if r['m_product_id']==p['m_product_id']]
    require(stock and sum(number(r['qtyonhand']) for r in stock)==3,'Receipt did not increase native stock by three')
    moves=[r for r in table('m_transaction') if r['m_product_id']==p['m_product_id']]
    require(len(moves)==1 and moves[0]['movementtype']=='V+' and number(moves[0]['movementqty'])==3 and moves[0]['m_inoutline_id']==rl['m_inoutline_id'],'Missing inbound receipt stock movement')
    allocations=[r for r in table('c_allocationline') if r['c_invoice_id']==invoice['c_invoice_id'] and r['c_payment_id']==payment['c_payment_id']]
    require(allocations and sum(number(r['amount']) for r in allocations)==-number(payment['payamt']),'Outbound allocation sign or amount differs')
    accounting_keys={(318,invoice['c_invoice_id']),(335,payment['c_payment_id'])}
    for allocation in allocations:
        hdr=only('c_allocationhdr',c_allocationhdr_id=allocation['c_allocationhdr_id'])
        require(hdr['docstatus']=='CO','Procurement allocation incomplete');accounting_keys.add((735,hdr['c_allocationhdr_id']))
    facts=[r for r in table('fact_acct') if (r['ad_table_id'],r['record_id']) in accounting_keys]
    require({(r['ad_table_id'],r['record_id']) for r in facts}==accounting_keys,'Procurement accounting missing')
    balances={}
    for row in facts:
        key=tuple(row[x] for x in ('ad_table_id','record_id','c_acctschema_id','c_currency_id'))
        old=balances.get(key,(Decimal(0),Decimal(0)))
        balances[key]=(old[0]+number(row['amtacctdr'])-number(row['amtacctcr']),old[1]+number(row['amtsourcedr'])-number(row['amtsourcecr']))
    require(all(x==(0,0) for x in balances.values()),'Procurement accounting unbalanced')
    require(all(observed[x]['posted']=='Y' for x in ('vendorInvoice','vendorPayment')),'Procurement documents unposted')
    return seal({'artifact_type':'lightyear-native-procurement-lane','lane':lane,'trace':trace,'trace_sha256':trace_hash,
                 'state_sha256':snapshot['content_sha256'],'harness_sha256':execution['harness_sha256'],
                 'status':'passed-bounded-procure-to-pay','accounting_entries_verified':len(facts),
                 'balanced_accounting_groups':len(balances),'evidence_class':'native-application-and-database-observation'})
