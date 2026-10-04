"""Administrator launcher: read one token, drop privileges, then exec the agent.

No token file is copied, printed, or passed in argv. Never install this setuid or
grant lyagent sudo permission for it. The administrator invokes it interactively.
"""
import os
from pathlib import Path
import sys


def main():
    import pwd

    if os.geteuid() != 0:
        raise SystemExit("Run this launcher with sudo as the VM administrator")
    agent = pwd.getpwnam("lyagent")
    token = Path("/var/lib/lightyear-verify/session/token").read_text().strip()
    if not token or any(c.isspace() for c in token):
        raise SystemExit("Invalid task token")
    env = {
        "HOME": agent.pw_dir,
        "USER": agent.pw_name,
        "LOGNAME": agent.pw_name,
        "SHELL": "/bin/bash",
        "PATH": f"{agent.pw_dir}/.local/bin:/opt/lightyear-verify-venv/bin:/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "TERM": os.environ.get("TERM", "xterm-256color"),
        "LIGHTYEAR_VERIFY_TOKEN": token,
    }
    os.setgroups([])
    os.setgid(agent.pw_gid)
    os.setuid(agent.pw_uid)
    os.umask(0o077)
    os.chdir("/srv/dev")
    command = sys.argv[1:] or ["/bin/bash", "--noprofile", "--norc", "-i"]
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    main()
