"""Refuse absent, duplicate, stale or incomplete shards before threshold assessment."""
import argparse
import json
from pathlib import Path
from lightyear_mainframe.campaign_provenance import read_sealed,current_binding
from lightyear_mainframe.target_retention import verify_retention,file_hash
from tools.check_equivalence_followup import population,finalize,targeted_accounting,targeted_outcome


def semantic_fresh(rows):
    def execution(row):
        return {k:row.get(k) for k in ('status','returncode','outputs','stdout_sha256','stderr_sha256')}
    return [{k:r.get(k) for k in ('id','status','killed_by')} | {
        'actual':execution(r.get('actual',{})), 'baseline':execution(r.get('baseline',{})),
        'comparisons':[dict(case=p.get('case'),status=p.get('status'),baseline=execution(p['baseline']),actual=execution(p['actual'])) for p in r.get('comparisons',[])],
        'evidence_gaps':bool(r.get('evidence_gaps'))}
        for r in rows]


def validate_shards(records, job, head, shards):
    if len(records)!=shards or {r['shard'] for r in records}!=set(range(shards)):
        raise ValueError('shards-missing-or-duplicate')
    expected=sorted(population(job));first=records[0];results=[]
    for row in records:
        if row['head']!=head or row['job']!=job or row['shards']!=shards or row['population']!=expected:
            raise ValueError('shard-binding-mismatch')
        selected=expected[row['shard']::shards]
        if row['selected']!=selected or sorted(r['id'] for r in row['results'])!=selected:
            raise ValueError('shard-partition-incomplete')
        if semantic_fresh(row['fresh'])!=semantic_fresh(first['fresh']) or row['diversity']!=first['diversity'] or row['current']['after_faults']!=first['current']['after_faults'] or row['census']!=first['census']:
            raise ValueError('fresh-shard-results-disagree')
        for result in row['results']:
            if 'targeted_cases' in result and result['targeted_cases']!=200:
                raise ValueError('shard-target-count-incomplete')
        results.extend(row['results'])
    return sorted(results,key=lambda r:r['id'])


def aggregate(folder,job,shards,output):
    head=current_binding()['head'];records=[]
    for path in sorted(Path(folder).glob('**/shard.json')):
        row=read_sealed(path)
        if row['job']!=job:continue
        root=path.parent;manifest=verify_retention(root/'execution-retention',head)
        if manifest['content_sha256']!=row['retention_manifest_sha256']:raise ValueError('shard-retention-mismatch')
        for name,expected in row['measurements'].items():
            target=(root/name).resolve()
            if not target.is_relative_to(root.resolve()) or file_hash(target)!=expected:raise ValueError('measurement-hash-mismatch')
            measured=json.loads(target.read_text());identifier=target.parent.name
            result=next(r for r in row['results'] if r['id']==identifier)
            if [r['index'] for r in measured]!=list(range(200)):raise ValueError('target-indices-incomplete')
            witnessed=False
            for case in measured:
                if targeted_outcome(case['baseline'],case['actual'])!=case['status']:raise ValueError('target-classifier-mismatch')
                reasons=[]
                if case['index'] in (0,199):reasons.append('fixed-sample')
                if case['status'].startswith('killed-') and not witnessed:reasons.append('first-killing-witness')
                if case['baseline']['status']!='executed' or case['actual']['status']!='executed':reasons.append('execution-refusal')
                witnessed=witnessed or case['status'].startswith('killed-')
                for key in ('baseline','actual'):
                    if sorted(case[key]['retention_reasons'])!=sorted(reasons) or case[key]['retained']!=bool(reasons):raise ValueError('retention-policy-mismatch')
                    for f in case[key]['files'].values():
                        if 'blob' in f and f['blob']!='cas/'+f['sha256']+'.gz':raise ValueError('blob-reference-mismatch')
                        if 'blob' in f and f['blob'] not in manifest['files']:raise ValueError('blob-missing')
            if any(result[k]!=v for k,v in targeted_accounting(measured).items()):raise ValueError('target-accounting-mismatch')
        expected_measurements={'targets/'+r['id']+'/results.json' for r in row['results'] if 'targeted_cases' in r}
        if set(row['measurements'])!=expected_measurements:raise ValueError('measurements-incomplete')
        records.append(row)
    results=validate_shards(records,job,head,shards)
    output=Path(output);output.mkdir(parents=True)
    first=records[0]
    finalize(output,job,head,results,{r['id']:r for r in first['fresh']},first['current'],first['diversity'],first['census'],records)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('job');p.add_argument('shards',type=int);p.add_argument('output',type=Path)
    a=p.parse_args();aggregate(a.folder,a.job,a.shards,a.output)
