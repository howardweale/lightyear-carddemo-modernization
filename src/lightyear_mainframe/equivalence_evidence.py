"""Source-bound APPL-RESULT census and decision-dependent equivalence evidence."""
import hashlib
import json
import re
from pathlib import Path
from .scenario_coverage import code
from .systematic_mutation import TOKEN

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {'CBACT04C': '5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4',
           'CBTRN02C': '708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f'}


def seal(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def appl_result_census(text, program):
    """Token census of fixed-format code, excluding comments and literal contents.

    Only the exact declaration, two condition names and literal MOVE destinations
    are admitted. Any alias, group consumer, new raw read or SET fails closed.
    The source digest is also pinned: a changed program requires a fresh proof.
    """
    rows=[]; declarations=[]; conditions={}; active=False
    for number,raw in enumerate(text.splitlines(),1):
        line=code(raw).strip(); tokens=[m[0].upper() for m in TOKEN.finditer(line)]
        if not tokens: continue
        if tokens[:2]==['PROCEDURE','DIVISION']: active=True
        names={x for x in tokens if x in ('APPL-RESULT','APPL-AOK','APPL-EOF')}
        if not names: continue
        if not active:
            if tokens[:2]==['01','APPL-RESULT'] and 'REDEFINES' not in tokens:
                declarations.append(number); kind='declaration'
            elif tokens[:2] in (['88','APPL-AOK'],['88','APPL-EOF']) and tokens[2:3]==['VALUE']:
                value=int(tokens[3]); conditions[tokens[1]]=value; kind='condition-declaration'
            else: raise ValueError('APPL-RESULT-unsupported-declaration:'+str(number))
        elif 'APPL-RESULT' in names:
            clean=tokens[:-1] if tokens[-1:]==['.'] else tokens
            if len(clean)!=4 or clean[0]!='MOVE' or not clean[1].isdigit() or clean[2:]!=['TO','APPL-RESULT']:
                raise ValueError('APPL-RESULT-new-consumer:'+str(number))
            kind='literal-destination'
        else:
            if tokens[0] not in ('IF','AND','OR','UNTIL','PERFORM'):
                raise ValueError('APPL-RESULT-condition-consumer:'+str(number))
            kind='condition-read'
        rows.append(dict(line=number,tokens=tokens,kind=kind))
    if len(declarations)!=1 or conditions!={'APPL-AOK':0,'APPL-EOF':16}:
        raise ValueError('APPL-RESULT-condition-domain')
    source=hashlib.sha256(text.encode()).hexdigest()
    if source!=SOURCES.get(program): raise ValueError('APPL-RESULT-source-changed-needs-review')
    result=dict(schema='appl-result-reference-census/1',program=program,source_sha256=source,
                condition_values=conditions,references=rows,raw_consumers=[],passed=True)
    return {**result,'content_sha256':seal(result)}


def class_covered(mutant, argument, census):
    if not argument or not census.get('passed'): return False
    if mutant.get('source_path') or mutant['source_sha256']!=census['source_sha256']: return False
    if mutant['operator'] not in ('constant','delete-MOVE'): return False
    old=code(mutant['original']).strip().rstrip('.').split()
    if len(old)!=4 or old[0]!='MOVE' or old[2:]!=['TO','APPL-RESULT']: return False
    # The census establishes the only observers, but not overwrite/control flow.
    # Keep the individual source-bound argument for deletions/overwritten stores.
    if mutant['operator']=='constant':
        new=code(mutant['replacement']).strip().rstrip('.').split()
        if len(new)!=4 or new[2:]!=['TO','APPL-RESULT']: return False
        if int(old[1]) in (0,16) or int(new[1]) in (0,16): return False
    return argument.get('source_sha256')==census['source_sha256']


def register_dependencies(argument, register=None):
    register=register or json.loads((ROOT/'docs/factory/keep-or-fix-register.json').read_text())
    identifier=argument.get('mutant_id',argument.get('id'))
    needed=[]
    # Both description stores are unconsumed only while the posting-time109 gap remains.
    if identifier in ('CBTRN02C-delete-MOVE-557-314','CBTRN02C-delete-MOVE-209-47'): needed=['REWRITE-109']
    text=argument.get('argument','')
    if 'outer EOF ELSE' in text or 'unreachable' in text and identifier and identifier.startswith('CBACT04C'):
        needed.append('CBACT04C-FINAL-ACCOUNT-EOF-ELSE')
    rows={r['id']:r for r in register['defects']}; result=[]
    for key in sorted(set(needed)):
        entry=rows[key]
        if entry.get('fix_authorized') or entry.get('disposition') not in ('keep','keep-by-default'):
            raise ValueError('equivalence-register-decision-changed:'+key)
        result.append(dict(id=key,entry_sha256=seal(entry),required_disposition=entry['disposition']))
    return result


def validate_dependencies(argument, register):
    current={r['id']:r for r in register['defects']}
    for row in argument.get('depends_on_register',[]):
        entry=current.get(row['id'])
        if not entry or seal(entry)!=row['entry_sha256'] or entry.get('fix_authorized'):
            raise ValueError('equivalence-register-decision-changed:'+row['id'])
    return True


def mutation_threshold_report(fresh, followup, accepted, scope, register):
    """Amended threshold/2 exclusions; arguments alone never authorize exclusion."""
    if scope not in ('twin','zos-facing'):raise ValueError('claim-scope')
    approvals={r['id']:r for r in accepted};reviews={r['id']:r for r in followup}
    killed=[];excluded=[];refused=[];unresolved=[]
    for current in fresh:
        identifier=current['id'];row=reviews.get(identifier,{})
        if current['status'].startswith('killed-') or row.get('refuted'):
            killed.append(identifier);continue
        if current['status']=='not-compiled':refused.append(identifier);continue
        a=row.get('argument',{});validate_dependencies(a,register)
        host_only=(identifier=='CBTRN02C-delete-MOVE-718-447' or bool(a.get('compiler_storage_semantics') or a.get('compiler_runtime_contract'))
            or 'not z/OS' in a.get('argument','') or 'not native z/OS' in a.get('argument','')
            or 'host CEE3ABD terminating shim' in a.get('argument',''))
        approval=approvals.get(identifier)
        individual=bool(approval and approval['source_sha256']==row.get('mutant',{}).get('source_sha256')
                        and not (scope=='zos-facing' and approval['scope']=='host-compiler-scoped'))
        if individual and approval.get('explicit_zos_scope_basis') and identifier in ('CBACT04C-receiving-size-133-19','CBTRN02C-constant-718-445'):
            host_only=False
        basis='compiler-proven' if scope=='twin' and row.get('TCE',{}).get('identical') else 'APPL-RESULT-class-proof' if row.get('class_covered') else 'individually-accepted' if individual else None
        if basis and not(scope=='zos-facing' and host_only):excluded.append(dict(id=identifier,basis=basis))
        else:unresolved.append(dict(id=identifier,reason='host-compiler-scoped argument unresolved for z/OS' if host_only and scope=='zos-facing' else 'individual operator review required'))
    eligible=len(fresh)-len(excluded)-len(refused)
    return dict(schema='scenario-threshold-2-mutation-assessment/1',claim_scope=scope,sites=len(fresh),killed=len(killed),
        compiler_refusals=refused,excluded_equivalents=excluded,eligible=eligible,kill_rate=f'{len(killed)}/{eligible}',
        minimum_50_met=eligible>=50,at_least_90_percent=eligible>0 and len(killed)*10>=eligible*9,
        unresolved_survivors=unresolved,mutation_conditions_met=eligible>=50 and len(killed)*10>=eligible*9 and not unresolved,
        whole_threshold_effective=False,other_requirements=['fresh business/I-O coverage bindings','two values per compared output field','complete B1 review dispositions'],
        release_authorized=False)


def amended_threshold_report(mutation, coverage, diversity, compared_fields, current_head):
    """Assess every October11 amended condition, without authorizing release."""
    from lightyear_factory.scenario_policy import IO_ACCEPTANCES
    reasons=[]; program=coverage.get('program'); source=coverage.get('source_sha256')
    if source!=SOURCES.get(program) or not re.fullmatch(r'[0-9a-f]{40}',current_head):
        reasons.append('fresh-current-head-source-binding-required')
    if not coverage.get('instrumented'):reasons.append('instrumented-coverage-required')
    business=coverage.get('coverage_by_class',{}).get('business-logic',{})
    if type(business.get('total'))!=int or business['total']<=0 or business.get('covered')!=business['total']:
        reasons.append('business-outcomes-below-100-percent')
    accepted={(r['id'],r['outcome']) for r in IO_ACCEPTANCES if r['program']==program and r['source_sha256']==source}
    gaps=[r for r in coverage.get('uncovered',[]) if r.get('classification')!='io-handling' or (r.get('id'),r.get('outcome')) not in accepted]
    if gaps:reasons.append('unaccepted-business-or-IO-outcome')
    fields=sorted(set(compared_fields));missing=[f for f in fields if type(diversity.get(f))!=int or diversity[f]<2]
    if not fields:reasons.append('compared-field-inventory-required')
    if missing:reasons.append('output-fields-below-two-values')
    if not mutation['mutation_conditions_met']:reasons.append('mutation-or-individual-review-conditions-unmet')
    result=dict(schema='scenario-threshold/2-amended-assessment',decision_date='2026-10-11T14:00:00-07:00',
        status='approved-subject-to-B1-completion',current_head=current_head,program=program,source_sha256=source,
        claim_scope=mutation['claim_scope'],mutation=mutation,business=business,
        io=coverage.get('coverage_by_class',{}).get('io-handling'),unaccepted_outcomes=gaps,
        accepted_uncovered_IO=[r for r in coverage.get('uncovered',[]) if (r.get('id'),r.get('outcome')) in accepted],
        distinct_values_per_output_field=diversity,compared_fields=fields,below_two_values=missing,
        conditions_met=not reasons,blocking_reasons=reasons,release_authorized=False,
        qualification_credit=False,measurement_credit=False)
    return {**result,'content_sha256':seal(result)}
