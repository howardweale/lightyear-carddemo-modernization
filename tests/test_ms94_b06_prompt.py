import json
import unittest
from lightyear_calibration.contracts import canonical
from tools.ms94_b06_prompt import compose, sha, JOURNEY_FIELDS


class GenericPromptTests(unittest.TestCase):
    def test_template_bytes_identical_for_all_journeys_and_repairs(self):
        template = canonical({'artifact_type': 'ms94-b06-generic-builder-template/1', 'instruction': 'fixed'})
        for name in ('J1', 'J2', 'J3'):
            section = canonical({k: name if k == 'id' else {} for k in JOURNEY_FIELDS})
            args = dict(template_sha256=sha(template), journey_sha256=sha(section))
            for kwargs in ({}, {'previous_candidate': 'candidate', 'diagnostics': [{'id': 'closed'}]}):
                prompt = compose(template, section, **args, **kwargs)
                self.assertEqual(template, canonical(prompt['generic_template']))
                self.assertEqual(sha(section), prompt['journey_section_sha256'])

    def test_mismatch_override_or_partial_repair_is_refused(self):
        template = canonical({'artifact_type': 'ms94-b06-generic-builder-template/1'})
        section = {k: 'J1' if k == 'id' else {} for k in JOURNEY_FIELDS}
        raw = canonical(section)
        args = dict(template_sha256=sha(template), journey_sha256=sha(raw))
        with self.assertRaises(ValueError): compose(template+b' ', raw, **args)
        with self.assertRaises(ValueError): compose(template, raw, **args, previous_candidate='x')
        section['instruction'] = 'override'
        raw = canonical(section)
        with self.assertRaises(ValueError): compose(template, raw, template_sha256=sha(template), journey_sha256=sha(raw))
