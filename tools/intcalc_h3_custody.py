"""Trusted verifier-only ports for H3-A. Does not open or receive a decryption identity."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
import time

from tools import intcalc_hidden_answer_receiver as rx
from tools import intcalc_private_reference_host as h1


def check(ok):
    if not ok:
        raise ValueError("stage2-custody")


def mounted(device, mount_id):
    for row in Path("/proc/self/mountinfo").read_bytes().splitlines():
        fields = row.split()
        check(len(fields)>=7)
        if fields[2].decode("ascii")==device or int(fields[0])==mount_id:
            return True
    return False


def absent_group(pid):
    try:
        os.killpg(pid,0)
    except ProcessLookupError:
        return True
    return False


@contextmanager
def opened(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        check(stat.S_ISREG(os.fstat(fd).st_mode))
        yield fd
    finally:
        os.close(fd)


class Session:
    def __init__(self, proc):
        self.proc=proc
        self.piped=self.success=False

    def pipe(self):
        check(not self.piped)
        self.piped=True
        fd=os.dup(self.proc.stdout.fileno())
        try:
            return rx.Pipe(fd)
        except BaseException:
            os.close(fd)
            raise

    def join_success(self, deadline):
        check(self.piped and self.proc.wait(timeout=max(0,deadline-time.monotonic()))==0
              and absent_group(self.proc.pid))
        self.success=True
        return True


class CustodyBroker:
    """Fixed vault leaves, pin-checked executable fd, exclusive ledger claim and local physical confirmation."""
    def __init__(self, root, vault, age, mount_id, device, projection, host_qualification, storage, announce, confirm):
        self.root=root
        self.vault=vault
        self.age=age
        self.mount_id=mount_id
        self.device=device
        self.projection=projection
        self.host_qualification=host_qualification
        self.storage=storage
        self.announce=announce
        self.confirm=confirm
        self.phase="fresh"
        self.claim_digest=None

    def claim(self, row, end):
        check(self.phase=="fresh" and row==self.projection and time.monotonic()<end)
        self.phase="spent"
        self.claim_digest=self.storage()
        check(rx.hash_ok(self.claim_digest))
        self.phase="claimed"
        return self.claim_digest

    def advance(self, claim, current, following, end):
        check(self.phase==current and claim==self.claim_digest and time.monotonic()<end)
        self.phase=following

    def read_completion(self, claim, end):
        self.advance(claim,"claimed","completion",end)
        path=h1.private_directory(self.root/self.vault)/"completion.json"
        h1.private_control_file(path)
        raw=h1.read(path,65536)
        check(rx.completion(raw,self.projection)['bindings']['host_qualification_sha256']==self.host_qualification)
        return raw

    @contextmanager
    def open_cipher(self, claim, end):
        self.advance(claim,"completion","cipher",end)
        with opened(h1.private_directory(self.root/self.vault)/"answers.age") as fd:
            yield fd
        check(self.phase=="reaped")
        self.phase="closed"

    @contextmanager
    def decrypt(self, fd, claim, expected, end):
        self.advance(claim,"cipher","decrypt",end)
        check(expected==self.projection["age_sha256"] and mounted(self.device,self.mount_id))
        with opened(self.age) as binary:
            info=os.fstat(binary)
            check(info.st_nlink==1 and info.st_uid in (0,os.getuid()) and info.st_mode & 0o022==0
                  and 0<info.st_size<=64*1024*1024)
            with os.fdopen(os.dup(binary),"rb") as stream:
                check(hashlib.file_digest(stream,"sha256").hexdigest()==expected)
            os.lseek(binary,0,os.SEEK_SET)
            reader,writer=os.pipe()
            proc=None
            try:
                proc=subprocess.Popen([sys.executable,"-I","-B",str(Path(__file__).with_name("intcalc_h3_usb_channel.py")),
                    "child",claim,str(binary),str(fd),str(self.mount_id),self.device,str(writer),str(end)],
                    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                    close_fds=True,pass_fds=(binary,fd,writer),start_new_session=True,env={})
                os.close(writer)
                writer=None
                check(select.select([reader],[],[],max(0,end-time.monotonic()))[0] and os.read(reader,1)==b"R")
                self.announce(claim,proc.pid,end)
                session=Session(proc)
                yield session
                check(session.success)
            finally:
                if writer is not None:
                    os.close(writer)
                os.close(reader)
                if proc is not None:
                    if not absent_group(proc.pid):
                        try:
                            os.killpg(proc.pid,signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    proc.stdout.close()
                    proc.wait(timeout=max(0,end-time.monotonic()))
                    check(absent_group(proc.pid))
        self.phase="reaped"

    def removal_receipt(self, claim, end):
        self.advance(claim,"closed","consumed",end)
        # Operator callback is synchronous, private and after age and the ciphertext handles closed.
        check(self.confirm(claim,end) is True and not mounted(self.device,self.mount_id)
              and time.monotonic()<end)
        return dict(claim_sha256=claim,operation_id=self.projection["operation_id"],decryptor_exited=True,
                    group_absent=True,handles_closed=True,usb_mount_absent=True,howard_removed_usb=True,
                    howard_no_identity_copy=True,codex_absent=True)

def terminal_note(claim,pid,end):
    check(time.monotonic()<end)
    with open("/dev/tty","w",encoding="ascii") as tty:
        check(tty.isatty())
        print("Stage-2 claim",claim,"custodian child",pid,file=tty,flush=True)


def terminal_removal(claim,end):
    import termios
    with open("/dev/tty","w",encoding="ascii") as tty:
        fd=os.open("/dev/tty",os.O_RDONLY|os.O_NONBLOCK|os.O_NOCTTY)
        try:
            check(os.isatty(fd) and tty.isatty())
            termios.tcflush(fd,termios.TCIFLUSH)
            answer="REMOVED NO-COPY CODEX-STOPPED "+claim
            print("After ejecting and physically removing the dedicated stick, confirming no identity copy "
                  "on either host, and Codex stopped throughout, type:",answer,file=tty,flush=True)
            check(select.select([fd],[],[],max(0,end-time.monotonic()))[0])
            return os.read(fd,256)==(answer+"\n").encode("ascii") and time.monotonic()<end
        finally:
            os.close(fd)
