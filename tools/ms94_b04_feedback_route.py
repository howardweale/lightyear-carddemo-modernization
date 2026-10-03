"""Forward qualified closed runtime observations unchanged; review structural items only."""
from lightyear_calibration.contracts import require
from lightyear_calibration.journey_repair import select_feedback
from tools.qualification_feedback_v4 import EXCEPTIONS, STAGES

VERSION = 'candidate-origin-runtime-direct-delivery-v2'


def partition(observed):
    require(len({d['id'] for d in observed}) == len(observed), 'Duplicate diagnostic identity')
    runtime, structural = [], []
    for d in observed:
        if d.get('category') != 'candidate-runtime-exception':
            structural.append(d); continue
        required = {'id','category','exception_class','thrown_by','candidate_frame','lanes'}
        require(required <= set(d) <= required | {'public_stage','api_call'}, 'Runtime diagnostic contains undeclared fields')
        require(d['exception_class'] in EXCEPTIONS | {'other'} and d['thrown_by'] in ('candidate','application')
                and d['lanes'] in ('one','both'), 'Unqualified runtime diagnostic')
        frame=d['candidate_frame']
        require(set(frame)=={'method','line'} and isinstance(frame['method'],str)
                and type(frame['line']) is int and frame['line']>0, 'Invalid candidate frame')
        require('public_stage' not in d or d['public_stage'] in {x[0] for x in STAGES}, 'Unknown public stage')
        # Only candidate-origin runtime crashes bypass the existing analyst.
        (runtime if d['thrown_by']=='candidate' else structural).append(d)
    return runtime, structural


def route(observed, structural_proposal=None):
    runtime, structural = partition(observed)
    require(bool(structural) == (structural_proposal is not None), 'Structural reviewer accounting differs')
    selected = select_feedback(structural, structural_proposal, True) if structural else []
    ids={d['id'] for d in runtime+selected}
    return {'routing_policy':VERSION, 'runtime_forwarded_ids':[d['id'] for d in runtime],
            'analyst_proposal':structural_proposal,
            'diagnostics':[d for d in observed if d['id'] in ids]}


def verify_route(observed, record):
    expected=route(observed,record['analyst_proposal'])
    require({k:v for k,v in record.items() if k not in ('content_sha256','signature')} == expected,
            'Runtime/structural feedback routing differs')
    return expected['diagnostics']
