"""Zero-model delivery witness using actual exported canonical diagnostic bytes."""
import hashlib
from lightyear_calibration.contracts import canonical, require, seal
from tools.ms94_b04_feedback_route import partition, route


def witness(observed,suspect):
    if suspect:
        require(observed==[],'Equipment-origin failure exposed candidate feedback')
        return seal({'disposition':'halted-equipment-suspect','diagnostics':[],
            'builder_input_bytes':'[]','builder_input_sha256':hashlib.sha256(b'[]').hexdigest(),
            'analyst_invoked':False,'sink_invoked':False,'model_calls':0,'scope':'Zero-model transport qualification'})
    direct,legacy=partition(observed)
    # Legacy review remains gated. No analyst model is called in equipment
    # qualification; a deterministic decline fixture exercises that boundary.
    proposal={'decisions':[{'diagnostic_id':d['id'],'disposition':'reject',
                           'reason':'outside-permitted-scope'} for d in legacy]} if legacy else None
    routed=route(observed,proposal)
    delivered=routed['diagnostics']
    require(delivered==direct,'Candidate runtime observations were gated or legacy items bypassed review')
    raw=canonical(delivered)
    # The receiving sink decodes the actual transport bytes; no builder/model
    # is invoked, and this is never represented as a successful model repair.
    import json
    received=json.loads(raw)
    require(received==direct,'Transport changed diagnostic bytes')
    return seal({'disposition':'direct-runtime-forwarded' if direct else 'legacy-review-declined' if legacy else 'no-feedback',
        'diagnostics':received,'builder_input_bytes':raw.decode(),
        'builder_input_sha256':hashlib.sha256(raw).hexdigest(),'routing':routed,
        'analyst_invoked':False,'legacy_analyst_fixture':bool(legacy),'sink_invoked':bool(direct),
        'model_calls':0,'scope':'Zero-model transport qualification; no model repair outcome'})
