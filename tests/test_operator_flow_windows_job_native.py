"""Native Windows containment probes with inert children; no remote operations.

These tests are discovered by the existing Windows verification job. They are
not included in the Linux scratch suite and do not prove a complete publisher.
"""
import os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from tools.ci.operator_flow_windows_job import run_contained

@unittest.skipUnless(os.name=='nt','requires native Windows Job Objects')
class WindowsJobNativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP') if k in os.environ}
    def tearDown(self):self.tmp.cleanup()
    def run_child(self,source,**changes):
        args=dict(command=[sys.executable,'-B','-c',source],cwd=self.root,env=self.env,
            timeout=10,max_bytes=8192,memory_bytes=256*1024**2,process_limit=8)
        args.update(changes);return run_contained(**args)
    def test_original_success_bytes(self):
        r=self.run_child("import sys;sys.stdout.buffer.write(b'original\\x00bytes')")
        self.assertEqual((r.returncode,r.stdout,r.stderr),(0,b'original\x00bytes',None))
    def test_nonzero_not_success(self):
        r=self.run_child("import sys;print('failed');sys.exit(7)")
        self.assertEqual(r.returncode,7);self.assertEqual(r.stdout,b'failed\r\n')
    def test_stdout_flood_refuses(self):
        with self.assertRaisesRegex(ValueError,'publisher-job-output-limit'):
            self.run_child("import os;\nwhile True:os.write(1,b'x'*65536)",max_bytes=1024)
    def test_stderr_discarded(self):
        r=self.run_child("import os;os.write(2,b'x'*1048576);print('ok')")
        self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,b'ok\r\n');self.assertIsNone(r.stderr)
    def test_timeout_stops_original(self):
        started=self.root/'started';late=self.root/'late'
        code=f"from pathlib import Path;import time;Path({str(started)!r}).write_text('started');time.sleep(8);Path({str(late)!r}).write_text('late')"
        with self.assertRaisesRegex(ValueError,'publisher-job-timeout'):
            self.run_child(code,timeout=3)
        self.assertTrue(started.exists());self.assertFalse(late.exists())
    def test_parent_zero_does_not_hide_live_descendant(self):
        started=self.root/'grandchild-started';late=self.root/'grandchild-late'
        child=f"from pathlib import Path;import time;Path({str(started)!r}).write_text('started');time.sleep(6);Path({str(late)!r}).write_text('late')"
        code=f"import subprocess,sys;subprocess.Popen([sys.executable,'-B','-c',{child!r}])"
        with self.assertRaisesRegex(ValueError,'publisher-job-timeout'):
            self.run_child(code,timeout=3)
        self.assertTrue(started.exists());time.sleep(4);self.assertFalse(late.exists())
    def test_active_process_cap(self):
        child=self.root/'unexpected'
        code=f"import subprocess,sys\ntry: subprocess.Popen([sys.executable,'-B','-c',\"from pathlib import Path;Path({str(child)!r}).touch()\"])\nexcept OSError: print('limited')"
        r=self.run_child(code,process_limit=1)
        self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,b'limited\r\n');self.assertFalse(child.exists())
    def test_job_memory_cap(self):
        r=self.run_child("try: x=bytearray(512*1024**2)\nexcept MemoryError: print('limited')",
            memory_bytes=128*1024**2)
        self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,b'limited\r\n')

    def test_missing_executable_refuses_before_child(self):
        with self.assertRaisesRegex(ValueError,'publisher-job-create'):
            self.run_child('pass',command=[str(self.root/'missing.exe')])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_supervisor_death_closes_job_without_inherited_handle(self):
        import ctypes
        from ctypes import wintypes
        ready=self.root/'ready'
        grandchild="from pathlib import Path;import os,time;Path("+repr(str(ready))+").write_text(str(os.getppid())+' '+str(os.getpid()));time.sleep(60)"
        child="import subprocess,sys,time;subprocess.Popen([sys.executable,'-B','-c',"+repr(grandchild)+"]);time.sleep(60)"
        harness=self.root/'harness.py'
        repo=Path(__file__).resolve().parents[1]
        harness.write_text("import sys,os\nsys.path.insert(0,"+repr(str(repo))+")\nfrom tools.ci.operator_flow_windows_job import run_contained\nrun_contained("+repr([sys.executable,'-B','-c',child])+",cwd="+repr(str(self.root))+",env=dict(os.environ),timeout=30,max_bytes=1024,memory_bytes=268435456,process_limit=8)\n")
        p=subprocess.Popen([sys.executable,'-B',str(harness)],env=self.env,cwd=self.root,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=wintypes.HANDLE
        k.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];k.WaitForSingleObject.restype=wintypes.DWORD
        k.CloseHandle.argtypes=[wintypes.HANDLE];k.CloseHandle.restype=wintypes.BOOL
        handles=[]
        try:
            deadline=time.monotonic()+10
            while time.monotonic()<deadline and p.poll() is None:
                if ready.exists() and len(ready.read_text().split())==2:break
                time.sleep(0.02)
            self.assertTrue(ready.exists(),'inert grandchild was not started')
            pids=[int(x) for x in ready.read_text().split()]
            self.assertEqual(len(pids),2)
            for pid in pids:
                h=k.OpenProcess(0x100000,False,pid);self.assertTrue(h);handles.append(h)
                self.assertEqual(k.WaitForSingleObject(h,0),258)
            p.terminate();p.wait(timeout=5)
            for h in handles:self.assertEqual(k.WaitForSingleObject(h,5000),0)
        finally:
            if p.poll() is None:p.terminate();p.wait(timeout=5)
            for h in handles:k.CloseHandle(h)
