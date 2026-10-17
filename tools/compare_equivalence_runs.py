"""Require identical classifications from two complete runs of one source head."""
import argparse,json
from pathlib import Path
from lightyear_mainframe.equivalence_automation import verify,digest,sealed


def compare(first,second):
    a=verify(first);b=verify(second)
    if (a['head'],a['program'])!=(b['head'],b['program']):raise ValueError('repeat-head-or-program-mismatch')
    def projection(ledger):
        rows=[{k:r.get(k) for k in ('id','mutant_sha256','status','route','basis','solver_disabled')} for r in ledger['rows']]
        if len({r['id'] for r in rows})!=len(rows):raise ValueError('repeat-duplicate-mutant')
        return sorted(rows,key=lambda r:r['id'])
    left,right=projection(a),projection(b)
    if left!=right:raise ValueError('non-reproducible-resolution-set')
    return sealed(dict(head=a['head'],program=a['program'],mutants=len(left),
                       compared='every mutant, including unresolved and unobservable',
                       identical_resolutions=True,resolutions_sha256=digest(left)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('first',type=Path);p.add_argument('second',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=compare(json.loads(a.first.read_text()),json.loads(a.second.read_text()))
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
