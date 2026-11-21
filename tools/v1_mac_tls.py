"""Public MAC-TLS-1. The CLI exposes one host and one TLS handshake; no application protocol."""
import argparse
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import re
import socket
import ssl
import sys
import time

HOST = "api.openai.com"
PORT = 443
WINDOW = 30
ID = re.compile(r"v1-rehearsal-[0-9a-f]{32}\Z")


def require(ok):
    if not ok:
        raise ValueError("mac-tls-1-refused")


def handshake():
    os.environ.clear()
    require(not os.environ)
    start = time.monotonic_ns()
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    require(ctx.check_hostname and ctx.verify_mode == ssl.CERT_REQUIRED)
    dns_start = time.monotonic_ns()
    addresses = socket.getaddrinfo(HOST, PORT, type=socket.SOCK_STREAM)
    resolved = time.monotonic_ns()
    family, kind, proto, _, address = addresses[0]
    with socket.socket(family, kind, proto) as channel:
        channel.settimeout(10)
        channel.connect(address)
        connected = time.monotonic_ns()
        with ctx.wrap_socket(channel, server_hostname=HOST, do_handshake_on_connect=False) as tls:
            tls.do_handshake()
            finished = time.monotonic_ns()
            require(tls.getpeercert() and tls.version())
            version = tls.version()
    return dict(schema="mac-tls-1-public/1", host=HOST, port=PORT, verified=True,
                environment_empty=True, trust="interpreter default server-auth roots",
                python=sys.version.split()[0], openssl=ssl.OPENSSL_VERSION, tls=version,
                verify_mode=int(ctx.verify_mode), check_hostname=ctx.check_hostname,
                clock="monotonic_ns", ticks_per_second=10**9, context_ticks=dns_start-start, dns_ticks=resolved-dns_start,
                connect_ticks=connected-resolved, handshake_ticks=finished-connected,
                http_requests=0, application_bytes=0, credentials=0, prompts=0)


def child(pipe):
    try:
        row = handshake()
        row["child_python_sha256"] = hashlib.sha256(Path(sys.executable).resolve(strict=True).read_bytes()).hexdigest()
        pipe.send_bytes(json.dumps(row,sort_keys=True).encode("ascii"))
    except (Exception,KeyboardInterrupt):
        pipe.send_bytes(b"{}")
    finally:
        pipe.close()


def offline_terminal():
    # Exercise terminal echo cancellation only on our own public pseudo-terminal.
    import pty
    import termios
    master, slave = pty.openpty()
    try:
        before = termios.tcgetattr(slave)
        quiet = list(before)
        quiet[3] &= ~termios.ECHO
        try:
            termios.tcsetattr(slave,termios.TCSANOW,quiet)
            require(not termios.tcgetattr(slave)[3] & termios.ECHO)
            os.write(master,b"\x04")  # EOF at a fresh canonical input line.
            require(os.read(slave,1)==b"")
        finally:
            termios.tcsetattr(slave,termios.TCSANOW,before)
    finally:
        os.close(slave)
        os.close(master)
    return "synthetic-pty-eof-echo-disabled"


def run(identifier, expected_python):
    require(ID.fullmatch(identifier) and sys.platform=="darwin" and platform.machine()=="arm64")
    require(sys.flags.isolated and sys.dont_write_bytecode and set(os.environ) <= {"LC_CTYPE","__CF_USER_TEXT_ENCODING"})
    os.environ.clear()
    digest=hashlib.sha256(Path(sys.executable).resolve(strict=True).read_bytes()).hexdigest()
    require(re.fullmatch("[0-9a-f]{64}",expected_python) and digest==expected_python)
    ctx=multiprocessing.get_context("spawn")
    recv,send=ctx.Pipe(duplex=False)
    proc=ctx.Process(target=child,args=(send,),daemon=True)
    end=time.monotonic()+WINDOW
    try:
        proc.start()
        send.close()
        require(recv.poll(max(0,end-time.monotonic()-2)))
        row=json.loads(recv.recv_bytes(4096))
        proc.join(max(0,end-time.monotonic()-1))
        require(proc.exitcode==0 and row.get("verified") is True and row.get("child_python_sha256")==digest)
    finally:
        recv.close()
        send.close()
        if proc.pid is not None:
            if proc.is_alive():
                proc.kill()
                proc.join(max(0,end-time.monotonic()))
            require(not proc.is_alive())
        proc.close()
    row.update(rehearsal_id=identifier, python_sha256=digest, child_reaped=True,
               terminal_check=offline_terminal(), operator_qualification=False)
    return row


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rehearsal-id",required=True)
    parser.add_argument("--python-sha256",required=True)
    args=parser.parse_args()
    try:
        print(json.dumps(run(args.rehearsal_id,args.python_sha256),sort_keys=True))
    except (Exception,KeyboardInterrupt):
        print("mac-tls-1-refused",file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    sys.exit(main())
