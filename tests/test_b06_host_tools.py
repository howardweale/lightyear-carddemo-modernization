import os
from pathlib import Path
import tempfile
import unittest
from tools.b06_host_probe.jdk import executable
from tools.b06_host_probe.stress import run
from tools.check_source_lf import check_paths


class HostToolsTests(unittest.TestCase):
    def test_explicit_toolchain_no_path_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'bin').mkdir()
            tool=root/'bin'/('java.exe' if os.name=='nt' else 'java');tool.write_bytes(b'fixture')
            self.assertEqual(tool,executable(root,'java'))
            with self.assertRaisesRegex(ValueError,'host-jdk-tool-missing'):
                executable(root,'javac')
            with self.assertRaisesRegex(ValueError,'host-jdk-tool-not-allowed'):
                executable(root,'../java')

    def test_invalid_heap_refuses_before_launch_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'new'
            for value in (0,31,4097,True):
                with self.assertRaisesRegex(ValueError,'stress observer heap out of range'):
                    run(Path(tmp),out,observer_heap_mib=value)
            self.assertFalse(out.exists())

    def test_changed_source_lf_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'tools').mkdir();path=root/'tools/probe.py'
            path.write_bytes(b'pass\r\n')
            with self.assertRaisesRegex(ValueError,'source-crlf: tools/probe.py'):
                check_paths(root,['tools/probe.py'])
            path.write_bytes(b'pass\n');check_paths(root,['tools/probe.py'])
