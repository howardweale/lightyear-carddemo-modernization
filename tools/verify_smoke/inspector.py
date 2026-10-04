"""Inspector v2 launcher as lyagent: token forwarding through RAM only.

The Inspector SDK does not automatically inherit arbitrary environment variables.
Its read-only session config lives in an anonymous Linux memfd, never on disk or
in command arguments. The parent keeps it alive until Inspector exits.
"""
import json
import os
import pwd
import subprocess


def main():
    if os.geteuid() != pwd.getpwnam("lyagent").pw_uid:
        raise SystemExit("Run inside the agent.py shell as lyagent")
    token = os.environ["LIGHTYEAR_VERIFY_TOKEN"]
    config = {"mcpServers": {"lightyear-verify": {
        "type": "stdio", "protocolEra": "auto",
        "command": "/opt/lightyear-verify-venv/bin/lightyear-verify-mcp",
        "args": ["--workspace", "/srv/dev", "--public-manifest", "/srv/dev/public.json",
                 "--judge-url", "http://127.0.0.1:8770"],
        "env": {"LIGHTYEAR_VERIFY_TOKEN": token},
    }}}
    fd = os.memfd_create("verify-inspector-session", os.MFD_CLOEXEC)
    try:
        os.write(fd, json.dumps(config).encode())
        os.lseek(fd, 0, os.SEEK_SET)
        env = {**os.environ, "HOST": "127.0.0.1", "CLIENT_PORT": "6274",
               "MCP_AUTO_OPEN_ENABLED": "false", "MCP_INSPECTOR_SECRET_STORE": "memory"}
        for key in ("DANGEROUSLY_OMIT_AUTH", "DANGEROUSLY_BIND_ALL_INTERFACES", "MCP_CATALOG_PATH"):
            env.pop(key, None)
        # Use the locally installed Inspector, pinned by package-lock.json.
        return subprocess.run(
            ["/srv/dev/inspector/node_modules/.bin/mcp-inspector", "--web", "--config",
             f"/proc/{os.getpid()}/fd/{fd}"], env=env).returncode
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())

