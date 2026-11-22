"""Linux-only custody channel. Only Howard's separate sender and age child receive the USB fd."""
from array import array
import os
from pathlib import Path
import re
import socket
import stat
import struct
import sys
import time


def check(ok):
    if not ok:
        raise ValueError("custody-channel")


def address(claim, pid):
    check(re.fullmatch("[0-9a-f]{64}", claim) and type(pid) is int and pid > 1)
    return "\0h3-" + claim + "-" + str(pid)


def peer(sock):
    return struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))


def mount(fd):
    import fcntl
    check(fcntl.fcntl(fd,fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY)
    lines = Path("/proc/self/fdinfo/" + str(fd)).read_text().splitlines()
    ids = [int(x.split()[1]) for x in lines if x.startswith("mnt_id:")]
    info = os.fstat(fd)
    check(len(ids) == 1 and stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 65536)
    return ids[0], "%d:%d" % (os.major(info.st_dev), os.minor(info.st_dev))


def send(claim, pid):
    # Howard supplies an already-open stdin from the dedicated medium ONLY
    # after seeing the consumed claim and the child's readiness. No filename.
    mount(0)
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as channel:
        channel.settimeout(5)
        channel.connect(address(claim,pid))
        p, uid, _ = peer(channel)
        check(p == pid and uid == os.getuid())
        check(channel.sendmsg([b"U"], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array("i",[0]))]) == 1)


def child(claim, binary, cipher, mount_id, device, ready, end):
    # Standalone exec child; the verifier never accepts descriptors on this channel.
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as listener:
        listener.bind(address(claim,os.getpid()))
        listener.listen(1)
        listener.settimeout(max(0, end-time.monotonic()))
        check(os.write(ready,b"R") == 1)
        os.close(ready)
        with listener.accept()[0] as sock:
            check(peer(sock)[1] == os.getuid())
            sock.settimeout(max(0, end-time.monotonic()))
            item = array("i")
            data, anc, flags, _ = sock.recvmsg(2,socket.CMSG_SPACE(item.itemsize),socket.MSG_CMSG_CLOEXEC)
            check(data == b"U" and not flags & (socket.MSG_TRUNC|socket.MSG_CTRUNC) and len(anc) == 1)
            level, kind, payload = anc[0]
            check((level,kind) == (socket.SOL_SOCKET,socket.SCM_RIGHTS) and len(payload)==item.itemsize)
            item.frombytes(payload)
            fd = item[0]
            check(mount(fd) == (mount_id,device) and mount_id > 0 and os.fstat(fd).st_dev != os.stat("/").st_dev)
            check(os.lseek(fd,0,os.SEEK_SET)==0)
            os.dup2(fd,0,inheritable=True)
            os.close(fd)
    check(time.monotonic() < end)
    os.set_inheritable(cipher,True)
    os.set_inheritable(binary,False)
    os.execve(binary,["age","--decrypt","-i","-","/proc/self/fd/"+str(cipher)],{"PATH":"/nonexistent"})


def entry(args):
    try:
        if args[0] == "send" and len(args)==3:
            send(args[1],int(args[2]))
        elif args[0]=="child" and len(args)==8:
            child(args[1],int(args[2]),int(args[3]),int(args[4]),args[5],int(args[6]),float(args[7]))
        else:
            raise ValueError()
        return 0
    except (Exception, KeyboardInterrupt):
        return 2


if __name__ == "__main__":
    sys.exit(entry(sys.argv[1:]))
