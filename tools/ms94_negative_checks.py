"""Independent per-lane fault diagnosis; no business answers go to builder."""
from lightyear_calibration.contracts import CalibrationError,read_json,require,verify
from lightyear_calibration.ms94_faults import FAULTS
from lightyear_calibration.operations_journey import verify_lane
from lightyear_calibration.native_reconciliation import state,rows
from lightyear_calibration.journey_verify import footprint
from lightyear_calibration.application_journey import read_trace


def negative_checks(run,fault,gate):
    folder=run/'cases/operations/1';checks={}
    for lane in ('oracle','postgresql'):
        try:
            m=read_json(folder/'mutations'/(lane+'.json'));verify(m)
            require(m['lane']==lane and m['fault']==fault and m['committed'] and m['affected_rows']>0,'Incomplete mutation')
            where=folder/'execution'/lane; actual=None
            try:
                if fault=='outside-footprint':
                    from lightyear_calibration.application_effects import TABLES
                    a=state(folder/'baseline'/lane/'entry',lane);b=state(folder/'after'/lane,lane)
                    changed={t for t in a['tables'] if a['tables'][t]['row_multiset']!=b['tables'][t]['row_multiset']}
                    require(not changed-TABLES,FAULTS[fault])
                elif fault=='costing-wrong-organization':
                    from tools.qualification_procurement_scope import validate,EXTRA
                    current=folder/'after'/lane;old=folder/'baseline'/lane/'entry'
                    a=state(current,lane);b=state(old,lane)
                    tables=set(EXTRA)|{'c_orderline','m_inoutline','c_invoiceline','c_acctschema','m_matchinv','m_costdetail'}
                    validate({t:rows(current,a['tables'][t]) for t in tables},
                             {t:rows(old,b['tables'][t]) for t in EXTRA},read_trace(where/'journey.xml')[0])
                elif fault=='timestamp-outside-scope':
                    # Paired semantic rejection, with a verified mutation on each lane.
                    findings=gate.get('checks',{}).get('combined',{}).get('unresolved_row_differences',[])
                    if any(v.get('table')=='c_order' and v.get('column')=='dateordered' and lane in v for v in findings):
                        actual=FAULTS[fault]
                else:
                    verify_lane(folder/'after'/lane,where/'journey.xml',read_json(where/'execution.json'),(where/'harness.java').read_bytes())
            except CalibrationError as exc: actual=str(exc)
            message=(gate.get('error') or {}).get('message')
            correct=gate['status']=='business-failure' and actual==FAULTS[fault]
            if fault!='timestamp-outside-scope': correct=correct and message==FAULTS[fault]
            checks[lane]={'passed':correct,'rejection':actual,'expected_rejection':FAULTS[fault]}
        except Exception as exc: checks[lane]={'passed':False,'error_type':type(exc).__name__}
    return checks
