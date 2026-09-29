"""Record an explicitly supplied human review against the exact frozen packet.

This command records an operator attestation; it does not perform a review or
make an AI into a human reviewer. Call only after receiving the named human's
explicit acceptance of these source hashes.
"""
from datetime import datetime,timezone
from pathlib import Path
from lightyear_calibration.contracts import read_json,require,verify
from lightyear_calibration.journey_order import file_hash,save
from lightyear_calibration.journey_runtime import JourneySigner


def record(root,packet,output,kind,reviewer,acceptance,independent=False):
    require(kind in ('support-source','independent-purchasing-rule-and-reference'),'Unknown review kind')
    require(not output.exists(),'Review record already exists')
    require(reviewer.strip() and acceptance.strip(),'Named human and explicit acceptance required')
    require(kind=='support-source' or independent,'Purchasing reviewer must be independent of the author')
    value=read_json(packet);verify(value)
    for name,sha in value['files'].items():require(file_hash(root/name)==sha,'Review source changed')
    result=JourneySigner(root).sign({'artifact_type':'ms94-human-review','review_kind':kind,
        'reviewer':reviewer,'reviewer_is_author':False if independent else None,
        'human_attestation':True,'accepted':True,'explicit_human_acceptance':acceptance,
        'packet_sha256':value['content_sha256'],'reviewed_at':datetime.now(timezone.utc).isoformat(),
        'limit':'Posting guard does not prevent application-internal costing or reposting.',
        'independent_identity_verification':False})
    save(output,result);return result


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--kind',required=True);p.add_argument('--reviewer',required=True)
    p.add_argument('--acceptance',required=True);p.add_argument('--independent',action='store_true');a=p.parse_args()
    print(json.dumps(record(a.root.resolve(),a.packet.resolve(),a.output.resolve(),a.kind,a.reviewer,a.acceptance,a.independent),indent=2))
