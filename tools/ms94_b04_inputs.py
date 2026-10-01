"""Prospective B03/B04 input comparison; no candidate source is transferred."""
import hashlib
from lightyear_calibration.contracts import canonical, read_json, require, verify
from lightyear_calibration.journey_order import file_hash


def compare(root, plan):
    previous = read_json(root/'docs/calibration/idempiere-ms94/stage-b-03/trials/pilot-01/plan.json')
    verify(previous)
    fields = ('initial_prompt', 'builder_client', 'requested_model', 'reasoning_effort',
              'tool_runtime', 'max_client_invocations', 'max_compilations', 'client_timeout_seconds',
              'max_elapsed_seconds', 'support_sha256')
    require(all(canonical(plan[n]) == canonical(previous[n]) for n in fields),
            'B04 would change a builder input, runtime, model request or limit')
    # All inherited executable code, public contracts, schemas and API resources are checked,
    # including the original controller/transport. B04 adds routing modules alongside these.
    selected = {n:h for n,h in previous['implementation_sha256'].items()
                if n.startswith(('src/', 'tools/', 'factory/'))}
    for name, digest in selected.items():
        require(file_hash(root/name) == digest, 'Inherited B03 code/public input changed: '+name)
    require(plan['assessed_on'] != previous['assessed_on'],
            'Revisit the prospective pooling declaration if assessment dates are identical')
    return {'builder_inputs_byte_identical': True, 'checked_fields': list(fields),
            'initial_prompt_bytes_sha256': hashlib.sha256(canonical(plan['initial_prompt'])).hexdigest(),
            'inherited_code_and_factory_files_checked': len(selected),
            'b03_trial_plan_sha256': previous['content_sha256'],
            'native_assessed_on': {'b03':previous['assessed_on'], 'b04':plan['assessed_on']},
            'pooled_n40_allowed': False,
            'pooling_omitted_reason': 'Native assessed_on differs from B03; exact first-attempt input identity is not claimed. Application clock and period windows remain real-time.'}
