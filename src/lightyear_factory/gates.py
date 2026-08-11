from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from lightyear_execution.backend import LocalProcessBackend
from lightyear_execution.contracts import canonical_hash

from .contracts import GateContract


MAX_CAPTURE_BYTES = 64 * 1024


class GateRunner:
    """Run deterministic acceptance commands without invoking a shell."""

    def __init__(
        self,
        workspace_root: Path,
        allow_network: bool = False,
        backend: Any | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.allow_network = allow_network
        self.backend = backend or LocalProcessBackend()

    def run(self, gates: tuple[GateContract, ...]) -> dict[str, Any]:
        results = [self._run_one(gate) for gate in gates]
        return {
            "status": "passed" if all(item["status"] == "passed" for item in results) else "failed",
            "gates": results,
        }

    def _run_one(self, gate: GateContract) -> dict[str, Any]:
        environment = dict(os.environ)
        environment["LIGHTYEAR_FACTORY_WORKSPACE"] = str(self.workspace_root)
        environment["LIGHTYEAR_NETWORK_POLICY"] = "allow" if self.allow_network else "deny"
        controller_src = Path(__file__).resolve().parents[1]
        inherited_pythonpath = [
            str(Path(item).resolve())
            for item in environment.get("PYTHONPATH", "").split(os.pathsep)
            if item
        ]
        environment["PYTHONPATH"] = os.pathsep.join(
            dict.fromkeys([str(controller_src), *inherited_pythonpath])
        )
        if not self.allow_network:
            for key in (
                "ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY",
                "all_proxy", "http_proxy", "https_proxy", "ftp_proxy",
            ):
                environment.pop(key, None)
            environment["NO_PROXY"] = "*"
        result = self.backend.execute(
            gate.command, self.workspace_root, environment, gate.timeout_seconds
        )
        exit_code = result.exit_code
        timed_out = result.timed_out
        stdout = result.stdout[-MAX_CAPTURE_BYTES:]
        stderr = result.stderr[-MAX_CAPTURE_BYTES:]
        execution = dict(result.evidence)
        execution["content_sha256"] = canonical_hash(execution)
        return {
            "id": gate.gate_id,
            "status": "passed" if exit_code == 0 and not timed_out else "failed",
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_ms": result.duration_ms,
            "command": list(gate.command),
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "output_sha256": hashlib.sha256(stdout + b"\0" + stderr).hexdigest(),
            "expose_output_to_builder": gate.expose_output_to_builder,
            "execution": execution,
        }


def builder_failure_view(report: dict[str, Any]) -> dict[str, Any]:
    """Remove holdout output before a verification report reaches a builder."""

    gates = []
    for item in report.get("gates", []):
        public = {
            "id": item["id"],
            "status": item["status"],
            "exit_code": item["exit_code"],
            "timed_out": item["timed_out"],
            "output_sha256": item["output_sha256"],
        }
        if item.get("expose_output_to_builder"):
            public["stdout"] = item.get("stdout", "")
            public["stderr"] = item.get("stderr", "")
        gates.append(public)
    return {"status": report.get("status"), "gates": gates}
