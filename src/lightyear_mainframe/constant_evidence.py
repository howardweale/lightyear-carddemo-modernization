"""Build constant-field evidence from observed campaign comparisons and bound sites."""
from hashlib import sha256
import json
from pathlib import Path
from lightyear_factory.threshold3 import ACCEPTANCE, BINDINGS, SEAL
from .equivalence_evidence import seal
from .loader_domain import executed
from .systematic_mutation import outcome


def build(root, program, results, inventory, compared_fields):
    if program != 'CBACT04C':
        return {}
    record = json.loads((Path(root)/ACCEPTANCE).read_bytes())
    if record.get('content_sha256') != SEAL or seal({k:v for k,v in record.items() if k != 'content_sha256'}) != SEAL:
        raise ValueError('constant-evidence-acceptance-binding')
    sites = {r['id']:r for r in inventory}
    evidence = {}
    for approved in record['constant_field_acceptances']:
        if approved['program'] != 'INTCALC':
            continue
        binding = {k:approved[k] for k in BINDINGS}
        mutants = []
        for row in results:
            site = sites.get(row['id'], {})
            if site.get('source_path') or site.get('line') != binding['source_line'] or site.get('source_sha256') != binding['source_sha256']:
                continue
            pairs = row.get('comparisons', row.get('valid_domain_comparisons', []))
            if not pairs and row.get('baseline') and row.get('actual'):
                pairs = [dict(baseline=row['baseline'],actual=row['actual'])]
            valid = [p for p in pairs if executed(p.get('baseline',{})) and executed(p.get('actual',{}))]
            mutants.append(dict(id=row['id'],line=site['line'],source_sha256=site['source_sha256'],
                status=row['status'],valid_comparisons=len(valid),
                evidence_complete=bool(pairs) and len(valid)==len(pairs) and not row.get('evidence_gaps'),
                record_sha256=seal(row),caught_comparison=any(outcome(p['baseline'],p['actual'])==row['status'] and row['status'].startswith('killed-') for p in valid)))
        qualified=[m for m in mutants if m['evidence_complete'] and m['valid_comparisons']>0
                   and (not m['status'].startswith('killed-') or m['caught_comparison'])
                   and m['status'] in ('killed-failure','killed-divergent','survived','equivalent (argued, listed)')]
        evidence[binding['field']] = dict(binding,compared=binding['field'] in compared_fields,
            mutants=qualified,unqualified_mutants=[m for m in mutants if m not in qualified])
    return evidence
