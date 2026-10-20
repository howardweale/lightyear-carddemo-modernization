from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from lightyear_execution.backend import LocalProcessBackend, OCIContainerBackend
from lightyear_execution.contracts import ExecutionPolicy, canonical_hash

from .contracts import GateContract, ContractError


MAX_CAPTURE_BYTES = 64 * 1024


class CandidateBuildBackend(OCIContainerBackend):
    """Reuse the OCI boundary; build in ephemeral storage inside that container."""

    LAUNCHER = ('mkdir -p /tmp/factory-build; '
                'cp -R /workspace/. /tmp/factory-build/; '
                'cd /tmp/factory-build; exec "$@"')

    def build_invocation(self, command, workspace, environment):
        # The parent validates the requested executable against the approved policy.
        invocation, plan = super().build_invocation(command, workspace, environment)
        image_index = invocation.index(self.policy.image_reference)
        invocation[image_index+1:] = ['/bin/sh', '-ec', self.LAUNCHER, 'factory-build', *plan['command']]
        for index, arg in enumerate(invocation):
            if arg.startswith('PYTHONPATH='):
                invocation[index] = 'PYTHONPATH=/tmp/factory-build/src'
            elif arg.startswith('LIGHTYEAR_FACTORY_WORKSPACE='):
                invocation[index] = 'LIGHTYEAR_FACTORY_WORKSPACE=/tmp/factory-build'
        plan.pop('content_sha256', None)
        plan.update(candidate_build_root='/tmp/factory-build', host_workspace_writable=False,
                    controller_launcher_sha256=hashlib.sha256(self.LAUNCHER.encode()).hexdigest())
        plan['content_sha256'] = canonical_hash(plan)
        return invocation, plan


class GateRunner:
    """Run deterministic acceptance commands without invoking a shell."""

    def __init__(
        self,
        workspace_root: Path,
        allow_network: bool = False,
        backend: Any | None = None,
        require_container: bool = False,
        isolation_scan=None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.allow_network = allow_network
        self.require_container = require_container
        if isolation_scan is not None and not callable(isolation_scan):
            raise ContractError("gate-isolation-scanner-required")
        self.isolation_scan = isolation_scan
        if require_container:
            if allow_network or type(backend) is not OCIContainerBackend or not backend.execute_enabled:
                raise ContractError('isolation-breach: candidate-container-required')
            # Revalidate even a directly constructed policy, before any candidate I/O.
            policy = ExecutionPolicy.from_dict(backend.policy.to_dict())
            self.backend = CandidateBuildBackend(policy, backend.runtime, execute=True)
        else:
            self.backend = backend or LocalProcessBackend()

    def _inspect(self, surface, raw):
        if self.isolation_scan is not None:
            try:
                self.isolation_scan(surface, raw)
            except Exception:
                raise ContractError('gate-isolation-refused') from None

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
        self._inspect('gate-command', json.dumps(list(gate.command), ensure_ascii=False).encode('utf-8'))
        try:
            result = self.backend.execute(
                gate.command, self.workspace_root, environment, gate.timeout_seconds
            )
        except Exception as exc:
            if self.isolation_scan is not None:
                self._inspect('gate-error', str(exc).encode('utf-8'))
                raise ContractError('gate-execution-refused') from None
            raise
        # Inspect complete captured bytes before truncation, decoding, reports or feedback.
        self._inspect('gate-stdout', result.stdout)
        self._inspect('gate-stderr', result.stderr)
        self._inspect('gate-execution-evidence', json.dumps(result.evidence, sort_keys=True,
                      ensure_ascii=False).encode('utf-8'))
        exit_code = result.exit_code
        timed_out = result.timed_out
        stdout = result.stdout[-MAX_CAPTURE_BYTES:]
        stderr = result.stderr[-MAX_CAPTURE_BYTES:]
        execution = dict(result.evidence)
        if self.require_container and (execution.get('enforced') is not True
                or execution.get('assurance') != 'enforced'
                or execution.get('network_mode') != 'none'
                or execution.get('candidate_build_root') != '/tmp/factory-build'
                or execution.get('workspace_read_only') is not True):
            raise ContractError('isolation-breach: candidate-container-evidence')
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


def builder_failure_view(report: dict[str, Any], vocabulary: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Remove holdout output before a verification report reaches a builder."""

    if vocabulary is not None:
        rows=[]
        for item in report.get('differences',[]):
            if type(item.get('interaction')) is not int or item['interaction']<0:
                raise ContractError('feedback-interaction')
            if item.get('screen') not in vocabulary['screens']:raise ContractError('feedback-screen')
            if item.get('category') not in ('value','attribute','cursor','message','db-row','fault'):
                raise ContractError('feedback-category')
            row={key:item[key] for key in ('interaction','screen','category')}
            for key in ('field','table'):
                if key in item:
                    if item[key] not in vocabulary[key+'s']:raise ContractError('feedback-name')
                    row[key]=item[key]
            rows.append(row)
        status=report.get('status')
        if status not in ('passed','failed','not_run'):raise ContractError('feedback-status')
        return dict(status=status,differences=rows)
    gates = []
    for item in report.get("gates", []):
        public = {
            "id": item["id"],
            "status": item["status"],
            "exit_code": item["exit_code"],
            "timed_out": item["timed_out"],
            "output_sha256": item["output_sha256"],
        }
        if item.get("expose_output_to_builder") is True:
            public["stdout"] = item.get("stdout", "")
            public["stderr"] = item.get("stderr", "")
        gates.append(public)
    return {"status": report.get("status"), "gates": gates}
