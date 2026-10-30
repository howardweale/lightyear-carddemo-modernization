"""Bind existing P5 envelope bytes to independently supplied expectations.

Component only. Caller provisioning of reviewed keys/run/source expectations is
not implemented here. No proof of original controller origin, strict predicates,
death or admission follows from a valid signature. No signing or qualification.
Existing inventory/envelope formats and strict qualifier remain unchanged.
"""
from hashlib import sha256
from pathlib import Path
import re
from lightyear_control_tower.decisions import verify_envelope
from lightyear_factory.contracts import ContractError
from lightyear_factory.model_admission import _bounded_regular_bytes
from lightyear_execution.configured_receipt_terminal import _original_json
from tools.ci.p5_drills import DRILLS,EXPECTED

def _require(value,reason):
    if not value:raise ContractError('configured-outcome-inventory-'+reason)

def _limits():
    return {'summary.json':1024*1024,**{name+'.json':8*1024*1024 for name in DRILLS},
            **{name+'.public.pem':4096 for name in DRILLS}}

def check_outcome_inventory_bytes(raw,expected):
    # expected must come from separately reviewed external configuration, never
    # from this inventory, bundled keys or signed body. Matching mappings alone
    # do not establish that provisioning boundary; this function grants nothing.
    limits=_limits()
    _require(type(raw) is dict and set(raw)==set(limits),'file-set')
    _require(all(type(raw[k]) is bytes and 0<len(raw[k])<=limit for k,limit in limits.items()),'size')
    _require(type(expected) is dict and set(expected)==set(DRILLS),'expected-set')
    report=_original_json(raw['summary.json'])
    _require(type(report) is dict and report.get('schema')=='p5-drills/1' and report.get('complete') is True,'summary')
    rows=report.get('drills')
    _require(type(rows) is list and len(rows)==len(DRILLS) and all(type(row) is dict for row in rows),'rows')
    _require(all(type(row.get('id')) is str for row in rows) and {row['id'] for row in rows}==set(DRILLS),'ids')
    for row in rows:
        name=row['id'];binding=expected[name]
        _require(type(binding) is dict and set(binding)=={'public_key','commit','run_id','run_attempt','source_sha256'},'expected-shape')
        public=binding['public_key'];pins=binding['source_sha256']
        _require(type(public) is bytes and 0<len(public)<=4096 and type(binding['commit']) is str
                 and re.fullmatch('[0-9a-f]{40}',binding['commit']) is not None
                 and type(binding['run_id']) is str and re.fullmatch('[1-9][0-9]{0,19}',binding['run_id']) is not None
                 and binding['run_attempt']=='1' and type(pins) is dict and bool(pins)
                 and all(type(k) is str and bool(k) and type(v) is str and re.fullmatch('[0-9a-f]{64}',v) is not None for k,v in pins.items()),'expected-values')
        _require(row.get('harness_error') is False and row.get('receipt_file')==name+'.json'
                 and row.get('public_key_file')==name+'.public.pem','row-paths')
        receipt_raw=raw[name+'.json'];envelope=_original_json(receipt_raw)
        _require(type(envelope) is dict and sha256(receipt_raw).hexdigest()==row.get('receipt_sha256'),'receipt-digest')
        _require(raw[name+'.public.pem']==public,'independent-public-key')
        _require(verify_envelope(envelope,public),'native-signature')
        _require(envelope.get('id')==name and envelope.get('expected')==EXPECTED[name]
                 and type(envelope.get('expectation_met')) is bool
                 and type(envelope.get('gaps')) is list and all(type(x) is str for x in envelope['gaps'])
                 and type(row.get('expectation_met')) is bool
                 and envelope['expectation_met']==row['expectation_met'] and envelope['gaps']==row.get('gaps'),'signed-row-relations')
        _require(all(envelope.get(k)==binding[k] for k in ('commit','run_id','run_attempt','source_sha256')),'independent-run-source')
    # In particular, do not set gaps=[], expectation_met or production flags,
    # call qualify(), infer case success, or return an authority receipt.

def read_outcome_inventory(directory,expected):
    root=Path(directory)
    _require(root.is_absolute() and root.is_dir() and not any(p.casefold()=='onedrive' for p in root.parts),'root')
    _require(not any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (root,*root.parents)),'redirected-root')
    limits=_limits()
    _require({p.name for p in root.iterdir()}==set(limits),'directory-inventory')
    raw={name:_bounded_regular_bytes(root/name,limit,'configured-outcome-inventory-file') for name,limit in limits.items()}
    check_outcome_inventory_bytes(raw,expected)
    _require({p.name for p in root.iterdir()}==set(limits),'directory-changed')
    _require(all(_bounded_regular_bytes(root/name,limit,'configured-outcome-inventory-file')==raw[name] for name,limit in limits.items()),'bytes-changed')
    return raw
