"""Prospective A2 planted sources; never builder inputs or cohort successes."""
from pathlib import Path
from lightyear_calibration.contracts import read_json,require,seal
from lightyear_calibration.journey_order import file_hash,save

AREA=Path('factory/idempiere/qualification-ms94-v6/diagnostic-controls')
BASE=Path('factory/idempiere/qualification-ms94-v5/references/retained/LightyearOperationsTest.java')
FAULTS=('reversal-allocation-assertion','invoice-null-dereference','shipment-api-rejection',
        'support-throw','missing-rollback-wait','nonnumeric-order-id')


def replace_once(source,old,new):
    require(source.count(old)==1,'Planted control anchor is not unique')
    return source.replace(old,new,1)


def construct(source,fault):
    require(fault in FAULTS,'Unknown planted fault')
    expected={'status':'execution-failure','equipment_suspect':False}
    marker=None
    if fault=='reversal-allocation-assertion':
        needle='            recovery(ctx, template);'
        addition='''            MAllocationHdr[] reversalAllocations = MAllocationHdr.getOfInvoice(ctx, creditReversal.get_ID(), trx);
            require(reversalAllocations.length > 0, "Planted control needs a reversal allocation");
            for (MAllocationHdr reversalAllocation : reversalAllocations) {
                for (MAcctSchema schema : schemas) {
                    int reversalFacts = DB.getSQLValueEx(trx,
                        "SELECT COUNT(*) FROM Fact_Acct WHERE AD_Table_ID=? AND Record_ID=? AND C_AcctSchema_ID=?",
                        reversalAllocation.get_Table_ID(), reversalAllocation.get_ID(), schema.get_ID());
                    if (reversalFacts == 0) throw new AssertionError("Planted non-empty reversal-allocation assertion");
                }
            }
'''
        source=replace_once(source,needle,addition+needle)
        marker='if (reversalFacts == 0) throw new AssertionError'
        expected.update(thrown_by='candidate',public_stage='reversal allocation',exception_class='AssertionError')
    elif fault=='invoice-null-dereference':
        needle='            post(invoice, schemas);'
        source=replace_once(source,needle,'''            MInvoice unloadedInvoice = new Query(ctx, MInvoice.Table_Name, "C_Invoice_ID=?", trx)
                .setParameters(-1).first();
            unloadedInvoice.getGrandTotal(); // planted null dereference
'''+needle)
        marker='unloadedInvoice.getGrandTotal();'
        expected.update(thrown_by='candidate',public_stage='invoice',exception_class='NullPointerException')
    elif fault=='shipment-api-rejection':
        needle='            MInOut shipment = new MInOut(order,'
        source=replace_once(source,needle,'''            MOrder wrongShipmentOrder = new MOrder(ctx, 0, trx);
            wrongShipmentOrder.setC_DocType_ID(DictionaryIDs.C_DocType.MM_SHIPMENT.id);
            new MInOut(wrongShipmentOrder, 0, businessDate); // wrong document type for automatic shipment selection
'''+needle)
        marker='new MInOut(wrongShipmentOrder, 0, businessDate);'
        expected.update(thrown_by='application',public_stage='shipment',exception_class='AdempiereException')
    elif fault=='support-throw':
        needle='    public static void postOnce(org.compiere.model.PO model, org.compiere.model.MAcctSchema[] schemas) {'
        source=replace_once(source,needle,needle+'\n        if (model != null) throw new IllegalStateException("Planted test-only support failure");')
        expected.update(equipment_suspect=True,disposition='halted-equipment-suspect')
    elif fault=='missing-rollback-wait':
        source=replace_once(source,'            Thread.sleep(1500); // Allow independent observation before any retry can commit.',
                            '            // Planted omission of the post-rollback observation wait.')
        expected.update(status='contract-violation',code='missing-public-rollback-witness')
    elif fault=='nonnumeric-order-id':
        needle='            lifecycle("status", "completed-and-committed");'
        source=replace_once(source,needle,'            lifecycle("order.id", "not-a-number");\n'+needle)
        expected.update(status='contract-violation',code='invalid-public-identifier',field='order.id')
    if marker:
        lines=[i for i,line in enumerate(source.splitlines(),1) if marker in line]
        require(len(lines)==1,'Planted throwing line must be unique')
        expected['candidate_frame']={'method':'operationsJourney','line':lines[0]}
    return source,expected


def prepare(root):
    root=Path(root);base=root/BASE
    original=base.read_text(encoding='utf-8')
    require(file_hash(base)==read_json(base.parent/'manifest.json')['harness_sha256'],'Retained source changed')
    results={}
    for fault in FAULTS:
        folder=root/AREA/fault;require(not folder.exists(),'Do not replace a planted source')
        source,expected=construct(original,fault);folder.mkdir(parents=True)
        path=folder/'LightyearOperationsTest.java';path.write_bytes(source.encode('utf-8'))
        support=source[source.index('final class JourneySupport {'):]
        baseline_support=original[original.index('final class JourneySupport {'):]
        require((support==baseline_support)==(fault!='support-throw'),'Unexpected support change')
        value=seal({'artifact_type':'ms94-a2-planted-fault-source','fault':fault,
            'base_reference_sha256':file_hash(base),'harness_sha256':file_hash(path),
            'expected':expected,'test_only_support_change':fault=='support-throw',
            'human_source_attestation':False,'qualification_only':True,'autonomous_success':False,'model_calls':0})
        save(folder/'manifest.json',value);results[fault]=value
    return results


def assess(gate,diagnostics,suspect,manifest):
    """Require exact declared provenance/stage/class, never a generic rejection."""
    expected=manifest['expected'];ok=gate['status']==expected['status'] and suspect==expected['equipment_suspect']
    runtime=[d for d in diagnostics if d.get('category')=='candidate-runtime-exception']
    if expected['equipment_suspect']:
        return ok and diagnostics==[]
    if expected['status']=='contract-violation':
        return ok and not runtime and any(d.get('category')=='trace-contract' and d.get('code')==expected['code']
            and ('field' not in expected or d.get('field')==expected['field']) for d in diagnostics)
    fields=('thrown_by','public_stage','exception_class','candidate_frame')
    return ok and len(runtime)==1 and runtime[0]['lanes']=='both' and all(runtime[0].get(k)==expected[k] for k in fields)


if __name__=='__main__':
    import json
    print(json.dumps(prepare(Path('.').resolve()),indent=2))
