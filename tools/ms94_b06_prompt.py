"""B06 prompt composition: one immutable generic template across journeys."""
import hashlib
import json
from lightyear_calibration.contracts import canonical, require

JOURNEY_FIELDS = frozenset(('id', 'work_order', 'inputs', 'public_shapes', 'public_trace_contract', 'api_reference', 'deterministic_support', 'trace_fields'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def compose(template_bytes, journey_bytes, *, template_sha256, journey_sha256,
            previous_candidate=None, diagnostics=None):
    require(sha(template_bytes) == template_sha256, 'Generic template hash mismatch')
    require(sha(journey_bytes) == journey_sha256, 'Journey section hash mismatch')
    template = json.loads(template_bytes)
    journey = json.loads(journey_bytes)
    require(canonical(template) == template_bytes, 'Noncanonical generic template')
    require(canonical(journey) == journey_bytes, 'Noncanonical journey section')
    require(set(journey) == JOURNEY_FIELDS and journey['id'] in ('J1', 'J2', 'J3'), 'Journey section schema differs')
    require(template['artifact_type'] == 'ms94-b06-generic-builder-template/1', 'Wrong builder template')
    require((previous_candidate is None) == (diagnostics is None), 'Repair inputs must be paired')
    value = {'generic_template': template, 'journey_section': journey,
             'template_sha256': template_sha256, 'journey_section_sha256': journey_sha256}
    if previous_candidate is not None:
        require(isinstance(previous_candidate, str) and isinstance(diagnostics, list) and diagnostics,
                'Repair needs a candidate and delivered closed diagnostics')
        value['repair'] = {'previous_candidate': previous_candidate, 'diagnostics': diagnostics}
    return value
