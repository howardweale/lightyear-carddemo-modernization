"""Independent gates for declared journeys; no model participates in verdicts."""
from pathlib import Path
from .contracts import canonical, read_json, require, seal, verify
from .journey_order import LANES, CASES, GATES, COMMANDS, RUNS, save, known_findings, file_hash, diagnostic_profile
from .native_reconciliation import state, rows, reconcile, HISTORY_POLICY
from .native_catalog import read_capture
from .application_effects import admit, TABLES
from .application_journey import read_trace
from .schema_equivalence import assess
from . import boundary_journey, operations_journey


def attempts(run):
    value=read_json(run/'selected-attempts.json')
    require(set(value)==set(CASES),'Incomplete selected attempt set')
    for case, number in value.items():
        require(type(number) is int and 1 <= number <= 2,'Invalid selected attempt')
    auth=read_json(run/'authorization.json')
    from lightyear_control_tower.decisions import verify_envelope
    key=(run/'authority.public.pem').read_bytes()
    require(verify_envelope(auth,key),'Run authorization signature invalid')
    references=auth.get('case_references',{})
    result={}
    for case,number in value.items():
        if case in references:
            ref=references[case]
            from lightyear_execution.journey_network import InternalOnlyNetwork
            InternalOnlyNetwork(ref['run_id'])
            parent=run.parent/ref['run_id'];receipt=read_json(parent/'receipt.json')
            require(verify_envelope(receipt,key) and receipt['content_sha256']==ref['receipt_sha256'], 'Resume parent receipt differs')
            require(receipt['plan_sha256']==auth['plan']['plan_sha256'],'Resume cannot inherit a different plan')
            require(read_json(parent/'cleanup.json')['complete'],'Resume parent cleanup incomplete')
            require(number==ref['attempt'],'Resume attempt differs')
            result[case]=parent/'cases'/case/str(number)
        else:result[case]=run/'cases'/case/str(number)
    return result


def entries(run, folders):
    findings=[]
    for case,folder in folders.items():
        catalogs={}
        for lane in LANES:
            base=folder/'baseline'/lane
            expected=read_json(run/'inputs'/(lane+'-entry-multisets.json'))
            for moment in ('before','after','entry'):
                snapshot=state(base/moment,lane)
                require({k:v['row_multiset'] for k,v in snapshot['tables'].items()}==expected,'Entry row multisets differ from admitted state')
            catalogs[lane]=read_capture(base/'catalog.json')
            require(catalogs[lane]['import_binding']=={'ms84_checkpoint_sha256':read_json(run/'inputs/checkpoint.json')['content_sha256'],'state_sha256':state(base/'after',lane)['content_sha256']},'Catalog lineage differs from verified entry state')
            probes=read_json(base/'probes.json');verify(probes)
            require(probes['catalog_sha256']==catalogs[lane]['content_sha256'],'Probe catalog differs')
            require(probes['expected_cases']==probes['expectations_met']==30 and len(probes['cases'])==30
                    and all(x['expectation_met'] for x in probes['cases']) and probes['transaction_rolled_back'] is True,'Constraint entry gate failed')
        assessment=assess(catalogs)
        c=assessment['counts']
        require(c['foreign_key_catalog_matches']==3826 and c['foreign_key_missing_relationships']==c['nullable_differences']==0,'Schema successor differs')
        findings.append({'case':case,'constraint_checks_per_lane':30,'matching_foreign_keys':3826})
    return findings


def rebound_prior(run, before):
    prior=read_json(run/'inputs/checkpoint.json');verify(prior)
    for lane,folder in before.items():
        snap=state(folder,lane)
        require({k:v['row_multiset'] for k,v in snap['tables'].items()}==read_json(run/'inputs'/(lane+'-entry-multisets.json')),'Cannot rebind a changed entry state')
    return seal({**{k:v for k,v in prior.items() if k!='content_sha256'},
                 'replayed_checkpoint_sha256':prior['content_sha256'],
                 'state_sha256':{lane:state(folder,lane)['content_sha256'] for lane,folder in before.items()}})


def comparisons(run, folders):
    results={}; keys=read_json(run/'inputs/primary-keys.json')
    for case, verifier in [('boundary',boundary_journey),('operations',operations_journey)]:
        folder=folders[case];before={lane:folder/'baseline'/lane/'entry' for lane in LANES}
        after={lane:folder/'after'/lane for lane in LANES}
        executions={lane:read_json(folder/'execution'/lane/'execution.json') for lane in LANES}
        prior=rebound_prior(run,before)
        base=reconcile(after,keys,before=before,prior=prior,policy=HISTORY_POLICY)
        effects=admit(base,after,before,keys,executions,prior_checkpoint=prior)
        lane_results={}
        for lane in LANES:
            where=folder/'execution'/lane
            lane_results[lane]=verifier.verify_lane(after[lane],where/'journey.xml',executions[lane],(where/'harness.java').read_bytes())
            save(folder/'verified'/(lane+'.json'),lane_results[lane])
        compared=verifier.compare_lanes(lane_results,effects)
        for name,value in [('base',base),('effects',effects),('comparison',compared)]:save(folder/'verified'/(name+'.json'),value)
        results[case]={'comparison':compared,'effects':effects}
    return results


def diagnostic(run, folder):
    """Only the exact recorded fault is expected. No equivalence is inferred."""
    plan=read_json(run/'plan.json');verify(plan)
    result={}
    for lane in LANES:
        where=folder/'execution'/lane
        e=read_json(where/'execution.json');verify(e)
        require(e['harness_sha256']==plan['diagnostic_harness_sha256']==file_hash(where/'harness.java'),'Diagnostic harness changed')
        require(e['application_source_commit']==plan['declaration']['application']['source_commit'],'Diagnostic application changed')
        trace,_=read_trace(where/'journey.xml')
        log=(where/'maven.log').read_text(encoding='utf-8')
        result[lane+'_exit_code']=e['exit_code']
        if lane=='oracle':
            result['exact_oracle_error']='ORA-03049' in log and 'FOR UPDATE FETCH FIRST 2 ROWS ONLY' in log
            snap=state(folder/'after'/lane,lane)
            issues=rows(folder/'after'/lane,snap['tables']['ad_issue'])
            old=state(folder/'baseline'/lane/'entry',lane)
            previous={r['ad_issue_id'] for r in rows(folder/'baseline'/lane/'entry',old['tables']['ad_issue'])}
            new=[r for r in issues if r['ad_issue_id'] not in previous]
            require(sorted([diagnostic_profile(row) for row in new],key=canonical)==read_json(run/'inputs/diagnostic-issues.json'),'Diagnostic issue profiles differ from the archived firstOnly failure')
            require(all(row['loggername']=='org.compiere.model.Query' or 'LightyearOperationsTest.creditIncrement' in row['stacktrace'] for row in new),'Secondary diagnostic issue arose outside the expected harness call')
            result['oracle_issue_profiles_reproduced']=len(new)
        else:result['postgresql_completed']=trace.get('status')=='completed-and-committed'
    return result


def footprint(folders):
    findings=[]
    for case,folder in folders.items():
        for lane in LANES:
            before=state(folder/'baseline'/lane/'entry',lane);after=state(folder/'after'/lane,lane)
            require(set(before['tables'])==set(after['tables']),'Table inventory changed')
            allowed=TABLES | ({'ad_issue'} if case=='diagnostic-first-only' and lane=='oracle' else set())
            changed=[t for t in before['tables'] if before['tables'][t]['row_multiset']!=after['tables'][t]['row_multiset']]
            business_require(not set(changed)-allowed,'Write outside declared footprint or new application issue')
            findings.append({'case':case,'lane':lane,'changed_tables':sorted(changed)})
    return findings


def verify_gate(run,command):
    run=Path(run).resolve();plan=read_json(run/'plan.json');verify(plan)
    from lightyear_control_tower.decisions import verify_envelope
    root=run.parents[len(RUNS.parts)]
    key=(root/'work/ms87/operator/authority.public.pem').read_bytes()
    auth=read_json(run/'authorization.json')
    require(verify_envelope(auth,key) and auth['run_id']==run.name and auth['plan']['plan_sha256']==plan['content_sha256'], 'Gate authorization differs')
    require((run/'authority.public.pem').read_bytes()==key,'Run public key differs from trust anchor')
    for name,expected in plan.get('inputs_sha256',{}).items():
        require('/' not in name and '\\' not in name and file_hash(run/'inputs'/name)==expected,'Gate input differs from pinned plan')
    for harness in plan['declaration']['application']['harnesses']:
        require(file_hash(run/'inputs'/(harness['id']+'.java'))==harness['sha256'],'Gate harness differs from declaration')
    if command=='verify-cleanup':
        from lightyear_control_tower.decisions import verify_envelope
        cleanup=read_json(run/'cleanup.json')
        require(verify_envelope(cleanup,(run/'authority.public.pem').read_bytes()),'Invalid cleanup signature')
        require(cleanup['run_id']==run.name and cleanup['plan_sha256']==plan['content_sha256'],'Cleanup scope differs')
        require(cleanup['complete'] is True and not cleanup['remaining_containers'] and not cleanup['remaining_networks']
                and cleanup['credentials_destroyed'] is True,'Cleanup incomplete')
        details={'cleanup_sha256':cleanup['content_sha256']}
    else:
        folders=attempts(run)
        if command=='verify-entry':details=entries(run,folders)
        elif command=='verify-footprint':details=footprint(folders)
        else:
            results=comparisons(run,folders)
            b=results['boundary']['comparison'];o=results['operations']['comparison']
            if command=='verify-outcomes':
                require(b['passed_check_count']=={'oracle':14,'postgresql':15},'Unexpected business outcome')
                require(o['bounded_operations_equivalence'] is True,'Operational business outcome failed')
                details={'boundary':b['passed_check_count'],'operations':o['status']}
            elif command=='verify-differences':
                unexplained=results['boundary']['effects']['unresolved_differences']
                require(len(unexplained)==1 and unexplained[0]['table']=='m_inout' and unexplained[0]['column']=='shipdate'
                        and unexplained[0]['oracle']=='2026-09-26T12:34:56'
                        and unexplained[0]['postgresql']=='2026-09-26T12:34:56.123456','Unknown difference requires human decision')
                require(not results['operations']['effects']['unresolved_differences'],'Unknown operations difference')
                details={'boundary_known_unresolved':1,'operations_unresolved':0}
            elif command=='verify-known-findings':
                d=diagnostic(run,folders['diagnostic-first-only']);known=known_findings(b,d)
                require(all(known.values()),'Known finding changed or disappeared')
                details={'known_findings':known,'diagnostic':d}
            else:raise ValueError('Unsupported gate')
    result=seal({'artifact_type':'lightyear-journey-gate','command':command,'passed':True,
                 'plan_sha256':plan['content_sha256'],'details':details})
    save(run/'gates'/(command+'.json'),result)
    return result

from lightyear_calibration.ms94_v3_errors import business_require
