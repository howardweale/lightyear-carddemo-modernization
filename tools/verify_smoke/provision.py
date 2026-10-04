"""Dedicated-VM provisioning. Only public tracked assets enter the installation.

The kit never accepts an arbitrary evaluation path and never resets judge state.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone

INSTALL = Path("/opt/lightyear-verify")
STATE = Path("/var/lib/lightyear-verify-smoke")
PRIVATE = Path("/var/lib/lightyear-verify")
DEV = Path("/srv/dev")
TOWER = Path("/srv/verify-tower")
FIXTURE = "tests/mainframe/fixtures/arrival-rehearsal/INTCALC-run1-2026-10-05"
PREFIXES = ("src/", "spec/mainframe/", "tests/", "candidate-java/", "extensions/runtime/")
SINGLE = {"pyproject.toml", "README.md", "tools/run_verify_acceptance.py"}

UNIT = """[Unit]
Description=Lightyear Verify public-fixture smoke judge
After=network.target

[Service]
Type=simple
User=lyjudge
Group=lyjudge
WorkingDirectory=/opt/lightyear-verify
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=PYTHONUTF8=1
Environment=PATH=/usr/bin:/bin
UMask=0077
ExecStart=/opt/lightyear-verify-venv/bin/lightyear-judge serve --data-root /var/lib/lightyear-verify/session --task verify-intcalc --port 8770
Restart=no
KillMode=control-group
TimeoutStopSec=30
StandardOutput=append:/var/lib/lightyear-verify/service.log
StandardError=append:/var/lib/lightyear-verify/service.log
"""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Link refused: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path.read_bytes())
    return result


def architecture(machine=None):
    return {"aarch64": "arm64", "x86_64": "x86_64"}[machine or platform.machine()]


def git_output(source, *args):
    # The operator selected this checkout; do not change global Git trust.
    return subprocess.check_output(["git", "-c", f"safe.directory={source.resolve()}", "-C", str(source), *args])


def source_files(source):
    # Tracked public assets only. Excludes work/, archives, keys and arbitrary local data.
    paths = git_output(source, "ls-files", "-z").decode().split("\0")
    chosen = {p for p in paths if p and (p in SINGLE or p.startswith(PREFIXES))}
    # Include this kit during development as well as after publication.
    chosen.update("tools/verify_smoke/" + p.name for p in (source / "tools/verify_smoke").iterdir()
                  if p.suffix in {".py", ".sh"} and p.is_file())
    fixture_names = {n for n in chosen if n.startswith(FIXTURE + "/")}
    if not fixture_names:
        raise ValueError("Public fixture missing from Git")
    for name in fixture_names:
        if (source / name).read_bytes() != git_output(source, "show", f"HEAD:{name}"):
            raise ValueError("Rehearsal fixture differs from the reviewed public commit")
    for name in chosen:
        p = source / name
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"Non-regular public source: {name}")
    return {p: sha((source / p).read_bytes()) for p in sorted(chosen)}


def write_same(path, raw, mode=0o644):
    if path.is_symlink():
        raise ValueError(f"Existing link refused: {path}")
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"Existing file differs; preserve it and investigate: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(raw)
    path.chmod(mode)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def identities():
    import pwd
    import grp
    judge, agent = (pwd.getpwnam(n) for n in ("lyjudge", "lyagent"))
    if judge.pw_uid == agent.pw_uid or min(judge.pw_uid, agent.pw_uid) == 0:
        raise ValueError("Distinct non-root identities required")
    for user in (judge, agent):
        groups = {user.pw_gid, *(g.gr_gid for g in grp.getgrall() if user.pw_name in g.gr_mem)}
        # Fresh dedicated accounts only: no sudo/admin/docker or shared groups.
        if groups != {user.pw_gid} or user.pw_dir != f"/home/{user.pw_name}":
            raise ValueError("Unexpected account home or supplementary group")
        if user.pw_gid == (agent if user == judge else judge).pw_gid:
            raise ValueError("Shared primary group")
        sudo = subprocess.run(["sudo", "-l", "-U", user.pw_name], capture_output=True)
        if sudo.returncode == 0:
            raise ValueError("Account has sudo privileges")
    return judge, agent


def owned_dir(path, user, mode):
    if path.is_symlink():
        raise ValueError("Directory link refused")
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)
    os.chown(path, user.pw_uid, user.pw_gid)


def owned_tree(path, user):
    for p in (path, *path.rglob("*")):
        if p.is_symlink():
            raise ValueError("Tree link refused")
        os.chown(p, user.pw_uid, user.pw_gid)


def public_workspace(source, workspace):
    entries = {}
    for src, name, purpose, extra in (
        ("spec/mainframe/copybooks/CVACT01Y.cpy", "account.cpy", "copybook", {}),
        (FIXTURE + "/before/ACCTFILE.bin", "accounts.bin", "development-records", {"copybook": "account.cpy"}),
        (FIXTURE + "/job-output.txt", "job.txt", "development-log", {}),
    ):
        raw = (source / src).read_bytes()
        write_same(workspace / name, raw)
        entries[name] = {"purpose": purpose, "sha256": sha(raw), **extra}
    write_same(workspace / "public.json", json_bytes({"files": entries}))
    return sha((workspace / "public.json").read_bytes())


def evaluation_copy(source, destination):
    expected = inventory(source / FIXTURE)
    if destination.exists() and any(destination.iterdir()):
        actual = inventory(destination)
        if actual != {Path(FIXTURE).name + "/" + k: v for k, v in expected.items()}:
            raise ValueError("Evaluation must contain exactly the unchanged public run1 fixture")
    else:
        shutil.copytree(source / FIXTURE, destination / Path(FIXTURE).name)
    return inventory(destination)


def install(source):
    judge, agent = identities()
    files = source_files(source)
    marker = STATE / "owner.json"
    if not marker.exists():
        for path in (INSTALL, Path("/opt/lightyear-verify-venv"), PRIVATE, DEV, TOWER):
            if path.exists():
                raise ValueError(f"Dedicated VM required; unmanaged path exists: {path}")
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_same(marker, json_bytes({"source_files": files}), 0o600)
    for name in files:
        write_same(INSTALL / name, (source / name).read_bytes())
    owned_dir(PRIVATE, judge, 0o700)
    owned_dir(PRIVATE / "evaluation", judge, 0o700)
    evaluation_copy(INSTALL, PRIVATE / "evaluation")
    owned_tree(PRIVATE / "evaluation", judge)
    owned_dir(TOWER, judge, 0o755)
    owned_dir(DEV, agent, 0o755)
    manifest_hash = public_workspace(INSTALL, DEV)
    if not (DEV / "candidate-java").exists():
        shutil.copytree(INSTALL / "candidate-java", DEV / "candidate-java")
    owned_tree(DEV, agent)
    config = {
        "task_id": "verify-intcalc", "agent_uid": agent.pw_uid,
        "evaluation": str(PRIVATE / "evaluation"), "exports": str(TOWER / "exports"),
        "tower_workspace": str(TOWER), "submissions": 5, "attempt_slots": 5,
        "fixture": True, "disclosure_mode": "field",
        "public_task": {"source": "CBACT04C", "target": "Java", "shapes": ["ACCTFILE", "TRANSACT"],
                        "development_manifest": "public.json", "development_manifest_sha256": manifest_hash},
    }
    write_same(PRIVATE / "config.json", json_bytes(config), 0o600)
    os.chown(PRIVATE / "config.json", judge.pw_uid, judge.pw_gid)
    write_same(Path("/etc/systemd/system/lightyear-verify-smoke.service"), UNIT.encode())
    # This file contains environment variable NAMES only, never the token.
    write_same(DEV / "codex-mcp.toml", b'''[mcp_servers.lightyear_verify]
command = "/opt/lightyear-verify-venv/bin/lightyear-verify-mcp"
args = ["--workspace", "/srv/dev", "--public-manifest", "/srv/dev/public.json", "--judge-url", "http://127.0.0.1:8770"]
env_vars = ["LIGHTYEAR_VERIFY_TOKEN"]
tool_timeout_sec = 60
''')


def finish(source):
    # Existing acceptance supervisor expects the Maven output in its protected source.
    project = INSTALL / "candidate-java/target"
    for p in (DEV / "candidate-java/target/classes").rglob("*"):
        if p.is_file():
            write_same(project / "classes" / p.relative_to(DEV / "candidate-java/target/classes"), p.read_bytes())
    name = "carddemo-spring-batch-candidate-0.1.0-SNAPSHOT.jar"
    write_same(project / name, (DEV / "candidate-java/target" / name).read_bytes())
    record = {
        "schema": "verify-smoke-setup/1", "recorded_at": datetime.now(timezone.utc).isoformat(),
        "architecture": architecture(), "uname_machine": platform.machine(),
        "kernel": platform.release(), "model_calls": 0, "fixture": True,
        "source_commit": git_output(source, "rev-parse", "HEAD").decode().strip(),
        "source_files": source_files(source), "evaluation": inventory(PRIVATE / "evaluation"),
        "config_sha256": sha((PRIVATE / "config.json").read_bytes()),
        "candidates": json.loads((DEV / "candidates.json").read_bytes()),
        "apparmor_status": json.loads(subprocess.check_output(["aa-status", "--json"])),
        "apparmor_profile_sha256": sha(Path("/etc/apparmor.d/bwrap-userns-restrict").read_bytes()),
        "separation_before_init": "passed; authority key absent; repeated after init",
        "packages": subprocess.check_output(["dpkg-query", "-W", "bubblewrap", "apparmor", "apparmor-profiles",
                                             "openjdk-21-jdk-headless", "python3", "maven"]).decode(),
    }
    write_same(STATE / "setup.json", json_bytes(record), 0o600)


def verify(source=None):
    identities()
    record = json.loads((STATE / "setup.json").read_bytes())
    if record["architecture"] != architecture():
        raise ValueError("Architecture changed")
    if source and source_files(source) != record["source_files"]:
        raise ValueError("Setup source differs; use a new dedicated VM for another revision")
    for name, digest in record["source_files"].items():
        if sha((INSTALL / name).read_bytes()) != digest:
            raise ValueError(f"Installed source changed: {name}")
    if inventory(PRIVATE / "evaluation") != record["evaluation"]:
        raise ValueError("Evaluation changed")
    if sha((PRIVATE / "config.json").read_bytes()) != record["config_sha256"]:
        raise ValueError("Config changed")
    if sha(Path("/etc/apparmor.d/bwrap-userns-restrict").read_bytes()) != record["apparmor_profile_sha256"]:
        raise ValueError("AppArmor profile changed")
    if Path("/etc/systemd/system/lightyear-verify-smoke.service").read_text() != UNIT:
        raise ValueError("Service definition changed")
    config = json.loads((PRIVATE / "config.json").read_bytes())
    if sha((DEV / "public.json").read_bytes()) != config["public_task"]["development_manifest_sha256"]:
        raise ValueError("Public manifest changed")
    print(f"Verified smoke installation ({architecture()}); no state reset.")


if __name__ == "__main__":
    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Linux VM administrator required")
    action = sys.argv[1]
    source = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    {"install": install, "finish": finish, "verify": verify}[action](source)
