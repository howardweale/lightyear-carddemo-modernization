"""Native gate execution with exact receipt policy and original report capture."""
from pathlib import Path
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_factory.gates import GateRunner,CandidateBuildBackend
from .backend import OCIContainerBackend
from .configured_receipt_policy import parse_configured_receipt_policy


class ReceiptGateRunner(GateRunner):
    def __init__(self,workspace,backend,scanner):
        if (type(backend) is not OCIContainerBackend or backend.execute_enabled is not True
                or not callable(scanner)):
            raise ContractError('configured-gate-native-container-required')
        policy=parse_configured_receipt_policy(backend.policy.to_dict())
        self.workspace_root=Path(workspace).resolve();self.allow_network=False
        self.require_container=True;self.isolation_scan=scanner
        self.backend=CandidateBuildBackend(policy,backend.runtime,execute=True)


def _native_runner(runner,context,workspace,scanner):
    if (type(runner) is not ReceiptGateRunner or type(runner.backend) is not CandidateBuildBackend
            or runner.workspace_root!=workspace.root or runner.isolation_scan is not scanner
            or runner.backend.policy.to_dict()!=context.policy.to_dict()
            or runner.backend.runtime!=context.backend.runtime or runner.backend.execute_enabled is not True
            or runner.allow_network is not False or runner.require_container is not True
            or getattr(runner.run,'__func__',None) is not GateRunner.run
            or getattr(runner._run_one,'__func__',None) is not GateRunner._run_one
            or getattr(runner.backend.execute,'__func__',None) is not OCIContainerBackend.execute
            or getattr(runner.backend.build_invocation,'__func__',None) is not CandidateBuildBackend.build_invocation):
        raise ContractError('configured-gate-original-native-runner-required')


def run_original_receipt_gates(controller,workspace,order):
    from .configured_receipt_controller import verify_configured_controller,_CONTROLLERS
    from .configured_receipt_terminal import _require_origin
    from .configured_receipt_security import _PENDING
    verify_configured_controller(controller,order);_require_origin(controller)
    context=controller.execution_context;saved=_CONTROLLERS[context]
    if (saved['workspace'] is not workspace or order is not context._order
            or order.allow_network is not False or context in _PENDING):
        raise ContractError('configured-gate-original-workspace-required')
    scanner=controller._isolation_scanner()
    runner=ReceiptGateRunner(workspace.root,context.backend,scanner)
    _native_runner(runner,context,workspace,scanner)
    report=runner.run(order.gates)
    _native_runner(runner,context,workspace,scanner)
    verify_configured_controller(controller,order);_require_origin(controller)
    if ([row['id'] for row in report['gates']]!=[gate.gate_id for gate in order.gates]
            or [row['command'] for row in report['gates']]!=[list(gate.command) for gate in order.gates]):
        raise ContractError('configured-gate-original-contract-required')
    _PENDING[context]=(report,canonical_hash(report))
    return report
