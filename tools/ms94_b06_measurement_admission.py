"""Require builder OS evidence for measurement and its zero-model preflight.

Native judge qualification has no builder and does not import this gate. Passing
this gate conveys no model-call authority and no complete preflight verdict.
"""
from lightyear_calibration.contracts import digest, seal
from tools.ms94_b06_admission import check
from tools.ms94_b06_os_probe import admit


def builder_gate(plan, context):
    from tools.ms94_b06_engineering_boundary import refuse_engineering
    refuse_engineering(plan)
    refuse_engineering(context)
    check(isinstance(context, dict) and isinstance(plan.get('builder_boundary'), dict),
          'measurement-builder-probe-required')
    spec = plan['builder_boundary']
    check(spec.get('transport_sha256') == digest(context['transport']),
          'measurement-builder-transport-changed')
    record = admit(context['root'], spec['probe'], context['public_key'], context['transport'])
    return {'probe_file_sha256': spec['probe']['sha256'],
            'probe_content_sha256': record['content_sha256'],
            'transport_sha256': spec['transport_sha256']}


def preflight_builder_gate(plan, context):
    return seal({'artifact_type': 'ms94-b06-preflight-builder-admission/1',
                 'plan_sha256': plan['content_sha256'], **builder_gate(plan, context),
                 'model_calls': 0, 'complete_preflight_passed': False})
