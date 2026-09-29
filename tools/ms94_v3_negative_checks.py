"""Negative-control evidence from each engine, independent of candidate assertions."""
from lightyear_calibration.contracts import read_json,require
from lightyear_calibration.journey_order import file_hash
from lightyear_calibration.native_reconciliation import state,rows
from tools.ms94_negative_checks_v2 import negative_checks as original


def negative_checks(run,fault,gate):
    if fault not in ('candidate-reposts-own-match','duplicate-trace-key'):
        return original(run,fault,gate)
    out={};folder=run/'cases/operations/1'
    for lane in ('oracle','postgresql'):
        where=folder/'execution'/lane
        try:
            execution=read_json(where/'execution.json')
            if fault=='duplicate-trace-key':
                log=(where/'maven.log').read_text(encoding='utf-8')
                passed=gate['status']=='execution-failure' and execution['exit_code']!=0 and 'Duplicate trace key' in log
                out[lane]={'passed':passed,'log_sha256':file_hash(where/'maven.log'),
                           'expected_rejection':'Duplicate trace key','scored_as_judge_mutation':False}
            else:
                snapshot=state(folder/'after'/lane,lane)
                observed=rows(folder/'after'/lane,snapshot['tables']['t_fact_acct_history'])
                baseline=state(folder/'baseline'/lane/'entry',lane)
                prior=rows(folder/'baseline'/lane/'entry',baseline['tables']['t_fact_acct_history'])
                bound=read_json(run/'inputs/history-bound.json')
                increase=len(observed)-len(prior)
                passed=(gate['status']=='business-failure' and execution['exit_code']==0 and
                        (gate.get('error') or {}).get('type')=='BusinessViolation' and
                        (gate.get('error') or {}).get('message')=='Candidate bypasses the public posting API' and
                        increase>bound['maximum_history_rows'])
                out[lane]={'passed':passed,'observed_history_additions':increase,
                           'state_sha256':snapshot['content_sha256'],'expected_rejection':'candidate-initiated own-match repost'}
        except Exception as error:out[lane]={'passed':False,'error_type':type(error).__name__}
    return out
