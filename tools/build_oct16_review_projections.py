"""CI-only analysis of retained October 15 receipts; never runs an application."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
HEAD='f343925026bee705ed3c16a734dc5bae4b24c588'
REPO='howardweale/lightyear-carddemo-modernization'


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')


# Original Actions bytes; this archive changes storage only, never measurement.
POSTTRAN_ARCHIVE_URL = 'https://github.com/howardweale/lightyear-carddemo-modernization/releases/download/artifact-preservation-11991139660/11991139660-original.zip'
POSTTRAN_PROVENANCE_URL = 'https://raw.githubusercontent.com/howardweale/lightyear-carddemo-modernization/23263e056585e1314a85be5b3d8e933901f466f9/docs/evidence/artifact-preservation-11991139660-2026-10-29/preservation-provenance.json'
POSTTRAN_PROVENANCE_SHA256 = '615fbae8bf06c797d413cc26dba9cbde2e5c7bf4990d7f1748ff91939a723e93'


def _verify_preserved_posttran(raw, provenance_raw):
    if sha256(provenance_raw).hexdigest() != POSTTRAN_PROVENANCE_SHA256:
        raise ValueError('POSTTRAN-archived-provenance')
    provenance = json.loads(provenance_raw)
    artifact = provenance['original_artifact']
    if (provenance['schema'] != 'github-actions-artifact-preservation/1'
            or artifact['id'] != 11991139660
            or artifact['name'] != 'factory-review-records-POSTTRAN-0'
            or artifact['workflow_run']['id'] != 38763552148
            or artifact['workflow_run']['head_sha'] != HEAD
            or provenance['release']['download_url'] != POSTTRAN_ARCHIVE_URL
            or provenance['preservation_only'] is not True
            or provenance['execution_authorized'] is not False):
        raise ValueError('POSTTRAN-archived-provenance')
    if len(raw) != artifact['size_in_bytes'] or len(raw) != 2175361:
        raise ValueError('POSTTRAN-original-archive-size')
    if sha256(raw).hexdigest() != '24ea12fe7a16fea5bb06999e6a409e36cfc3fba59646701ebfd453ed3eff343c':
        raise ValueError('POSTTRAN-original-archive-hash')
    return raw


def _preserved_posttran_bytes():
    try:
        with urllib.request.urlopen(POSTTRAN_PROVENANCE_URL, timeout=120) as response:
            provenance = response.read()
        with urllib.request.urlopen(POSTTRAN_ARCHIVE_URL, timeout=120) as response:
            raw = response.read()
    except OSError as error:
        raise ValueError('POSTTRAN-preserved-copy-unavailable') from error
    return _verify_preserved_posttran(raw, provenance)


def sources():
    url=f'https://github.com/{REPO}/releases/download/evidence-2026-10-15-intcalc/factory-review-records-INTCALC-0-mutation-results.json'
    with urllib.request.urlopen(url,timeout=120) as response: raw=response.read()
    if sha256(raw).hexdigest()!='ad4ab419496debd0a8d62beaf9ff7a265fd21832521277bbcd8462ae2b7bbfba': raise ValueError('INTCALC-original-receipt-hash')
    intcalc=json.loads(raw)
    raw=_preserved_posttran_bytes()
    if sha256(raw).hexdigest()!='24ea12fe7a16fea5bb06999e6a409e36cfc3fba59646701ebfd453ed3eff343c': raise ValueError('POSTTRAN-original-archive-hash')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        posttran=json.loads(archive.read('factory-review-POSTTRAN/mutation-results.json'))
    return {'INTCALC':intcalc,'POSTTRAN':posttran}


def verdict(report):
    twin=report['projected_thresholds']['twin']
    parts=[f"{len(twin['unresolved_survivors'])} unresolved twin mutants",
           f"{len(report.get('evidence_gaps', []))} raw campaign gaps"]
    if report['program']=='INTCALC':
        parts += [f"{len(report['below_two_values'])} fields below two values; verify threshold/3 constant evidence",
                  f"{len(report['pending_effective_acceptances'])} pending effective individual acceptances"]
    parts += [f"business {report['business']['fraction']}; I/O {report['io']['fraction']}"]
    if not report['effective']:parts.append('effective policy not recorded')
    if not report['release_authorized']:parts.append('release authority absent')
    return 'Not releasable: '+ '; '.join(parts)+'. No new z/OS acceptances.'


def build(output, prepared_on='2026-10-17'):
    if os.environ.get('GITHUB_ACTIONS')!='true': raise ValueError('CI-only-review-projection')
    from lightyear_mainframe.equivalence_evidence import mutation_threshold_report,seal
    from lightyear_mainframe.release_projection import review_projection,supplemental_acceptances
    from lightyear_mainframe.loader_domain import project,verify_seal
    output=Path(output); fresh=sources()
    folder=ROOT/'docs/factory/release-evidence-2026-10-15'
    index=json.loads((folder/'index.json').read_bytes())
    if index['head']!=HEAD or index['conclusion']!='success': raise ValueError('measured-head')
    for archive in index['sources']:
        for name,expected in archive['files'].items():
            if sha256((ROOT/name).read_bytes()).hexdigest()!=expected: raise ValueError('indexed-evidence-changed:'+name)
    read=lambda name:json.loads((ROOT/name).read_bytes())
    accepted=read('docs/factory/equivalence-decision-binding-2026-10-11.json')['accepted_mutants']
    register=read('docs/factory/keep-or-fix-register.json')
    reports={}
    for program in fresh:
        reviews=json.loads((folder/f'aggregate/{program}/results.json').read_bytes())
        report=review_projection(fresh[program],reviews,accepted,program,register)
        report.update(prepared_on=prepared_on,measurement_head=HEAD,measurement_run=38763552148,
            analysis_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
        if program=='INTCALC':
            overlay=verify_seal(json.loads((folder/'intcalc-0/factory-review-INTCALC/loader-domain-overlay.json').read_bytes()))
            overlaid=project(fresh[program],overlay)
            supplemented,pending,_=supplemental_acceptances(reviews,accepted,program,register)
            report['projected_thresholds']['twin']=mutation_threshold_report(overlaid,reviews,supplemented,'twin',register)
            hypothetical=mutation_threshold_report(overlaid,reviews,accepted,'zos-facing',register)
            report['hypothetical_zos_after_confirmation']=hypothetical
            groups=defaultdict(list)
            for item in hypothetical['excluded_equivalents']: groups[item['basis']].append(item['id'])
            report['hypothetical_zos_exclusions_by_basis']=dict(groups)
            report['zos_loader_blocked_ids']=sorted(r['id'] for r in fresh[program] if r['status']=='evidence-gap')
            report['scope_explanation']=f"The loader overlay is twin-scoped. Without signed and confirmed z/OS loader-domain evidence, all {len(report['zos_loader_blocked_ids'])} raw gaps remain and no z/OS-facing exclusion is applied."
            report['pending_effective_acceptances']=pending
            proposal=read('docs/factory/intcalc-duplicate-category-proposal-2026-10-12.json')
            new=dict(schema='factory-scoped-domain-decision-proposal/2',prepared_on=prepared_on,program='INTCALC',
                claim_scope='zos-facing',scenario_id=proposal['scenario_id'],bound_sources=proposal['bound_sources'],
                original_proposal_sha256=proposal['content_sha256'],approved=False,effective=False,needs_zos_confirmation=True,
                argument='Duplicate primary KSDS keys are outside the valid data domain. Confirm the actual IDCAMS REPRO loader rejection before applying this argument on z/OS.',
                required_capture=['Exact input hashes and duplicate keys','IDCAMS command, SYSIN and complete SYSPRINT','Loader return code and dataset definition','Proof that CBACT04C did not start','Ordinary valid-domain control load'],
                no_kill_or_comparison_credit=True,blocked_ids=report['zos_loader_blocked_ids'])
            new['content_sha256']=seal(new); save(output/f'intcalc-zos-loader-domain-proposal-{prepared_on}.json',new)
            # Capture-kit addendum: explicitly a loader negative test, not an IMS/application comparison.
            save(output/f'capture-kit-intcalc-duplicate-category-{prepared_on}.json',dict(schema='zos-loader-capture-case/1',
                scenario_id=new['scenario_id'],proposal_sha256=new['content_sha256'],bound_sources=new['bound_sources'],
                expected_application_execution=False,required_capture=new['required_capture'],execute_authorized=False))
        else:
            gaps=[]
            for row in fresh[program]:
                if row['status']!='evidence-gap': continue
                failures=row['evidence_gaps']; errors=Counter(g['actual']['error_type'] for g in failures)
                if row['line'] in (94,96):
                    reason='TCATBALF dump helper refused with rc66 after the application; changed receiving scale is not the INTCALC duplicate-key loader case.'
                    remedy='Preserve the mutant indexed bytes; add a bounded raw-record dumper that records invalid numeric representation rather than refusing before comparison. Fresh exact-head CI evidence is required.'
                elif row['line']==230:
                    reason='Mutated return code 3 or 5 was rejected by the harness before a complete comparison receipt.'
                    remedy='Record every completed process return code and all complete after-images, then compare the codes. Do not broaden the candidate allowed-code contract or credit these old refusals as kills.'
                else:
                    reason='The four-second application timeout fired; the mutated control flow removes read/EOF/abend progress.'
                    remedy='Keep as a gap. A bounded progress or termination witness and an explicitly reviewed timeout classification are required; raising the timeout or treating a refusal as a kill is not justified.'
                gaps.append(dict(id=row['id'],line=row['line'],raw_record_sha256=seal(row),cases=[g['case'] for g in failures],
                    failure_types=dict(errors),cause=reason,minimal_next_step=remedy))
            report['evidence_gaps']=gaps
        measured=json.loads((folder/f'aggregate/{program}/threshold-2-by-scope.json').read_bytes())['twin']
        report.update(business=measured['business'],io=measured['io'],below_two_values=measured['below_two_values'])
        report['verdict']=verdict(report)
        report.update(authorized_by='Howard',performed_by='Codex',supersedes=f'{program.lower()}-review-verdict-2026-10-16.json')
        report['content_sha256']=seal(report); reports[program]=report
        save(output/f'{program.lower()}-review-verdict-{prepared_on}.json',report)
        lines=[f'# {program} review verdict — {prepared_on}','',report['verdict'],'',
            f'Measured head `{HEAD}`, run 38763552148. This is a new analysis of retained evidence, not a new campaign.','',
            '| Scope | Before supplement | Projected | Unresolved |','| --- | --- | --- | --- |']
        for scope,value in report['projected_thresholds'].items():
            lines.append(f"| {scope} | {report['raw_thresholds'][scope]['kill_rate']} | {value['kill_rate']} | {len(value['unresolved_survivors'])} |")
        lines+=['',f"Diversity: {len(report['below_two_values'])} fields below two values.",'']
        lines+=['- '+name for name in report['below_two_values']]
        if program=='INTCALC':
            lines+=['',report['scope_explanation'],'',f"Hypothetical z/OS rate after confirmation and signing: {hypothetical['kill_rate']}. Not applied.",'',
                f"All {len(report['zos_loader_blocked_ids'])} blocked IDs and the hypothetical exclusions by explicit basis are in the JSON."]
        else:
            for row in report['evidence_gaps']:
                lines+=['',f"## {row['id']}",'',row['cause'],'',row['minimal_next_step'],'','Scenarios: '+', '.join(row['cases'])]
        (output/f'{program.lower()}-review-verdict-{prepared_on}.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    # Source argument, with the same exact line and hash rules as INTCALC's request.
    argument=next(g for g in read('docs/factory/io-gap-arguments.json')['gaps'] if g['program']=='CBTRN02C')
    source=(ROOT/'spec/mainframe/public-source/CBTRN02C.cbl').read_bytes().replace(b'\r\n',b'\n')
    if sha256(source).hexdigest()!=argument['source_sha256']: raise ValueError('POSTTRAN-IO-source')
    lines=source.decode().splitlines()
    if any(lines[r['line']-1].strip()!=r['source'] for r in argument['supporting_source']): raise ValueError('POSTTRAN-IO-lines')
    path='docs/factory/io-gap-arguments.json'
    save(output/f'posttran-io-exception-request-{prepared_on}.json',dict(schema='factory-contract/1',kind='io-exception-acceptance',program='POSTTRAN',
        sources=[dict(path=path,sha256=sha256((ROOT/path).read_bytes()).hexdigest(),commit=reports['POSTTRAN']['analysis_head'])],
        details=dict(source_sha256=argument['source_sha256'],outcome_id=argument['outcome_id'],outcome='false',line=203,basis='structurally-unreachable',argument_sha256=seal(argument))))
    return reports


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');a=p.parse_args();build(a.output)
