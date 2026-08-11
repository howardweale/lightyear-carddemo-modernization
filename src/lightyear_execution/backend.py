from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import ExecutionContractError, ExecutionPolicy, canonical_hash


MAX_CAPTURE_BYTES = 64 * 1024


@dataclass(frozen=True)
class ExecutionResult:
    exit_code: int | None
    timed_out: bool
    duration_ms: int
    stdout: bytes
    stderr: bytes
    evidence: dict[str, Any]


class LocalProcessBackend:
    """Compatibility backend. It is explicitly advisory, never hardened evidence."""

    backend_id = "host-process"
    assurance = "advisory"

    def execute(
        self, command: tuple[str, ...], workspace: Path, environment: dict[str, str], timeout: int
    ) -> ExecutionResult:
        started = time.monotonic()
        timed_out = False
        try:
            completed = subprocess.run(
                list(command), cwd=workspace, env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False,
            )
            exit_code = completed.returncode
            stdout = completed.stdout[-MAX_CAPTURE_BYTES:]
            stderr = completed.stderr[-MAX_CAPTURE_BYTES:]
        except subprocess.TimeoutExpired as error:
            timed_out = True
            exit_code = None
            stdout = (error.stdout or b"")[-MAX_CAPTURE_BYTES:]
            stderr = (error.stderr or b"")[-MAX_CAPTURE_BYTES:]
        return ExecutionResult(
            exit_code, timed_out, round((time.monotonic() - started) * 1000), stdout, stderr,
            {"backend": self.backend_id, "assurance": self.assurance, "enforced": False},
        )


class OCIContainerBackend:
    """Docker/Podman backend with a digest-pinned, non-root, networkless sandbox."""

    assurance = "enforced"

    def __init__(self, policy: ExecutionPolicy, runtime: str, execute: bool = True) -> None:
        if runtime not in policy.runtimes:
            raise ExecutionContractError("OCI runtime is not allowed by execution policy")
        self.policy = policy
        self.runtime = runtime
        self.execute_enabled = execute
        self.backend_id = f"oci-{runtime}"

    def build_invocation(
        self,
        command: tuple[str, ...],
        workspace: Path,
        environment: dict[str, str],
    ) -> tuple[list[str], dict[str, Any]]:
        executable = Path(command[0]).name
        if executable.startswith("python"):
            executable = "python3"
        if executable not in self.policy.allowed_commands:
            raise ExecutionContractError(f"Command is not allowed in hardened container: {executable}")
        normalized_command = [executable, *command[1:]]
        if any("\x00" in item for item in normalized_command):
            raise ExecutionContractError("Container command contains a null byte")
        allowed_env = {
            key: value for key, value in environment.items()
            if key in self.policy.allowed_environment
        }
        if "PYTHONPATH" in allowed_env:
            allowed_env["PYTHONPATH"] = "/workspace/src"
        if "LIGHTYEAR_FACTORY_WORKSPACE" in allowed_env:
            allowed_env["LIGHTYEAR_FACTORY_WORKSPACE"] = "/workspace"
        invocation = [
            self.runtime, "run", "--rm", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--pids-limit", str(self.policy.pids_limit),
            "--memory", f"{self.policy.memory_mb}m",
            "--cpus", str(self.policy.cpus),
            "--user", self.policy.run_as_user,
            "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={self.policy.tmpfs_mb}m",
            "--mount", f"type=bind,src={workspace.resolve()},dst=/workspace,readonly",
            "--workdir", "/workspace",
        ]
        for key in sorted(allowed_env):
            invocation.extend(["--env", f"{key}={allowed_env[key]}"])
        invocation.extend([self.policy.image_reference, *normalized_command])
        plan = {
            "backend": self.backend_id,
            "assurance": self.assurance,
            "image": self.policy.image_reference,
            "network_mode": "none",
            "read_only_root": True,
            "workspace_read_only": True,
            "run_as_user": self.policy.run_as_user,
            "cap_drop_all": True,
            "no_new_privileges": True,
            "pids_limit": self.policy.pids_limit,
            "memory_mb": self.policy.memory_mb,
            "cpus": self.policy.cpus,
            "tmpfs_mb": self.policy.tmpfs_mb,
            "environment_names": sorted(allowed_env),
            "command": normalized_command,
        }
        plan["content_sha256"] = canonical_hash(plan)
        return invocation, plan

    def execute(
        self, command: tuple[str, ...], workspace: Path, environment: dict[str, str], timeout: int
    ) -> ExecutionResult:
        invocation, plan = self.build_invocation(command, workspace, environment)
        if not self.execute_enabled:
            return ExecutionResult(
                0, False, 0, b"OCI policy conformance simulated; command was not executed.\n", b"",
                {**plan, "assurance": "simulated", "enforced": False},
            )
        runtime_path = shutil.which(self.runtime)
        if runtime_path is None:
            raise ExecutionContractError(f"Required OCI runtime is unavailable: {self.runtime}")
        invocation[0] = runtime_path
        started = time.monotonic()
        timed_out = False
        try:
            completed = subprocess.run(
                invocation, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=timeout, check=False,
                env={"PATH": os.environ.get("PATH", "")},
            )
            exit_code = completed.returncode
            stdout = completed.stdout[-MAX_CAPTURE_BYTES:]
            stderr = completed.stderr[-MAX_CAPTURE_BYTES:]
        except subprocess.TimeoutExpired as error:
            timed_out = True
            exit_code = None
            stdout = (error.stdout or b"")[-MAX_CAPTURE_BYTES:]
            stderr = (error.stderr or b"")[-MAX_CAPTURE_BYTES:]
        runtime_binary_sha256 = hashlib.sha256(Path(runtime_path).read_bytes()).hexdigest()
        evidence = {
            **plan,
            "runtime_binary_sha256": runtime_binary_sha256,
            "enforced": True,
        }
        return ExecutionResult(
            exit_code, timed_out, round((time.monotonic() - started) * 1000),
            stdout, stderr, evidence,
        )
