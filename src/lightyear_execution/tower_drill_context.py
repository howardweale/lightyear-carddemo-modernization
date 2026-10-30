"""Draft same-process continuation of a genuinely human-signed drill admission.

No keys, credentials, signing or reconstruction from a receipt. This relies on
the exact reviewed code and GitHub runner boundary, not Python object secrecy.
The context cannot qualify output: native public-output provenance is separate,
and full build-receipt qualification remains unresolved. Creating a consumption
claim is an irreversible attempt.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from weakref import WeakKeyDictionary

from lightyear_factory.model_admission import FactoryModelAdmission
from lightyear_factory.process_environment import _without_provider_credentials
from .backend import OCIContainerBackend
from .contracts import ExecutionContractError, ExecutionPolicy, canonical_hash
from .tower_drill_admission import verify_human_drill_plan
from .tower_drill_reservation import reserve_human_drill_plan
from .tower_drill_roles import verify_human_drill_role


_LIVE = WeakKeyDictionary()
_REPOSITORY = 'howardweale/lightyear-carddemo-modernization'


def _workflow_source(root, review, environment):
    """Check actual runner-selected workflow bytes against the signed executable.

    Environment provenance depends on the reviewed GitHub workflow/runner;
    this is not independent remote attestation or an execution grant.
    """
    expected = review['drill_binding']['ci']['workflow_ref']
    location, executable = expected.rsplit('@', 1)
    path = location[len(_REPOSITORY)+1:]
    actual = environment.get('GITHUB_WORKFLOW_REF', '')
    revision = environment.get('GITHUB_WORKFLOW_SHA', '')
    if (not location.startswith(_REPOSITORY+'/.github/workflows/')
            or not re.fullmatch(r'\.github/workflows/[A-Za-z0-9_-]+\.yml', path)
            or not re.fullmatch('[0-9a-f]{40}', executable)
            or not actual.startswith(location+'@')
            or not re.fullmatch('[0-9a-f]{40}', revision)):
        raise ExecutionContractError('human-drill-workflow-source-identity')
    def blob(ref):
        return subprocess.check_output(['git','--no-optional-locks','-C',str(root),
            'show',ref+':'+path],stderr=subprocess.DEVNULL,
            env=_without_provider_credentials())
    try:
        signed, running = blob(executable), blob(revision)
    except (OSError,subprocess.CalledProcessError):
        raise ExecutionContractError('human-drill-workflow-source-unavailable') from None
    if not signed or len(signed)>262144 or running!=signed:
        raise ExecutionContractError('human-drill-workflow-source-changed')
    return dict(path=path,signed_executable=executable,workflow_sha=revision,
                workflow_ref=actual,sha256=sha256(signed).hexdigest(),
                trust_boundary='reviewed-github-workflow-and-runner',execution_authorized=False)


def _runtime(admission,order,policy,source_root,input_paths,read_manifest):
    return admission.verify_runtime(order,source_root=source_root,input_paths=input_paths,
                                   policy=policy,read_manifest=read_manifest,
                                   now=datetime.now(timezone.utc))


def admit_human_drill_context(admission,order,policy,backend,*,source_root,
                             input_paths,read_manifest,evidence_path,
                             public_output_plan=None,public_isolation_plan=None):
    if (type(admission) is not FactoryModelAdmission or type(policy) is not ExecutionPolicy
            or type(backend) is not OCIContainerBackend or backend.execute_enabled is not True
            or backend.policy.to_dict()!=policy.to_dict()
            or policy.signature_algorithm!='FACTORY-TOWER-PROOF' or policy.allowed_secret_names):
        raise ExecutionContractError('human-drill-native-public-context-required')
    review=verify_human_drill_plan(admission,order,policy)
    # Validate public-key policy binding through the same genuine role verifier.
    role=next(iter(policy.role_actions))
    verify_human_drill_role(admission,order,policy,role,policy.role_actions[role][0])
    runtime=_runtime(admission,order,policy,source_root,input_paths,read_manifest)
    from .public_drill_outputs import review_public_drill_outputs
    from .human_drill_dispatch import load_public_isolation,validate_public_domain
    validate_public_domain(order,read_manifest,public_output_plan,public_isolation_plan)
    public_outputs=review_public_drill_outputs(admission,order,policy,public_output_plan)
    public_values=load_public_isolation(admission,order,policy,read_manifest,public_isolation_plan)
    workflow=_workflow_source(admission.root,review,os.environ)
    target=Path(evidence_path)
    if not target.is_absolute() or target.exists():
        raise ExecutionContractError('human-drill-exclusive-evidence-path')
    for parent in (target,*target.parents):
        if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)():
            raise ExecutionContractError('human-drill-evidence-link')
    if target.resolve().is_relative_to(admission.root.resolve()) or not target.parent.is_dir():
        raise ExecutionContractError('human-drill-evidence-outside-executable-required')
    # This is the ONLY production consumption entry. No supplied API, receipt,
    # boolean, reverify callback or existing claim can substitute for it.
    consumption=reserve_human_drill_plan(admission,order,policy)
    record=consumption['record']
    if (consumption['status']!='consumed-only' or record['consumed_before_execution'] is not True
            or record['work_order_sha256']!=order.content_sha256
            or record['execution_policy_sha256']!=policy.content_sha256
            or record['nonce_sha256']!=review['drill_binding']['nonce_sha256']
            or record['plan_sha256']!=review['verified_model_admission']['plan_sha256']
            or record['decision_sha256']!=review['verified_model_admission']['decision_sha256']
            or record['trusted_journal_head']!=review['verified_model_admission']['trusted_journal_head']
            or verify_human_drill_plan(admission,order,policy)!=review
            or _runtime(admission,order,policy,source_root,input_paths,read_manifest)!=runtime
            or _workflow_source(admission.root,review,os.environ)!=workflow):
        raise ExecutionContractError('human-drill-post-consumption-stop')
    receipt=dict(schema='factory-human-drill-context-admission/1',status='passed',
        work_order_sha256=order.content_sha256,execution_policy_sha256=policy.content_sha256,
        nonce_sha256=record['nonce_sha256'],decision_sha256=record['decision_sha256'],
        plan_sha256=record['plan_sha256'],trusted_journal_head=record['trusted_journal_head'],
        consumed_ref=consumption['ref'],consumed_tag_object=consumption['tag_object_sha'],
        consumption_record_sha256=record['content_sha256'],ci=deepcopy(record['ci']),
        workflow_source=workflow,stub_only=True,external_model_calls=0,
        runtime_binding_sha256=canonical_hash(runtime),credentials_issued=False,secrets_leased=False,
        output_qualified=False,resume_allowed=False)
    receipt['content_sha256']=canonical_hash(receipt)
    # A write/fsync failure leaves the consumed attempt stopped. No resume API.
    with target.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(receipt,sort_keys=True,separators=(',',':'))+'\n')
        stream.flush();os.fsync(stream.fileno())
    context=object.__new__(HumanDrillExecutionContext)
    context.policy,context.backend=policy,backend
    context.admission_receipt=deepcopy(receipt)
    context._admission,context._order=admission,order
    context._inputs=deepcopy(input_paths);context._manifest=deepcopy(read_manifest)
    context._root=source_root;context._runtime=runtime;context._review=review
    context._workflow=workflow;context._pid=os.getpid();context._bound=False;context._closed=False
    context._public_paths=(public_output_plan,public_isolation_plan)
    context._public_outputs=public_outputs;context._public_values=public_values
    context._controller_bound=False
    context.authorization_receipts=[];context.execution_evidence=[]
    _LIVE[context]=receipt['content_sha256']
    return context


class HumanDrillExecutionContext:
    def __init__(self,*args,**kwargs):
        raise ExecutionContractError('human-drill-no-receipt-constructor')

    def __copy__(self):
        raise ExecutionContractError('human-drill-context-not-copyable')

    def __deepcopy__(self,memo):
        raise ExecutionContractError('human-drill-context-not-copyable')

    def __reduce__(self):
        raise ExecutionContractError('human-drill-context-not-serializable')

    def _live(self):
        if (self not in _LIVE or getattr(self,'_closed',True)
                or getattr(self,'_pid',None)!=os.getpid()
                or canonical_hash(self.admission_receipt,{'content_sha256'})!=_LIVE[self]
                or self.admission_receipt.get('content_sha256')!=_LIVE[self]):
            self.close()
            raise ExecutionContractError('human-drill-fresh-process-context-required')
        try:
            from .public_drill_outputs import review_public_drill_outputs
            from .human_drill_dispatch import load_public_isolation
            if (type(self.backend) is not OCIContainerBackend or self.backend.execute_enabled is not True
                    or self.backend.policy.to_dict()!=self.policy.to_dict()
                    or _runtime(self._admission,self._order,self.policy,self._root,self._inputs,self._manifest)!=self._runtime
                    or verify_human_drill_plan(self._admission,self._order,self.policy)!=self._review
                    or _workflow_source(self._admission.root,self._review,os.environ)!=self._workflow
                    or review_public_drill_outputs(self._admission,self._order,self.policy,self._public_paths[0])!=self._public_outputs
                    or load_public_isolation(self._admission,self._order,self.policy,self._manifest,self._public_paths[1])!=self._public_values):
                raise ExecutionContractError('human-drill-context-binding-changed')
        except BaseException:
            self.close()
            raise

    def bind(self,work_order_sha256,issued_at):
        self._live()
        if self._bound or work_order_sha256!=self._order.content_sha256:
            self.close()
            raise ExecutionContractError('human-drill-context-already-bound-or-wrong-order')
        self._bound=True
        return dict(admission_receipt_sha256=self.admission_receipt['content_sha256'],
                    execution_policy_sha256=self.policy.content_sha256,identity_receipts=[])

    def authorize(self,role,action,now):
        self._live()
        if not self._bound:
            self.close()
            raise ExecutionContractError('human-drill-context-not-bound')
        # Current UTC is obtained inside the verifier; caller timestamps do not
        # extend the human-signed window or freeze a previously valid head.
        try:
            receipt=verify_human_drill_role(self._admission,self._order,self.policy,role,action)
        except BaseException:
            self.close()
            raise
        self.authorization_receipts.append(deepcopy(receipt))
        return receipt

    def lease_secret(self,*args,**kwargs):
        raise ExecutionContractError('human-drill-secrets-forbidden')

    def public_expected_values(self,order):
        self._live()
        if order is not self._order:raise ExecutionContractError('human-drill-expected-order')
        return self._public_values

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
            credentials_issued=False,secrets_leased=False,
            gaps=['full-production-build-receipt-route-not-integrated']+
                ([] if self._controller_bound else ['native-controller-public-trace-not-bound']))
        result['content_sha256']=canonical_hash(result)
        return result

    def close(self):
        self._closed=True
        _LIVE.pop(self,None)
