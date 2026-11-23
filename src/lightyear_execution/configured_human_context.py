"""Inactive same-process human configured context and scoped host-only lease.

No HMAC authority, passed-receipt constructor, injected secret reader or resume
entry exists. This relies on reviewed Python/workflow/runner code, not Python
object secrecy. No CLI or controller dispatch currently calls the entry. The
sole admission entry would consume a nonce and must not be invoked without
explicit execution authority. A context never qualifies a factory receipt.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
from weakref import WeakKeyDictionary

from lightyear_factory.model_admission import FactoryModelAdmission
from .backend import OCIContainerBackend
from .contracts import ExecutionContractError,ExecutionPolicy,canonical_hash
from .configured_human_admission import verify_configured_human_plan
from .configured_human_runtime import verify_configured_human_runtime
from .configured_human_scopes import reserve_configured_human_plan,verify_configured_human_role
from .configured_human_models import review_configured_human_models
from .configured_human_isolation import review_configured_human_isolation
from .tower_drill_context import _workflow_source

_LIVE=WeakKeyDictionary()


def _preflight(admission,order,policy,backend,source_root,input_paths,manifest,model_path,isolation_path):
    if (type(admission) is not FactoryModelAdmission or type(policy) is not ExecutionPolicy
            or type(backend) is not OCIContainerBackend or backend.execute_enabled is not True
            or backend.policy.to_dict()!=policy.to_dict()):
        raise ExecutionContractError('configured-human-native-context-required')
    if any(part.casefold()=='onedrive' for part in Path(source_root).parts):
        raise ExecutionContractError('configured-human-onedrive-refused')
    review=verify_configured_human_plan(admission,order,policy)
    runtime=verify_configured_human_runtime(admission,order,policy,source_root=source_root,
        input_paths=input_paths,read_manifest=manifest)
    models=review_configured_human_models(admission,order,policy,model_path,
        input_paths=input_paths,read_manifest=manifest)
    values=review_configured_human_isolation(admission,order,policy,manifest,isolation_path)
    workflow=_workflow_source(admission.root,review,os.environ)
    if verify_configured_human_plan(admission,order,policy)!=review:
        raise ExecutionContractError('configured-human-final-preflight-trust-changed')
    return dict(review=review,runtime=runtime,models=models,values=values,workflow=workflow)


def _exclusive_evidence_path(value,root):
    target=Path(value)
    if (not target.is_absolute() or target.exists() or not target.parent.is_dir()
            or target.resolve().is_relative_to(root.resolve())
            or any(part.casefold()=='onedrive' for part in target.parts)):
        raise ExecutionContractError('configured-human-exclusive-external-evidence-required')
    if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (target,*target.parents)):
        raise ExecutionContractError('configured-human-evidence-link')
    return target


def admit_configured_human_context(admission,order,policy,backend,*,source_root,
        input_paths,read_manifest,model_config_path,public_isolation_path,evidence_path):
    bound=_preflight(admission,order,policy,backend,source_root,input_paths,read_manifest,
                     model_config_path,public_isolation_path)
    target=_exclusive_evidence_path(evidence_path,admission.root)
    # All read-only checks precede this irreversible, genuine-proof reservation.
    # No supplied API, consumption record or resume flag is accepted.
    consumption=reserve_configured_human_plan(admission,order,policy)
    record=consumption['record'];review=bound['review'];model=review['verified_model_admission']
    if (consumption['status']!='consumed-only' or record['consumed_before_execution'] is not True
            or record['case_id']!='configured-build-control'
            or record['work_order_sha256']!=order.content_sha256
            or record['execution_policy_sha256']!=policy.content_sha256
            or record['nonce_sha256']!=review['drill_binding']['nonce_sha256']
            or record['plan_sha256']!=model['plan_sha256']
            or record['decision_sha256']!=model['decision_sha256']
            or record['trusted_journal_head']!=model['trusted_journal_head']
            or _preflight(admission,order,policy,backend,source_root,input_paths,read_manifest,
                model_config_path,public_isolation_path)!=bound):
        raise ExecutionContractError('configured-human-post-consumption-stop')
    _exclusive_evidence_path(target,admission.root)
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
    context=object.__new__(ConfiguredHumanExecutionContext)
    context.policy,context.backend=policy,backend
    context.admission_receipt=deepcopy(receipt)
    context._admission,context._order=admission,order
    context._source_root=source_root;context._inputs=deepcopy(input_paths)
    context._manifest=deepcopy(read_manifest);context._model_path=model_config_path
    context._isolation_path=public_isolation_path;context._binding=bound
    context._pid=os.getpid();context._closed=False;context._bound=False
    context._lease_started=False;context._lease_completed=False;context._controller_bound=False
    context.authorization_receipts=[];context.secret_receipts=[];context.execution_evidence=[]
    _LIVE[context]=receipt['content_sha256']
    return context


class ConfiguredHumanExecutionContext:
    def __init__(self,*args,**kwargs):
        raise ExecutionContractError('configured-human-no-receipt-constructor')

    def __repr__(self):return '<ConfiguredHumanExecutionContext>'

    def __copy__(self):
        raise ExecutionContractError('configured-human-context-not-copyable')

    def __deepcopy__(self,memo):
        raise ExecutionContractError('configured-human-context-not-copyable')

    def __reduce__(self):
        raise ExecutionContractError('configured-human-context-not-serializable')

    def _live(self):
        if (type(self) is not ConfiguredHumanExecutionContext or self not in _LIVE
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
            scope=verify_configured_human_role(self._admission,self._order,self.policy,role,action)
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
            scope=verify_configured_human_role(self._admission,self._order,self.policy,
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
            self.secret_receipts.append(receipt);self._lease_completed=True
            return value
        except BaseException:
            self.close()
            raise ExecutionContractError('configured-human-secret-lease-refused') from None

    def public_expected_values(self,order):
        self._live()
        if order is not self._order:
            self.close();raise ExecutionContractError('configured-human-isolation-order')
        return self._binding['values']

    def record_verification(self,report):
        self._live()
        self.execution_evidence.extend(deepcopy(item['execution'])
            for item in report.get('gates',[]) if 'execution' in item)

    def summary(self,required_actions=None):
        self._live()
        result=dict(evidence_class='human-admitted-drill-context',status='incomplete',
            production_ready=False,qualifies_for_factory_receipt=False,
            admission_receipt_sha256=self.admission_receipt['content_sha256'],
            authorization_receipt_sha256=[r['content_sha256'] for r in self.authorization_receipts],
            gate_execution_sha256=[r.get('content_sha256') for r in self.execution_evidence],
            secret_lease_sha256=[r['content_sha256'] for r in self.secret_receipts],
            credentials_issued=False,secrets_leased=self._lease_completed,
            gaps=['configured-controller-terminal-lineage-not-integrated',
                  'physical-send-count-generation-common-binding-unproved',
                  'full-production-build-receipt-route-not-integrated'])
        result['content_sha256']=canonical_hash(result)
        return result

    def close(self):
        self._closed=True
        _LIVE.pop(self,None)
