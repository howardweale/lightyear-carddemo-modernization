"""Argument refusal checks; no process is created by these tests."""
import os,sys,tempfile,unittest
from pathlib import Path
from tools.ci.operator_flow_windows_job import _limits,run_contained

class WindowsJobContractTests(unittest.TestCase):
    def args(self):
        return dict(command=[sys.executable,'-c','pass'],cwd=Path(tempfile.gettempdir()),
            env={'PATH':'unused'},timeout=1,max_bytes=1024,memory_bytes=256*1024**2,process_limit=4)
    def test_invalid_limits_refuse(self):
        for key,value in [('timeout',True),('timeout',float('nan')),('timeout',0),
            ('max_bytes',False),('max_bytes',4194305),('memory_bytes',0),('process_limit',0),('process_limit',33)]:
            with self.subTest(key=key,value=value):
                args=self.args();args[key]=value
                with self.assertRaisesRegex(ValueError,'publisher-job-limits'):_limits(**args)
    def test_environment_framing_refuses(self):
        for env in ({},{'PATH':'a','Path':'b'},{'A=B':'x'},{'A':'x\0y'},{'A':False}):
            args=self.args();args['env']=env
            with self.assertRaisesRegex(ValueError,'publisher-job-environment'):_limits(**args)
    def test_command_and_directory_refuse(self):
        for key,value in [('command',[]),('command',['relative.exe']),('command',[sys.executable,'x\0y']),('cwd','relative')]:
            args=self.args();args[key]=value
            with self.assertRaises(ValueError):_limits(**args)
    def test_non_windows_refuses_or_native_arguments_fail_first(self):
        args=self.args()
        if os.name!='nt':
            with self.assertRaisesRegex(ValueError,'publisher-job-windows-only'):run_contained(**args)
        else:
            args['process_limit']=False
            with self.assertRaisesRegex(ValueError,'publisher-job-limits'):run_contained(**args)
