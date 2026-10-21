"""Root test supervisor only: copy public code to a protected Linux installation.

Never use root for either service. All judge work runs as UID 1000, MCP as 65534.
The copy avoids Windows-mounted permission semantics; only public fixtures copied.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Run the acceptance supervisor on Linux as root")
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="verify-install-") as scratch:
        target = Path(scratch)
        target.chmod(0o755)
        for folder in ("src", "spec", "tests", "candidate-java"):
            shutil.copytree(
                source / folder,
                target / folder,
                ignore=shutil.ignore_patterns("__pycache__", ".venv", "node_modules"),
            )
        # Only the committed public graph inputs are added. No source evidence
        # or operator files outside these exact public repository paths.
        for name in ("knowledge/graph.snapshot.json.gz",
                     "knowledge/evidence/source.pack.json.gz",
                     "knowledge/ontology/relationships.json",
                     "verify/graph-projection-policy.json"):
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, destination)
        # Fixture modes may inherit Windows 0777. Make the test installation immutable
        # to both unprivileged identities, including all ancestor directory entries.
        for p in target.rglob("*"):
            p.chmod(0o755 if p.is_dir() else 0o644)
        env = {
            **os.environ,
            "PYTHONPATH": str(target / "src") + os.pathsep + str(target),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        # Report only public installation metadata if a hosted image is unsuitable.
        # This runs before creating any private judge session or signing key.
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                """
from lightyear_judge.sandbox import require_trusted_installation
try:
    require_trusted_installation(65534)
except ValueError as exc:
    frame = exc.__traceback__
    while frame.tb_next:
        frame = frame.tb_next
    print('Installation refused:', frame.tb_frame.f_locals.get('p'), flush=True)
    raise
""",
            ],
            cwd=target,
            env=env,
        )
        if probe.returncode:
            return probe.returncode
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_verify_mcp",
                "tests.test_verify_hardening",
                "tests.test_verify_graph_inventory",
                "-v",
            ],
            cwd=target,
            env=env,
        )
        if result.returncode:
            return result.returncode
        if os.environ.get("VERIFY_GRAPH_REPORT_DIR"):
            # Keep the original graph-off flow complete, then run the same full
            # SDK flow with approved graph context and no model client.
            return subprocess.run(
                [sys.executable, "-m", "unittest",
                 "tests.verify_graph_acceptance.GraphOnAcceptance.test_full_sdk_session_and_security", "-v"],
                cwd=target, env=env,
            ).returncode
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
