"""Model-free capability probes; deliberately not an OS sandbox attestation."""
import unittest
from unittest.mock import Mock
from tools.ms94_b06_builder_boundary import dispatch, admit_transport, ARGUMENTS
from tools.ms94_tool_policy_v5 import capability_arguments, verify_events


class BuilderBoundaryTests(unittest.TestCase):
    def test_tools_read_attempts_never_reach_host_broker(self):
        broker = Mock()
        for name, args in (
            ('read_file', {'path': 'tools/ms94_b06_materials.py'}),
            ('shell', {'command': 'type tools/ms94_b06_materials.py'}),
            ('public_api', {'class_name': '../tools/ms94_b06_materials.py'}),
            ('public_api', {'class_name': 'C:/repo/tools/ms94_b06_materials.py'}),
            ('public_api', {'class_name': 'tools.ms94_b06_materials'}),
            ('public_api', {'class_name': 'org.compiere.model.PO', 'path': 'tools/private.py'}),
            ('public_contract', {'scenario': '../../tools/ms94_b06_materials.py'}),
            ('deterministic_support', {'path': 'tools/private.py'})):
            with self.subTest(name=name, args=args), self.assertRaises(ValueError): dispatch(broker, name, args)
        broker.call.assert_not_called()

    def test_read_only_flag_is_not_accepted_as_os_confidentiality_proof(self):
        with self.assertRaisesRegex(ValueError, 'filesystem denial not demonstrated'):
            admit_transport(capability_arguments(), ARGUMENTS, [], os_read_probe_passed=False)

    def test_unknown_cli_read_capability_fails_closed(self):
        for kind in ('file_read', 'command_execution', 'web_search', 'file_change'):
            with self.assertRaises(ValueError): verify_events([{'item': {'type': kind}}], 'builder', [])


if __name__ == '__main__': unittest.main()
