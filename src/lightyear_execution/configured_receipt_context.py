"""Separate genuine main receipt context and one-use host broker proposal.

The existing exact context class serves the two fixed native case routes.
No publication/execution/nonce/secret authority is implied by this source.
SSH signer files require separate external provisioning; closing this context
revokes its live authority but makes no Python-memory zeroization claim.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
from weakref import WeakKeyDictionary

from lightyear_factory.model_admission import FactoryModelAdmission
from .backend import OCIContainerBackend
from .contracts import ExecutionContractError,ExecutionPolicy,canonical_hash
from .configured_receipt_admission import verify_configured_receipt_plan
from .configured_receipt_runtime import verify_configured_receipt_runtime
from .configured_receipt_scopes import verify_configured_receipt_role
from .configured_receipt_main import reserve_configured_receipt_main_plan,review_configured_receipt_main_identity
from .configured_receipt_materials import review_receipt_public_materials
from .configured_receipt_policy import TRANSPORT_SECRET
from .configured_receipt_models import review_configured_receipt_models
from .configured_receipt_isolation import review_configured_receipt_isolation
from .tower_drill_context import _workflow_source
from .configured_receipt_case import is_answer_order,review_case,reservation_entry,consumption_tools,role_verifier

_LIVE=WeakKeyDictionary()

def _decode_transport_key(value):
    # Canonical base64 of externally provisioned 32 bytes; no derivation or
    # generation. Do not include supplied material in errors or diagnostics.
    import base64,binascii
    try:
        if type(value) is not str or len(value)!=44:raise ValueError()
        raw=base64.b64decode(value,validate=True)
        if len(raw)!=32 or base64.b64encode(raw).decode('ascii')!=value:raise ValueError()
        return raw
    except (ValueError,UnicodeError,binascii.Error):
        raise ExecutionContractError('configured-receipt-transport-material-invalid') from None




def _preflight(admission,order,policy,backend,source_root,input_paths,manifest,model_path,isolation_path):
    if (type(admission) is not FactoryModelAdmission or type(policy) is not ExecutionPolicy
            or type(backend) is not OCIContainerBackend or backend.execute_enabled is not True
            or backend.policy.to_dict()!=policy.to_dict()):
        raise ExecutionContractError('configured-human-native-context-required')
    if any(part.casefold()=='onedrive' for part in Path(source_root).parts):
        raise ExecutionContractError('configured-human-onedrive-refused')
    if is_answer_order(order):
        from .configured_receipt_answer_preflight import review_answer_receipt_preflight
        return review_answer_receipt_preflight(admission,order,policy,backend,source_root,
            input_paths,manifest,model_path,isolation_path)
    review=verify_configured_receipt_plan(admission,order,policy)
    runtime=verify_configured_receipt_runtime(admission,order,policy,source_root=source_root,
        input_paths=input_paths,read_manifest=manifest)
    models=review_configured_receipt_models(admission,order,policy,model_path,
        input_paths=input_paths,read_manifest=manifest)
    values=review_configured_receipt_isolation(admission,order,policy,manifest,isolation_path)
    workflow=_workflow_source(admission.root,review,os.environ)
    public_materials=review_receipt_public_materials(admission,order,policy,manifest)
    main=review_configured_receipt_main_identity(admission,order,policy)
    if verify_configured_receipt_plan(admission,order,policy)!=review:
        raise ExecutionContractError('configured-human-final-preflight-trust-changed')
    return dict(review=review,runtime=runtime,models=models,values=values,workflow=workflow,main=main,public_materials=public_materials)


def _exclusive_evidence_path(value,root):
    target=Path(value)
    if (not target.is_absolute() or target.exists() or not target.parent.is_dir()
            or target.resolve().is_relative_to(root.resolve())
            or any(part.casefold()=='onedrive' for part in target.parts)):
        raise ExecutionContractError('configured-human-exclusive-external-evidence-required')
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (target,*target.parents)):
        raise ExecutionContractError('configured-human-evidence-link')
    return target


def admit_configured_receipt_context(admission,order,policy,backend,*,source_root,
        input_paths,read_manifest,model_config_path,public_isolation_path,evidence_path):
    bound=_preflight(admission,order,policy,backend,source_root,input_paths,read_manifest,
                     model_config_path,public_isolation_path)
    case=review_case(bound['review'])
    target=_exclusive_evidence_path(evidence_path,admission.root)
    retained=_exclusive_evidence_path(target.parent/'human-consumption.json',admission.root)
    if retained==target:
        raise ExecutionContractError('configured-human-evidence-path-collision')
    # All read-only checks precede this irreversible, genuine-proof reservation.
    # No supplied API, consumption record or resume flag is accepted.
    consumption=reservation_entry(case)(admission,order,policy)
    record=consumption['record'];review=bound['review'];model=review['verified_model_admission']
    if (consumption['status']!='consumed-only' or record['consumed_before_execution'] is not True
            or record['case_id']!=case
            or record['work_order_sha256']!=order.content_sha256
            or record['execution_policy_sha256']!=policy.content_sha256
            or record['nonce_sha256']!=review['drill_binding']['nonce_sha256']
            or record['plan_sha256']!=model['plan_sha256']
            or record['decision_sha256']!=model['decision_sha256']
            or record['trusted_journal_head']!=model['trusted_journal_head']):
        raise ExecutionContractError('configured-human-post-consumption-stop')
    _exclusive_evidence_path(target,admission.root)
    _exclusive_evidence_path(retained,admission.root)
    # Same serialization as the original annotated tag message, with no newline.
    # Preserve the native returned record before any admission/context can exist.
    # A failure after consumption never retries, removes or resumes the nonce.
    consumption_message_bytes,_,_=consumption_tools(case)
    message=consumption_message_bytes(record)
    with retained.open('xb') as stream:
        stream.write(message);stream.flush();os.fsync(stream.fileno())
    # Retain a successfully returned original consumption before proof re-entry.
    # Expiry or changed trust here stops admission but must not erase this record.
    # Failures inside the reservation before its return still need remote recovery
    # evidence; this ordering does not establish crash survival or retry authority.
    if _preflight(admission,order,policy,backend,source_root,input_paths,read_manifest,
            model_config_path,public_isolation_path)!=bound:
        raise ExecutionContractError('configured-human-post-consumption-stop')
    receipt=dict(schema='factory-human-drill-context-admission/1',status='passed',
        work_order_sha256=order.content_sha256,execution_policy_sha256=policy.content_sha256,
        nonce_sha256=record['nonce_sha256'],decision_sha256=record['decision_sha256'],
        plan_sha256=record['plan_sha256'],trusted_journal_head=record['trusted_journal_head'],
        consumed_ref=consumption['ref'],consumed_tag_object=consumption['tag_object_sha'],
        consumption_record_sha256=record['content_sha256'],ci=deepcopy(record['ci']),
        workflow_source=deepcopy(bound['workflow']),stub_only=False,
        external_model_calls=review['drill_binding']['external_model_calls'],
        runtime_binding_sha256=canonical_hash(bound['runtime']),credentials_issued=False,
        secrets_leased=False,output_qualified=False,resume_allowed=False)
    # external_model_calls retains the signed allowance, never an observed call
    # count; actual sends/count charges must come from original transport journals.
    receipt['content_sha256']=canonical_hash(receipt)
    with target.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(receipt,sort_keys=True,separators=(',',':'))+'\n')
        stream.flush();os.fsync(stream.fileno())
    context=object.__new__(ConfiguredReceiptExecutionContext)
    context.policy,context.backend=policy,backend
    context.admission_receipt=deepcopy(receipt)
    context._admission,context._order=admission,order
    context._source_root=source_root;context._inputs=deepcopy(input_paths)
    context._manifest=deepcopy(read_manifest);context._model_path=model_config_path
    context._isolation_path=public_isolation_path;context._binding=bound
    context._pid=os.getpid();context._closed=False;context._bound=False
    context._lease_started=False;context._lease_completed=False;context._controller_bound=False
    context._transport_lease_started=False;context._transport_lease_completed=False
    context.authorization_receipts=[];context.secret_receipts=[];context.execution_evidence=[]
    _LIVE[context]=receipt['content_sha256']
    return context


class ConfiguredReceiptExecutionContext:
    def __init__(self,*args,**kwargs):
        raise ExecutionContractError('configured-human-no-receipt-constructor')

    def __repr__(self):return '<ConfiguredReceiptExecutionContext>'

    def __copy__(self):
        raise ExecutionContractError('configured-human-context-not-copyable')

    def __deepcopy__(self,memo):
        raise ExecutionContractError('configured-human-context-not-copyable')

    def __reduce__(self):
        raise ExecutionContractError('configured-human-context-not-serializable')

    def _live(self):
        if (type(self) is not ConfiguredReceiptExecutionContext or self not in _LIVE
                or getattr(self,'_closed',True) or getattr(self,'_pid',None)!=os.getpid()
                or canonical_hash(self.admission_receipt,{'content_sha256'})!=_LIVE[self]
                or self.admission_receipt.get('content_sha256')!=_LIVE[self]):
            self.close()
            raise ExecutionContractError('configured-human-fresh-process-context-required')
        try:
            current=_preflight(self._admission,self._order,self.policy,self.backend,self._source_root,
                self._inputs,self._manifest,self._model_path,self._isolation_path)
            if current!=self._binding:
                raise ExecutionContractError('configured-human-context-binding-changed')
        except BaseException:
            self.close();raise

    def bind(self,work_order_sha256,issued_at):
        self._live()
        if self._bound or work_order_sha256!=self._order.content_sha256:
            self.close();raise ExecutionContractError('configured-human-wrong-order-or-rebind')
        self._bound=True
        return dict(admission_receipt_sha256=self.admission_receipt['content_sha256'],
                    execution_policy_sha256=self.policy.content_sha256,identity_receipts=[])

    def authorize(self,role,action,now):
        self._live()
        if not self._bound or not self._controller_bound:
            self.close();raise ExecutionContractError('configured-human-controller-not-bound')
        try:
            scope=role_verifier(self._order)(self._admission,self._order,self.policy,role,action)
            from .configured_receipt_security import observe_authorization
            observe_authorization(self,scope)
            self.authorization_receipts.append(deepcopy(scope));return scope
        except BaseException:
            self.close();raise

    def lease_secret(self,role,name,now):
        # Provider construction precedes controller.bind, but the immutable
        # work-order/proof/consumption binding already exists in this process.
        # Supplied time is ignored; genuine role verification uses current UTC.
        self._live()
        if role!='provider' or name!='OPENAI_API_KEY' or self._lease_started:
            self.close();raise ExecutionContractError('configured-human-secret-scope-or-reuse')
        self._lease_started=True
        try:
            scope=role_verifier(self._order)(self._admission,self._order,self.policy,
                                               'provider','secret:lease:OPENAI_API_KEY')
            self._live()
            value=os.environ.get('OPENAI_API_KEY','')
            if type(value) is not str or not value:
                raise ExecutionContractError('configured-human-secret-unavailable')
            # Never hash, store or emit credential material in the receipt.
            self._live()
            receipt=dict(name=name,role=role,work_order_sha256=self._order.content_sha256,
                execution_policy_sha256=self.policy.content_sha256,
                admission_receipt_sha256=self.admission_receipt['content_sha256'],
                role_scope_sha256=scope['content_sha256'],one_use=True,persisted=False)
            receipt['content_sha256']=canonical_hash(receipt)
            from .configured_receipt_security import observe_lease
            observe_lease(self,scope,receipt)
            self.secret_receipts.append(receipt);self._lease_completed=True
            return value
        except BaseException:
            self.close()
            raise ExecutionContractError('configured-human-secret-lease-refused') from None

    def lease_transport_key(self,controller,workspace,artifacts,ledger,run_dir):
        # Finalization owns this one-use lease. No API for arbitrary role/name,
        # caller key bytes, secret reader, timestamp or returned receipt exists.
        self._live()
        try:
            from lightyear_factory.orchestrator import FactoryOrchestrator,ArtifactStore
            from lightyear_factory.workspace import IsolatedWorkspace
            from .configured_receipt_controller import _CONTROLLERS
            from .configured_human_lifecycle import original_scanner_relations
            saved=_CONTROLLERS.get(self)
            if (type(controller) is not FactoryOrchestrator or controller.execution_context is not self
                    or saved is None or saved['controller'] is not controller or saved['ledger'] is not ledger
                    or saved['run_dir']!=Path(run_dir) or saved.get('finalized') is not False
                    or not self._bound or self._controller_bound or self._transport_lease_started
                    or type(workspace) is not IsolatedWorkspace or type(artifacts) is not ArtifactStore
                    or workspace.root!=(Path(run_dir)/'workspace').resolve()
                    or workspace.source_root!=Path(self._source_root).resolve()
                    or workspace.read_manifest!=self._manifest
                    or artifacts.root!=Path(run_dir)/'artifacts' or artifacts.run_id!=Path(run_dir).name
                    or artifacts.sequence!=0):
                raise ExecutionContractError('configured-receipt-original-key-owner-required')
            original_scanner_relations(controller,self._order,workspace,ledger,controller.agents.isolation_scan)
            self._transport_lease_started=True
            scope=role_verifier(self._order)(self._admission,self._order,self.policy,
                'recorder','secret:lease:FACTORY_TRANSPORT_KEY')
            self._live()
            value=_decode_transport_key(os.environ.get(TRANSPORT_SECRET,''))
            self._live()
            receipt=dict(name=TRANSPORT_SECRET,role='recorder',work_order_sha256=self._order.content_sha256,
                execution_policy_sha256=self.policy.content_sha256,
                admission_receipt_sha256=self.admission_receipt['content_sha256'],
                role_scope_sha256=scope['content_sha256'],one_use=True,persisted=False)
            receipt['content_sha256']=canonical_hash(receipt)
            from .configured_receipt_security import observe_lease
            observe_lease(self,scope,receipt)
            self.secret_receipts.append(receipt);self._transport_lease_completed=True
            return value,self._binding['public_materials']['key_id']
        except BaseException:
            self.close()
            raise ExecutionContractError('configured-receipt-transport-lease-refused') from None

    def public_expected_values(self,order):
        self._live()
        if order is not self._order:
            self.close();raise ExecutionContractError('configured-human-isolation-order')
        return self._binding['values']

    def record_verification(self,report):
        from .configured_receipt_security import accept_original_gate_report
        self.execution_evidence.extend(accept_original_gate_report(self,report))

    def summary(self,required_actions=None):
        from .configured_receipt_security import receipt_security_summary
        return receipt_security_summary(self,required_actions)

    def close(self):
        self._closed=True
        _LIVE.pop(self,None)
