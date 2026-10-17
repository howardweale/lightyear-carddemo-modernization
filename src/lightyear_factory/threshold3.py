"""Seven exact source constants may waive diversity, never comparison or mutation."""
from hashlib import sha256
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE = 'docs/factory/equivalence-operator-acceptance-2026-10-12.json'
SEAL = '822af989952301a165f468c38183871d644b2e0e1f8321ba1cb8a4daea13bfd9'
BINDINGS = ('field','source_path','source_sha256','source_line','source_line_sha256')


def exemptions(adequacy, threshold, compared_fields, root=None):
    from lightyear_control_tower.decisions import digest
    from .scenario_policy import PROPOSAL
    if any(threshold.get(k)!=PROPOSAL[k] for k in ('business_logic_outcomes','legacy_mutants_killed','minimum_systematic_mutants','distinct_values_per_output_field')):
        raise ValueError('threshold3-only-constant-exemptions')
    root=Path(root or ROOT)
    record=json.loads((root/ACCEPTANCE).read_bytes())
    if record.get('content_sha256') != SEAL or digest({k:v for k,v in record.items() if k!='content_sha256'}) != SEAL:
        raise ValueError('threshold3-constant-inventory')
    approved=[r for r in record['constant_field_acceptances'] if r['program']=='INTCALC']
    expected={r['field']:{k:r[k] for k in BINDINGS} for r in approved}
    rows=threshold.get('constant_exemptions',[])
    if len(expected)!=7 or len(rows)!=7 or len({r['field'] for r in rows})!=7:
        raise ValueError('threshold3-constant-inventory')
    if adequacy.get('program')!='CBACT04C': raise ValueError('threshold3-program')
    evidence=adequacy.get('constant_field_evidence',{})
    for row in rows:
        name=row['field']
        binding={k:row[k] for k in BINDINGS}
        if expected.get(name)!=binding: raise ValueError('threshold3-source-binding')
        source=(root/row['source_path']).read_bytes().replace(b'\r\n',b'\n')
        line=source.decode().splitlines()[row['source_line']-1]
        if sha256(source).hexdigest()!=row['source_sha256'] or sha256(line.encode()).hexdigest()!=row['source_line_sha256']:
            raise ValueError('threshold3-source-binding')
        proof=evidence.get(name,{})
        if ({k:proof.get(k) for k in BINDINGS}!=binding or proof.get('compared') is not True
            or name not in compared_fields or adequacy['distinct_values_per_output_field'].get(name)!=1):
            raise ValueError('threshold3-comparison-required')
        mutants=proof.get('mutants',[])
        if not mutants or len({m['id'] for m in mutants})!=len(mutants): raise ValueError('threshold3-mutation-required')
        for mutant in mutants:
            if (mutant.get('line')!=row['source_line'] or mutant.get('source_sha256')!=row['source_sha256']
                or mutant.get('status') not in ('killed-failure','killed-divergent','survived','equivalent (argued, listed)')
                or type(mutant.get('valid_comparisons')) is not int or mutant['valid_comparisons']<1
                or mutant.get('evidence_complete') is not True
                or not isinstance(mutant.get('record_sha256'),str)
                or re.fullmatch('[0-9a-f]{64}',mutant['record_sha256']) is None):
                raise ValueError('threshold3-mutation-required')
    return set(expected)
