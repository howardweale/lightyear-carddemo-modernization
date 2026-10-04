"""Single-use private evaluator process. Never a model or agent entry point."""

import sys
from pathlib import Path
from lightyear_control_tower.decisions import verify_envelope
from lightyear_control_tower.status_export import atomic_new
from lightyear_mainframe.zos_evidence import Signer, read_json
from .evaluation import evaluate
from .policy import fingerprint


def main(root, attempt_id):
    import ctypes
    import os
    import signal

    # A service crash must not leave a private evaluator running behind a new service.
    parent = os.getppid()
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise ValueError("worker-parent-lifetime-unavailable")
    if parent == 1 or os.getppid() != parent:
        raise ValueError("worker-parent-exited")
    root = Path(root)
    signer = Signer(root / "authority.pem")
    config = read_json(root / "task.json")
    if (
        not verify_envelope(config, signer.public)
        or config["implementation"] != fingerprint()
    ):
        raise ValueError("worker-binding-failed")
    # ARRIVALS is process-local: another task or an HTTP thread cannot change it.
    verdict, diagnostics, runs = evaluate(
        root,
        config["evaluation"],
        root / "artifacts" / (attempt_id + ".jar"),
        signer,
        review_root=config["tower_workspace"],
    )
    if config["implementation"] != fingerprint():
        raise ValueError("worker-implementation-changed")
    atomic_new(
        root / "worker-results" / (attempt_id + ".json"),
        signer.sign(
            dict(
                task=config["content_sha256"],
                attempt_id=attempt_id,
                verdict=verdict,
                diagnostics=diagnostics,
                runs=runs,
            )
        ),
    )


if __name__ == "__main__":
    main(*sys.argv[1:])
