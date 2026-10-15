"""Rebuild/re-solve every automated equivalence on the same source head in CI."""
import argparse
import json
import os
from pathlib import Path
from lightyear_mainframe.equivalence_automation import verify,digest,PROGRAMS,load_ir
from lightyear_mainframe.equivalence_compiler import require_ci,compile_object,toolchain
from lightyear_mainframe.equivalence_solver import recheck,pair,validate_pair
from lightyear_mainframe.legacy_twin import ROOT,build
from lightyear_mainframe.systematic_mutation import outcome
from tools.run_equivalence_automation import write
from tools.check_factory_review import attempt


def check(source,output):
    require_ci(); output.mkdir(parents=True,exist_ok=False)
    manifest=verify(json.loads((source/'manifest.json').read_text()))
    if manifest['head']!=os.environ['EQUIVALENCE_HEAD']:raise ValueError('recheck-head-mismatch')
    for name,expected in manifest['files'].items():
        path=(source/name).resolve()
        if not path.is_relative_to(source.resolve()) or digest(path.read_bytes())!=expected:raise ValueError('recheck-artifact-mismatch:'+name)
    ledger=verify(json.loads((source/'resolutions.json').read_text()));job=ledger['program']
    baseline=verify(json.loads((source/'triage.json').read_text()));triaged={r['id']:r for r in baseline['rows']}
    for path,sha in baseline['sources'].items():
        if digest((ROOT/path).read_text().encode())!=sha:raise ValueError('source-binding')
    chain=toolchain()
    if chain!=json.loads((source/'toolchain.json').read_text()):raise ValueError('toolchain-changed')
    original=compile_object(ROOT,output/'original',PROGRAMS[job]);text,ir=load_ir(ROOT,PROGRAMS[job]);checked=[]
    for row in ledger['rows']:
        if row['status'] not in ('equivalent','killed'):continue
        mid=row['id'];mutant=triaged[mid]['mutant'];folder=output/mid;folder.mkdir()
        if row['mutant_sha256']!=digest(mutant):raise ValueError('mutant-binding')
        if row['status']=='killed':
            proof=verify(json.loads((source/row['evidence'][0]['path']).read_text()))
            build(folder/'original',jobs=[job]);build(folder/'mutant',systematic=mutant,jobs=[job])
            a=attempt(folder/'original',proof['scenario'],folder/'original-run');b=attempt(folder/'mutant',proof['scenario'],folder/'mutant-run')
            if not outcome(a,b).startswith('killed-'):raise ValueError('killing-test-not-reproduced')
        elif row['route']=='S1':
            actual=compile_object(ROOT,folder/'compiler',PROGRAMS[job],mutant)
            if actual['object_sha256']!=original['object_sha256']:raise ValueError('object-identity-not-reproduced')
        elif row['route']=='S3':
            local=pair(text,mutant,ir)
            proof=verify(json.loads((source/'mutants'/mid/'solver/solver.json').read_text()))
            if proof['pair_sha256']!=digest(local):raise ValueError('solver-pair-binding')
            validation=validate_pair(local,folder/'validation',**{k:chain['binary_profile'][k] for k in ('binary_truncate','byteorder')})
            if not validation['enabled']:raise ValueError('encoder-no-longer-valid')
            if recheck(source/'mutants'/mid/'solver')!='unsat':raise ValueError('solver-proof-not-reproduced')
        else:raise ValueError('unsupported-resolution-route')
        checked.append(dict(id=mid,status=row['status'],route=row['route']))
    result=dict(head=ledger['head'],program=job,checked=checked,identical_resolutions=True,
                manifest_sha256=manifest['content_sha256'],model_calls=0)
    write(output/'recheck.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();print(json.dumps(check(a.source,a.output),indent=2))
