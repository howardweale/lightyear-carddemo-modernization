"""Named human-owned contract decisions; observations and old receipts stay intact."""
from datetime import date
from pathlib import Path
from .contracts import read_json, require
from .journey_order import file_hash, save
from .journey_runtime import JourneySigner, CONTROL
from lightyear_control_tower.decisions import verify_envelope
from lightyear_workflow.run_store import utcnow

CONTRACT=Path('factory/idempiere/contracts/oracle-date-second-precision.json')


def current_contract(root, today=None):
    path=root/CONTRACT
    if not path.exists():return None
    value=read_json(path)
    key=(root/CONTROL/'authority.public.pem').read_bytes()
    require(verify_envelope(value,key),'Timestamp contract signature differs')
    require(value['id']=='idempiere-oracle-date-seconds-v1' and value['owner']=='Howard Weale'
        and value['scope']['columns']==['adempiere.m_inout.shipdate']
        and value['scope']['oracle_datatype']=='DATE','Unexpected timestamp scope')
    today=today or date.today()
    return {**value,'review_due':today>=date.fromisoformat(value['review_date']),
        'effective':date.fromisoformat(value['effective_date'])<=today<date.fromisoformat(value['review_date'])}


def record_timestamp_acceptance(root, owner, review_date):
    require(owner=='Howard Weale','Use the authorized decision owner')
    require(not (root/CONTRACT).exists(),'Contract already recorded; preserve its immutable history')
    signer=JourneySigner(root)
    value=signer.sign({'artifact_type':'lightyear-owned-contract-decision',
        'id':'idempiere-oracle-date-seconds-v1','name':'iDempiere shipment time: second-level Oracle DATE precision',
        'owner':owner,'owner_role':'project and business-contract owner','decision':'accept-second-level-precision',
        'at':utcnow(),'effective_date':'2026-09-26','review_date':review_date,
        'authorization':'User explicitly requested acceptance of second-level precision for the demonstrated Oracle DATE column, with named ownership and a review date.',
        'scope':{'application':'iDempiere','columns':['adempiere.m_inout.shipdate'],'oracle_datatype':'DATE',
            'application_source_commit':'731515dcdd5278b843db33b9d3109d155b881951'},
        'rule':'For this column only, business comparison may use whole seconds after validating the same timezone and all date/time components through seconds. Preserve raw values and measured fractional loss. No rounding to a different second.',
        'limits':['No global timestamp normalization.','No acceptance for any other column or datatype.',
            'Subsecond ordering, audit and SLA uses are outside this contract.','Existing timestamp probes keep reporting the observed loss.',
            'No retrospective change to MS86, MS87 or MS88 verdicts; no full boundary, application or platform equivalence.'],
        'review_triggers':['Review date reached','Column datatype or application mapping changes','A business journey requires subsecond precision'],
        'evidence':{'receipt':'docs/calibration/idempiere-boundaries/receipt.json',
            'receipt_sha256':file_hash(root/'docs/calibration/idempiere-boundaries/receipt.json')},
        'independently_attested':False})
    save(root/CONTRACT,value)
    return value
