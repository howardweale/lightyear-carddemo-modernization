"""Trusted pre-candidate /proc probe; never connects to or consumes JDWP."""
import hashlib
import json
from pathlib import Path


def listener(proc=Path('/proc')):
    inodes = set()
    for name in ('tcp', 'tcp6'):
        for line in (proc / 'net' / name).read_text().splitlines()[1:]:
            fields = line.split()
            if fields[1].split(':')[-1] == '138D' and fields[3] == '0A':
                inodes.add(fields[9])  # LISTEN port 5005; do not perform a handshake.
    owners = []
    for process in proc.iterdir():
        if not process.name.isdigit():
            continue
        try:
            sockets = {p.readlink().as_posix() for p in (process / 'fd').iterdir()}
            if not any('socket:[' + inode + ']' in sockets for inode in inodes):
                continue
            executable = (process / 'exe').resolve(strict=True)
            args = (process / 'cmdline').read_bytes().split(b'\0')
            # Record names only: other environment entries may contain secrets.
            option_names = {b'JAVA_TOOL_OPTIONS', b'JDK_JAVA_OPTIONS', b'_JAVA_OPTIONS', b'LD_PRELOAD', b'LD_LIBRARY_PATH'}
            option_environment = sorted({entry.split(b'=', 1)[0].decode('ascii')
                for entry in (process / 'environ').read_bytes().split(b'\0')
                if b'=' in entry and entry.split(b'=', 1)[0] in option_names
                and entry.split(b'=', 1)[1]})
            stat = (process / 'stat').read_text().rsplit(')', 1)[1].split()
            owners.append({'pid': int(process.name), 'start_ticks': int(stat[19]),
                           'executable': str(executable),
                           'java_binary_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
                           'arguments': [arg.decode('utf-8') for arg in args if arg],
                           'jvm_option_environment_present': option_environment,
                           'socket_inodes': sorted(inodes)})
        except (FileNotFoundError, ProcessLookupError):
            continue
    return owners


if __name__ == '__main__':
    print(json.dumps(listener()), flush=True)
