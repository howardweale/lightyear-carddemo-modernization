"""Linux synthetic descriptor protocol tests. Only a fixed public marker is transferred."""
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from tools import intcalc_h3_custody as broker
from tools import intcalc_h3_usb_channel as bridge


@unittest.skipUnless(sys.platform=="linux","private-host descriptor protocol requires Linux")
class DescriptorTests(unittest.TestCase):
    def test_real_descriptor_handshake_uses_only_public_marker(self):
        claim="9"*64
        until=time.monotonic()+10
        read_fd,write_fd=os.pipe()
        with tempfile.TemporaryFile(dir="/dev/shm") as marker:
            marker.write(b"PUBLIC TOKEN"); marker.flush()
            reader=self.enterContext(open('/proc/self/fd/'+str(marker.fileno()),'rb'))
            mount,device=bridge.mount(reader.fileno())
            pid=os.fork()
            if pid==0:
                try:
                    os.close(read_fd)
                    def synthetic_exec(binary,argv,env):
                        ok=(os.read(0,32)==b"PUBLIC TOKEN" and argv[1:4]==["--decrypt","-i","-"]
                            and env=={"PATH":"/nonexistent"})
                        os._exit(0 if ok else 3)
                    bridge.os.execve=synthetic_exec
                    bridge.child(claim,marker.fileno(),marker.fileno(),mount,device,write_fd,until)
                except BaseException:
                    os._exit(2)
            os.close(write_fd)
            try:
                self.assertTrue(select.select([read_fd],[],[],5)[0])
                self.assertEqual(os.read(read_fd,1),b"R")
                sender=Path(bridge.__file__)
                submitted=subprocess.run([sys.executable,"-I","-B",str(sender),"send",claim,str(pid)],
                                          stdin=reader,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
                self.assertEqual((submitted.returncode,submitted.stdout,submitted.stderr),(0,b"",b""))
                while time.monotonic()<until:
                    child,status=os.waitpid(pid,os.WNOHANG)
                    if child:
                        pid=None
                        self.assertEqual(os.waitstatus_to_exitcode(status),0)
                        break
                    time.sleep(.01)
                self.assertIsNone(pid)
            finally:
                os.close(read_fd)
                if pid is not None:
                    try:
                        os.kill(pid,signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    os.waitpid(pid,0)

    def test_age_exit_required_after_anonymous_pipe_eof(self):
        for exit_code in (0,7):
            with subprocess.Popen([sys.executable,"-I","-c","raise SystemExit("+str(exit_code)+")"],
                                  stdout=subprocess.PIPE,start_new_session=True) as proc:
                session=broker.Session(proc)
                end=time.monotonic()+5
                with session.pipe() as pipe:
                    self.assertEqual(pipe.read(1,end),b"")
                if exit_code==0:
                    self.assertTrue(session.join_success(end))
                else:
                    with self.assertRaises(ValueError):
                        session.join_success(end)
                with self.assertRaises(ValueError):
                    session.pipe()
