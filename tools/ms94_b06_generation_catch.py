"""Replay of externally observed catch activation; no generated-frame trust."""
from tools.ms94_b06_admission import check

POLICY = 'handler-activation-v1'

def validate_unwind(event, required=False):
    record = event['record']
    check(event['catch_depth'] < record['entry_depth'] and bool(event['exception_class']),
          'observer-generation-unwind-depth')
    proof = event.get('catch_resolution')
    if proof is None:
        check(not required, 'observer-generation-catch-proof-missing')
        return  # Historical collector streams retain their original semantics.
    check(proof['thread_id'] == record['thread_id'], 'observer-generation-catch-thread')
    if proof['kind'] == 'uncaught':
        check(proof['frame_count'] == 0 and event['catch_depth'] == -1 and
              'location' not in proof, 'observer-generation-uncaught-depth')
    else:
        check(proof['kind'] == 'handler-breakpoint' and
              type(proof['frame_count']) is int and proof['frame_count'] > 0 and
              proof['frame_count'] == event['catch_depth'], 'observer-generation-catch-depth')
        location = proof['location']
        check(all(location.get(k) for k in ('class', 'method', 'signature')) and
              type(location.get('code_index')) is int and location['code_index'] >= 0,
              'observer-generation-catch-location')
