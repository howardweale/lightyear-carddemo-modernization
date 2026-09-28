import tempfile
from pathlib import Path
import tomllib
import unittest
from tools.qualification_transport_policy import builder_arguments,verify_events,SERVER,TOOLS
from lightyear_calibration.contracts import CalibrationError


class TransportPolicy(unittest.TestCase):
    def test_config_roundtrip_and_only_local_server(self):
        args=builder_arguments(Path('.'),Path('work/native-venv/Scripts/python.exe'),'test',2)
        config=tomllib.loads(next(v for v in args if v.startswith('mcp_servers=')))
        self.assertEqual({SERVER},set(config['mcp_servers']))
        s=config['mcp_servers'][SERVER]
        self.assertTrue(s['required']);self.assertEqual(list(TOOLS),s['enabled_tools'])
        self.assertIn('--ignore-user-config',args)

    def test_only_builder_can_use_approved_server_and_tools(self):
        event={'item':{'type':'mcp_tool_call','server':SERVER,'tool':'public_api'}}
        self.assertEqual(1,verify_events([event],'builder')['allowed_mcp_event_count'])
        with self.assertRaises(CalibrationError):verify_events([event],'analyst')
        for key,value in [('server','private'),('tool','read_file')]:
            wrong={'item':{**event['item'],key:value}}
            with self.assertRaises(CalibrationError):verify_events([wrong],'builder')

    def test_shell_browser_and_file_writes_rejected(self):
        for kind in ('command_execution','web_search','file_change'):
            with self.assertRaises(CalibrationError):verify_events([{'item':{'type':kind}}],'builder')


if __name__=='__main__':unittest.main()
