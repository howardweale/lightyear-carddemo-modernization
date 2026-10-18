"""Assemble an unsigned, fail-closed slice receipt from this CI run only."""
import argparse,json,os,sys,xml.etree.ElementTree as ET
from pathlib import Path
from hashlib import sha256
from collections import Counter

PROGRAMS=['COSGN00C','COMEN01C','COACTVWC','COACTUPC','COPAUS0C','COPAUS1C']
CLASSES=['SignonService','MenuService','AccountViewService','AccountUpdateService','AuthorizationListService','AuthorizationDetailService']
def hashed(path):return dict(path=str(path).replace('\\','/'),sha256=sha256(path.read_bytes()).hexdigest())
def mutation(path):
    if not path.exists():return dict(passed=False,reason='missing PIT XML',killed=0,total=0)
    nodes=ET.parse(path).getroot().findall('mutation');counts=Counter(n.attrib['status'] for n in nodes)
    present={n.findtext('mutatedClass').split('.')[-1].split('$')[0] for n in nodes}
    total=len(nodes);killed=counts['KILLED'];missing=sorted(set(CLASSES)-present)
    return dict(passed=bool(total and 10*killed>=9*total and not missing),killed=killed,total=total,
        percent=100*killed/total if total else None,threshold=90,missing_screen_handlers=missing,status_counts=dict(counts),
        denominator='every PIT mutation in configured screen-handler/helper scope; timeout, no-coverage and errors are not counted killed',report=hashed(path))
def main():
    a=argparse.ArgumentParser();a.add_argument('--artifacts',type=Path,required=True);a.add_argument('--out',type=Path,required=True);args=a.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    gates={};evidence=[];summaries={}
    for mode in ('api','browser','mutation'):
        root=args.artifacts/('carddemo-proof-'+mode);proof=root/'reference'/'summary.json'
        value=json.loads(proof.read_bytes()) if proof.exists() else {};summaries[mode]=value
        ok=value.get('passed') is True and set(value.get('programs_compared',[]))==set(PROGRAMS) and value.get('head')==os.environ.get('GITHUB_SHA')
        gates[mode+'-reference']=dict(passed=ok,programs_compared=len(value.get('programs_compared',[])),programs_required=6,
            interactions=value.get('interactions_compared',0),bms_interactions=value.get('bms_interactions_compared',0),completed_cases=value.get('completed_case_count',0),planned_cases=value.get('planned_case_count'),case_denominator_status=value.get('case_denominator_status','not measured'),cases=value.get('cases',[]),validated_fields=value.get('validated_fields',[]))
        if proof.exists():evidence.append(hashed(proof))
        if mode=='browser':
            f=root/'browser'/'summary.json';v=json.loads(f.read_bytes()) if f.exists() else {}
            gates['browser']=dict(passed=v.get('passed') is True and v.get('head')==os.environ.get('GITHUB_SHA') and v.get('interactions_compared',0)>0 and v.get('interactions_compared')==v.get('interactions_required'),interactions=v.get('interactions_compared',0),required=v.get('interactions_required',0))
        if mode=='mutation':gates['mutation']=mutation(root/'pit-reports'/'mutations.xml')
    results=json.loads(os.environ.get('PROOF_JOB_RESULTS','{}'));gates['ci-jobs']=dict(passed=bool(results) and all(v.get('result')=='success' for v in results.values()),results=results)
    manifests={}
    for category,patterns in {'generators':['src/lightyear_data/carddemo/*.py'],'pinned_sources':['spec/modernization/carddemo-screens/upstream/**/*','spec/modernization/carddemo-data/upstream/**/*'],'services':['factory/carddemo-web/service/src/main/**/*.java'],'ui':['factory/carddemo-web/ui/src/*'],'sessions':['factory/carddemo-web/runtime/prove_slice.py','tests/browser/carddemo-proof.mjs'],'mappings':['work/carddemo-web-bindings/*.json','work/carddemo-web-data/*.json']}.items():
        files=sorted({p for pattern in patterns for p in Path('.').glob(pattern) if p.is_file()});manifests[category]=[hashed(p) for p in files]
    artifact_files=[hashed(p) for p in sorted(args.artifacts.rglob('*')) if p.is_file()]
    passed=all(g['passed'] for g in gates.values()) and all(manifests.values())
    record=dict(schema='carddemo-slice-receipt/1',date='2026-10-18',status='proved-in-ci' if passed else 'incomplete',unsigned=True,
        source_head=os.environ.get('SOURCE_HEAD'),tested_commit=os.environ.get('GITHUB_SHA'),run_id=os.environ.get('GITHUB_RUN_ID'),
        upstream_commit='59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e',gates=gates,hashes=manifests,artifacts=artifact_files,
        scope=dict(programs=PROGRAMS,linked_action='COPAUS2C',baseline='bounded deterministic raw COBOL interpreter',shared_dependencies=['BMS parser','physical data plan and typed projection codec'],data='public VSAM fixture, seven synthetic IMS authorization rows, and one disclosed synthetic account/cross-reference pair for genuine no-change coverage'),
        quirks=['PAUTDTL1 uses the pinned DBD unique PAUT9CTS ascending byte-key sequence within each parent; synthetic insertion/twin ordinals remain provenance, not traversal order', 'Complete expected database states are content-addressed JSON files; browser and Java replay verify SHA-256 and compare every table and row after every interaction', 'Numeric DISPLAY condition names preserve invalid and LOW-VALUES bytes under the disclosed EBCDIC comparison bound until source validation', 'COPAUS2C fraud removal retains the AUTHFRDS audit row with AUTH_FRAUD=R through duplicate-insert UPDATE; it does not delete the row', 'Blank submitted group becomes LOW-VALUES and differs from stored spaces; post-commit resubmission preserves this behavior, while a separate synthetic PROOFGRP account retains strict no-change/no-error/no-write assertions', 'Visible terminal nulls project to blank cells; reference case artifacts retain exact symbolic-output hex and first-byte null selection', 'Positive update inputs explicitly use synthetic SSN 123-45-6789, OR/97001 and phone 2 (206)555-0102; original public fixture bytes and invalid cases remain preserved', 'COACTUPC account rewrite omits ZIP, preserved as source behavior','COMEN01 invalid option emits an error then faults on a table subscript; compare the emitted frame and database, discard that session, and make no continuation claim','BMS external constants use private symbolic bytes, not a native 3270 wire encoding','CSUTLDTC executes from pinned source; its CEEDAYS port models documented Gregorian YYYYMMDD feedback and Lilian epoch; native LE execution remains absent','SEND TEXT terminal responses have no BMS fields; complete text and ended state are compared','Menu options 3-10 route to one not-in-this-slice endpoint; those destination services and their screens are excluded, and boundary interactions are counted separately'],
        not_covered=['other fifteen maps and their services','native CICS, IMS and DB2 execution','production unloads or production data','release or z/OS acceptance','real signatures, import, activation or Phase 2'],
        factory_request=dict(status='unsigned-review-request',reviewer='Howard',action='review evidence and remaining gaps',signature=None,activation_authorized=False,phase2_authorized=False))
    # Require measured source-fault and date-boundary cases; missing results never count as passed.
    record['remaining_evidence_gaps']=[name for name,gate in gates.items() if not gate['passed']]
    for mode,value in summaries.items():
        if len(value.get('navigation_boundaries',[]))!=8:record['remaining_evidence_gaps'].append(mode+': missing outside-menu boundaries')
        if not value.get('source_faults'):record['remaining_evidence_gaps'].append(mode+': missing invalid-menu source-fault evidence')
        required={'leap-day-valid','leap-day-invalid'}
        if not required<={c['id'] for c in value.get('cases',[]) if c['status']=='passed'}:record['remaining_evidence_gaps'].append(mode+': missing bounded-date cases')
    record['acceptance_complete']=passed and not record['remaining_evidence_gaps']
    record['status']='proved-in-ci' if record['acceptance_complete'] else 'incomplete'
    record['navigation_boundaries']=summaries.get('api',{}).get('navigation_boundaries',[])
    payload=(json.dumps(record,indent=2,sort_keys=True)+'\n').encode();name='carddemo-slice-1-2026-10-18';(args.out/(name+'.json')).write_bytes(payload)
    lines=['# CardDemo slice 1 â€” unsigned receipt','',f"Status: {record['status']}. Acceptance complete: {record['acceptance_complete']}.",'',f"Source head: {record['source_head']}; tested commit: {record['tested_commit']}.",'','| Gate | Passed | Evidence |','|---|---|---|']
    for name,g in gates.items():lines.append('| '+name+' | '+str(g['passed'])+' | '+json.dumps({k:v for k,v in g.items() if k not in ('cases','results')})+' |')
    lines+=['','Remaining evidence gaps: '+', '.join(record['remaining_evidence_gaps']), '', 'Quirks:']+['- '+q for q in record['quirks']]+['','Out of scope:']+['- '+q for q in record['not_covered']]+['','Prepared as an unsigned Factory review request for Howard. No signature, import, activation or Phase 2 authority.','', 'JSON SHA-256: '+sha256(payload).hexdigest()]
    (args.out/'carddemo-slice-1-2026-10-18.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return 0 if record['acceptance_complete'] else 1
if __name__=='__main__':sys.exit(main())
