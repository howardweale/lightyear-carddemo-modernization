"""Interpret a retained work-order receipt without hiding its evidence gaps."""
from hashlib import sha256
import json
from pathlib import Path
import re


def latest(root):
    paths=sorted(p for p in (Path(root)/'docs/modernization').glob('carddemo-slice-gaps-*.json')
                 if re.fullmatch(r'carddemo-slice-gaps-\d{4}-\d{2}-\d{2}\.json',p.name))
    return paths[-1] if paths else None


def project(root, receipt_path, receipt):
    root=Path(root);path=latest(root)
    if path is None:
        return dict(acceptance_scope='historical work-order proof only; gap addendum unavailable',
                    remaining_evidence_gaps=['Evidence-gap addendum unavailable; no completeness claim.'])
    value=json.loads(path.read_bytes())
    expected=dict(path=receipt_path,sha256=sha256((root/receipt_path).read_bytes()).hexdigest())
    if value.get('schema')!='carddemo-slice-gap-addendum/1' or value.get('receipt')!=expected:
        raise ValueError('carddemo-gap-receipt-binding')
    gaps=value['remaining_evidence_gaps']
    if not isinstance(gaps,list) or len({g['id'] for g in gaps})!=len(gaps):
        raise ValueError('carddemo-gap-identities')
    descriptions=[]
    for gap in gaps:
        if not gap['description'].strip():raise ValueError('carddemo-gap-empty-description')
        text=gap['description']
        statuses=gap.get('mutation_statuses',[])
        if statuses:
            counts=receipt['gates']['mutation']['status_counts']
            text+=' '+', '.join(str(counts[s])+' '+s for s in statuses)+'.'
        descriptions.append(text)
    return dict(acceptance_scope=value['acceptance_meaning'],
                work_order_acceptance_complete=all(g['passed'] for g in receipt['gates'].values()),
                work_order_acceptance_items={k:g['passed'] for k,g in receipt['gates'].items()},
                remaining_evidence_gaps=descriptions,gap_addendum=path.relative_to(root).as_posix())


def paragraph(value):
    gaps=value['remaining_evidence_gaps']
    return ('Acceptance scope: '+value['acceptance_scope']+' Open evidence gaps: '
            +(' '.join(gaps) if gaps else 'None listed in the addendum; this does not expand claim scope.')
            +(' [Dated gap addendum](../modernization/'+Path(value['gap_addendum']).with_suffix('.md').name+').' if value.get('gap_addendum') else ''))


def markdown(value):
    items=value['work_order_acceptance_items']
    return ('# CardDemo slice evidence-gap addendum\n\n'+paragraph(value)+'\n\n'
            +'| Work-order item | Passed in the bound receipt |\n| --- | --- |\n'
            +''.join('| '+name+' | '+str(passed).lower()+' |\n' for name,passed in items.items())
            +'\nThe original receipt and all retained archives remain unchanged. No signing, import, activation, Phase 2 or release authority.\n')
