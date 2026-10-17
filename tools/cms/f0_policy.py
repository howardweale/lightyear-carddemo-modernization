"""F0 completeness and publication boundary; no CMS workloads or key access."""
from hashlib import sha256
import json
from pathlib import Path
import re


def diagnostic_hash(text):
    # Only the task-local prefix differs between runners. Preserve all diagnostic
    # text, codes and line numbers in the binding; publish the hash, never text.
    normalized=re.sub(r"[^\s'\"]*/work/cms/f0/",'<F0>/',text.replace('\\','/'))
    return sha256(normalized.encode('utf-8')).hexdigest()


def diagnostic_metadata(text, source_lines=()):
    normalized=[' '.join(line.split()) for line in text.splitlines()]
    active={' '.join(line.split()) for line in source_lines if len(line.strip())>=12}
    quoted=any(re.match(r'^\s*\d+\s*[|>]',line) for line in text.splitlines())
    quoted=quoted or any(source in diagnostic for source in active for diagnostic in normalized)
    return dict(sha256=sha256(text.encode('utf-8')).hexdigest(),
        normalized_sha256=diagnostic_hash(text),bytes=len(text.encode('utf-8')),
        possible_source_quote=bool(quoted),raw_diagnostics_uploaded=False)


def compile_outcome(rows, expected, inventory=None):
    last={}
    for row in rows:last[(row['package'],row['program'])]=row
    expected_by_key={(e['package'],e['program']):e for e in expected}
    if len(expected_by_key)!=len(expected):raise ValueError('duplicate expected compile limitation')
    unexpected=[];known=[]
    for key,row in last.items():
        if row['returncode']==0:continue
        binding=dict(package=row['package'],program=row['program'],source_sha256=row['source_sha256'],
            dialect=row['dialect'],returncode=row['returncode'],diagnostic_sha256=row['diagnostic_metadata']['normalized_sha256'])
        item=expected_by_key.get(key)
        if item and all(item.get(k)==v for k,v in binding.items()):known.append(dict(**binding,reason=item['reason']))
        else:unexpected.append(binding)
    observed={(r['package'],r['program'],r['source_sha256']) for r in last.values()}
    inventory_matched=inventory is None or observed=={(r['package'],r['program'],r['source_sha256']) for r in inventory}
    if not inventory_matched:unexpected.append({'reason':'pinned-program-inventory-mismatch'})
    return dict(programs=len(last),compiled=sum(r['returncode']==0 for r in last.values()),inventory_matched=inventory_matched,
        expected_limitations=known,unexpected_failures=unexpected,
        complete=bool(last) and not unexpected,all_programs_compiled=bool(last) and all(r['returncode']==0 for r in last.values()))


def require_smoke(record):
    if record.get('complete') is not True:raise SystemExit('cms-f0-smoke-incomplete')


def require_compile(outcome):
    if outcome.get('complete') is not True:raise SystemExit('cms-f0-compile-unexpected-incompleteness')


def require_java(result, claims_required):
    claims=result.get('claims',[])
    complete=(not result.get('error') and result.get('owned_process_stopped') is True
        and bool(result.get('paths')) and (not claims_required or (len(claims)==5 and all(c.get('http_status')==200 for c in claims))))
    result['complete']=complete
    return complete


def publish(root):
    """Explicit allowlist: raw compiler logs, source, rate bytes and prices excluded."""
    root=Path(root);out=root/'public';out.mkdir(parents=True,exist_ok=True)
    result={'schema':'cms-f0-public-receipt/1','notice':'Public CMS software, independently tested',
        'raw_diagnostics_uploaded':False,'pricing_outputs_uploaded':False,'source_uploaded':False,
        'comparison_verdict':'not supplied','release_authorized':False}
    for name in ('compile-results.json','smoke-hashes.json'):
        path=root/name
        if not path.exists():continue
        raw=path.read_bytes();value=json.loads(raw)
        result.setdefault('private_receipt_hashes',{})[name]=sha256(raw).hexdigest()
        if name=='compile-results.json':
            outcome=value.get('outcome',{})
            result['compile']={k:outcome[k] for k in ('programs','compiled','complete','all_programs_compiled','inventory_matched') if k in outcome}
            result['compile'].setdefault('complete',False)
            for group in ('expected_limitations','unexpected_failures'):
                result['compile'][group]=[{k:r[k] for k in ('package','program','source_sha256','dialect','returncode','diagnostic_sha256') if k in r} for r in outcome.get(group,[])]
            result['compile']['attempts']=len(value['results'])
            result['compile']['diagnostic_audit']=[dict(program=r['program'],dialect=r['dialect'],**{k:r['diagnostic_metadata'][k] for k in ('sha256','normalized_sha256','bytes','possible_source_quote','raw_diagnostics_uploaded')}) for r in value['results']]
        else:
            result['smoke']={k:value[k] for k in ('complete','source_modified','source_sha256','hold_copy_sha256','claims_sha256','driver_sha256','module_layout_sha256','table_adapters','build_returncode','run_returncode','stdout_sha256','stderr_sha256') if k in value}
            result['smoke'].update(cases=len(value.get('cases',[])),fields_per_case=len(value.get('fields',[])),input_checks=sum(c.get('input_checks',0) for c in value.get('cases',[])))
    result['complete']=result.get('compile',{}).get('complete') is True and result.get('smoke',{}).get('complete') is True
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('work/cms/f0'));a=p.parse_args();publish(a.root)
