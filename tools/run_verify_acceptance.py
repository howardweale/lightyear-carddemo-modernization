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
        # Fixture modes may inherit Windows 0777. Make the test installation immutable
        # to both unprivileged identities, including all ancestor directory entries.
        for p in target.rglob("*"):
            p.chmod(0o755 if p.is_dir() else 0o644)
        env = {
            **os.environ,
            "PYTHONPATH": str(target / "src"),
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
                "-v",
            ],
            cwd=target,
            env=env,
        )
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
