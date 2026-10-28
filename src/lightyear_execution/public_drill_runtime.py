"""Native controller-bound public stub trace. No keys, network or signatures."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path

from lightyear_factory.contracts import ContractError, canonical_hash
from lightyear_factory.ledger import RunLedger
from lightyear_factory.model_admission import _bounded_regular_bytes
from lightyear_factory.providers import ProviderResult, _validate_schema
from .tower_drill_context import HumanDrillExecutionContext
from .public_drill_outputs import validate_public_output_plan


def _bytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def match_invocation(step,sequence,role,instruction,payload,schema):
    invocation=dict(instruction=instruction,payload=payload,schema=schema)
    if (type(sequence) is not int or sequence!=step['sequence'] or role!=step['role']
            or canonical_hash(invocation)!=step['invocation_sha256']
            or canonical_hash(schema)!=step['schema_sha256']):
        raise ContractError('public-drill-unapproved-invocation')
    return invocation


def artifact_bytes(run_dir,reference,sequence,kind):
    expected=f'public-drill/{sequence:04d}-{kind}.json'
    if (type(reference) is not dict or set(reference)!={'path','sha256','bytes'}
            or reference['path']!=expected or type(reference['bytes']) is not int
            or not 0<reference['bytes']<=1024*1024):
        raise ContractError('public-drill-artifact-reference')
    raw=_bounded_regular_bytes(Path(run_dir)/expected,1024*1024,'public-drill-artifact-file')
    if len(raw)!=reference['bytes'] or sha256(raw).hexdigest()!=reference['sha256']:
        raise ContractError('public-drill-artifact-digest')
    return raw


def verify_recorded_trace(script,events,accounting,authorizations,calls,run_dir,admission):
    """Check retained relations only. This helper cannot establish execution origin."""
    bindings=[e for e in events if e['kind']=='public_drill_controller_bound']
    expected=dict(output_plan_sha256=script['content_sha256'],
        admission_receipt_sha256=admission['content_sha256'],
        work_order_sha256=admission['work_order_sha256'],provider='p5-scripted',model=script['model'])
    if len(bindings)!=1 or _bytes(bindings[0]['payload'])!=_bytes(expected):
        raise ContractError('public-drill-provenance-controller-binding')
    starts=[e for e in events if e['kind']=='public_drill_call_started']
    ends=[e for e in events if e['kind']=='public_drill_call_finished']
    if not len(ends)<=len(starts)<=len(ends)+1 or len(starts)>len(script['steps']):
        raise ContractError('public-drill-provenance-count')
    reservations={e['event_sha256']:e for e in accounting if e['kind']=='reserved'}
    auth={a['content_sha256']:a for a in authorizations}
    prior=bindings[0]['sequence']
    for index,start in enumerate(starts,1):
        step=script['steps'][index-1];payload=start['payload']
        req=json.loads(artifact_bytes(run_dir,payload['request'],index,'request'))
        if type(req) is not dict or set(req)!={'instruction','payload','schema'}:
            raise ContractError('public-drill-provenance-request-shape')
        match_invocation(step,index,payload['role'],req['instruction'],req['payload'],req['schema'])
        reserved=reservations.get(payload['logical_reservation_event_sha256'])
        role=step['role']
        action={'planner':'factory:plan','builder':'factory:build','failure_analyst':'factory:analyze-failure'}[role]
        authorization=auth.get(payload['authorization_sha256'])
        if (type(payload['sequence']) is not int or payload['sequence']!=index
                or payload['invocation_sha256']!=step['invocation_sha256']
                or payload['schema_sha256']!=step['schema_sha256']
                or payload['output_plan_sha256']!=script['content_sha256']
                or start['sequence']<=prior or reserved is None or authorization is None):
            raise ContractError('public-drill-provenance-start-binding')
        reservation=reserved['payload']['reservation']
        if (reservation['invocation_sha256']!=step['invocation_sha256']
                or reservation['request_sha256']!=step['invocation_sha256']
                or type(reservation['call_sequence']) is not int or reservation['call_sequence']!=index
                or reservation['role']!=step['role']
                or authorization['content_sha256']!=canonical_hash(authorization,{'content_sha256'})
                or authorization['role']!=role or authorization['action']!=action
                or authorization['work_order_sha256']!=admission['work_order_sha256']
                or any(authorization[k]!=admission[k] for k in
                    ('execution_policy_sha256','plan_sha256','decision_sha256','trusted_journal_head','nonce_sha256'))):
            raise ContractError('public-drill-provenance-reservation-or-role')
        prior=start['sequence']
        if index>len(ends):continue
        end=ends[index-1];p=end['payload']
        response=json.loads(artifact_bytes(run_dir,p['response'],index,'response'))
        if index>len(calls):raise ContractError('public-drill-provenance-accounting-missing')
        call=calls[index-1]
        expected_ref=dict(start_event_sha256=start['event_sha256'],end_event_sha256=end['event_sha256'],
                          output_plan_sha256=script['content_sha256'])
        if (p['start_event_sha256']!=start['event_sha256'] or end['sequence']<=prior
                or type(p['sequence']) is not int or p['sequence']!=index or p['role']!=step['role']
                or p['response_sha256']!=step['response_sha256']
                or canonical_hash({'content':response})!=step['response_sha256']
                or call.get('public_drill_record')!=expected_ref
                or call.get('content_sha256')!=canonical_hash(call,{'content_sha256'})
                or call.get('request_sha256')!=step['invocation_sha256']
                or call.get('response_sha256')!=step['response_sha256']
                or call.get('provider')!='p5-scripted' or call.get('model')!=script['model']
                or call.get('role')!=step['role'] or type(call.get('call_sequence')) is not int
                or call['call_sequence']!=index):
            raise ContractError('public-drill-provenance-content-or-accounting')
        prior=end['sequence']
    # A refused call may have a reserved-charge record but no completed output.
    # Never drop it or turn it into a successful expected-output observation.
    if not len(ends)<=len(calls)<=len(ends)+1:
        raise ContractError('public-drill-provenance-accounting-count')
    for call in calls[len(ends):]:
        if (call.get('status')!='failed' or call.get('usage')!='reserved-upper-bound'
                or call.get('content_sha256')!=canonical_hash(call,{'content_sha256'})
                or call.get('provider')!='p5-scripted' or call.get('model')!=script['model']
                or type(call.get('call_sequence')) is not int or call['call_sequence']!=len(ends)+1):
            raise ContractError('public-drill-provenance-unmatched-call')
    complete=len(starts)==len(ends)==len(calls)==len(script['steps'])
    return dict(output_plan_complete=complete,completed_public_calls=len(ends),
                unfinished_public_calls=len(starts)-len(ends),accounted_calls=len(calls),
                controller_origin_verified=False)


def verify_receipt_tail(receipt,summary,events):
    """The native receipt pins its snapshot; final scans follow that snapshot."""
    heads=[i for i,e in enumerate(events) if e['event_sha256']==receipt.get('ledger_head_sha256')]
    if len(heads)!=1:raise ContractError('public-drill-receipt-snapshot-missing')
    index=heads[0];tail=events[index+1:]
    if not tail:return index+1
    before={k:v for k,v in receipt.items() if k!='content_sha256'}
    expected=[('run-receipt-before-memory',before),('run-receipt',receipt),('run-summary',summary)]
    if len(tail)!=len(expected):raise ContractError('public-drill-unexpected-receipt-tail')
    for event,(name,value) in zip(tail,expected):
        raw=json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')
        payload=event['payload']
        if (event['kind']!='model_isolation_scan_passed' or payload.get('status')!='passed'
                or payload.get('scanned')!=[dict(artifact=name,sha256=sha256(raw).hexdigest())]):
            raise ContractError('public-drill-unexpected-receipt-tail')
    return index+1


class PublicDrillProvider:
    provider_id='p5-scripted'
    manage_failure_budget=True
    input_usd_per_million=0.0
    output_usd_per_million=0.0
    max_output_tokens=0

    def __init__(self,context,script):
        if type(context) is not HumanDrillExecutionContext:
            raise ContractError('public-drill-native-live-context-required')
        context._live()
        self.script=validate_public_output_plan(script,context._order.content_sha256,
                                               context._review['drill_binding']['case_id'])
        if self.script['content_sha256']!=context._public_outputs['output_plan_sha256']:
            raise ContractError('public-drill-context-output-binding')
        self.context=context;self.model=self.script['model'];self.controller=None
        self.ledger=None;self.run_dir=None;self.observed=[];self.failed=False

    def bind_controller(self,controller,order,ledger,run_dir):
        from lightyear_factory.orchestrator import FactoryOrchestrator
        from lightyear_factory.agents import ModelAgentSet
        from lightyear_factory.budgeted_providers import AccountedModelProvider
        self.context._live()
        if (self.controller is not None or type(controller) is not FactoryOrchestrator
                or controller.execution_context is not self.context or order is not self.context._order
                or type(controller.agents) is not ModelAgentSet or controller.agents.provider is not self
                or type(controller.agents.bounded_provider) is not AccountedModelProvider
                or controller.agents.bounded_provider.provider is not self
                or controller.agents.bounded_provider.order is not order
                or type(ledger) is not RunLedger or ledger.path!=Path(run_dir)/'events.jsonl'
                or Path(run_dir).parent!=controller.runs_root or not self.context._bound):
            raise ContractError('public-drill-controller-binding')
        self.controller,self.ledger,self.run_dir=controller,ledger,Path(run_dir)
        (self.run_dir/'public-drill').mkdir(exist_ok=False)
        self._append('public_drill_controller_bound',dict(output_plan_sha256=self.script['content_sha256'],
            admission_receipt_sha256=self.context.admission_receipt['content_sha256'],
            work_order_sha256=order.content_sha256,provider=self.provider_id,model=self.model))
        self.context._controller_bound=True

    def _live(self):
        self.context._live()
        validate_public_output_plan(self.script,self.context._order.content_sha256,
                                   self.context._review['drill_binding']['case_id'])
        if (self.failed or self.controller is None or self.controller.agents.provider is not self
                or self.script['content_sha256']!=self.context._public_outputs['output_plan_sha256']
                or self.model!=self.script['model']
                or self.controller.execution_context is not self.context
                or self.controller.agents.bounded_provider.provider is not self
                or self.controller.agents.bounded_provider.order is not self.context._order
                or RunLedger(self.ledger.path).events!=self.ledger.events):
            raise ContractError('public-drill-trace-live-binding')

    def _append(self,kind,payload):
        if RunLedger(self.ledger.path).events!=self.ledger.events:
            raise ContractError('public-drill-ledger-changed')
        event=self.ledger.append('RUNNING',kind,payload)
        with self.ledger.path.open('ab') as stream:os.fsync(stream.fileno())
        return event

    def _artifact(self,sequence,kind,value):
        raw=_bytes(value);relative=f'public-drill/{sequence:04d}-{kind}.json'
        if len(raw)>1024*1024:raise ContractError('public-drill-artifact-too-large')
        with (self.run_dir/relative).open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        return dict(path=relative,sha256=sha256(raw).hexdigest(),bytes=len(raw))

    def complete(self,role,instruction,payload,schema):
        self._live()
        try:
            sequence=len(self.observed)+1
            if sequence>len(self.script['steps']):raise ContractError('public-drill-extra-call')
            step=self.script['steps'][sequence-1]
            invocation=match_invocation(step,sequence,role,instruction,payload,schema)
            bound=self.controller.agents.bounded_provider
            if len(bound.calls)!=sequence-1:raise ContractError('public-drill-accounting-sequence')
            reservations=self.controller._live_journal_events()
            last=reservations[-1]
            if (last['kind']!='reserved' or last['payload']['reservation']['invocation_sha256']!=step['invocation_sha256']
                    or last['payload']['reservation']['call_sequence']!=sequence):
                raise ContractError('public-drill-durable-logical-reservation-required')
            action={'planner':'factory:plan','builder':'factory:build','failure_analyst':'factory:analyze-failure'}[role]
            authorization=self.context.authorize(role,action,None)
            request=self._artifact(sequence,'request',invocation)
            started=self._append('public_drill_call_started',dict(sequence=sequence,role=role,
                invocation_sha256=step['invocation_sha256'],schema_sha256=step['schema_sha256'],request=request,
                authorization_sha256=authorization['content_sha256'],
                logical_reservation_event_sha256=last['event_sha256'],output_plan_sha256=self.script['content_sha256']))
            content=deepcopy(step['response_content']);_validate_schema(content,schema,role)
            self.controller._scan_controller_value('public-drill-response',content)
            response=self._artifact(sequence,'response',content)
            finished=self._append('public_drill_call_finished',dict(sequence=sequence,role=role,
                start_event_sha256=started['event_sha256'],response=response,response_sha256=step['response_sha256']))
            reference=dict(start_event_sha256=started['event_sha256'],end_event_sha256=finished['event_sha256'],
                           output_plan_sha256=self.script['content_sha256'])
            evidence=dict(evidence_type='lightyear-model-call',provider=self.provider_id,model=self.model,role=role,
                request_sha256=step['invocation_sha256'],response_sha256=step['response_sha256'],
                input_tokens=0,output_tokens=0,estimated_cost_usd=0.0,cost_estimate_available=True,
                external_model_calls=0,public_drill_record=reference,elapsed_ms=0)
            evidence['content_sha256']=canonical_hash(evidence)
            self.observed.append(deepcopy(step))
            return ProviderResult(content,evidence)
        except BaseException:
            self.failed=True
            raise

    def provenance(self,receipt):
        # Only this native, same-process bound provider can assert controller origin.
        self.context._live()
        validate_public_output_plan(self.script,self.context._order.content_sha256,
                                   self.context._review['drill_binding']['case_id'])
        if (self.controller is None or self.controller.agents.provider is not self
                or self.controller.execution_context is not self.context
                or self.controller.agents.bounded_provider.provider is not self
                or self.controller.agents.bounded_provider.order is not self.context._order
                or self.script['content_sha256']!=self.context._public_outputs['output_plan_sha256']):
            raise ContractError('public-drill-provenance-context')
        events=RunLedger(self.ledger.path).events
        if events!=self.ledger.events:raise ContractError('public-drill-provenance-ledger')
        retained=json.loads(_bounded_regular_bytes(self.run_dir/'receipt.json',1024*1024,'public-drill-receipt'))
        if (retained!=receipt or receipt.get('content_sha256')!=canonical_hash(receipt,{'content_sha256'})
                or receipt.get('work_order_sha256')!=self.context._order.content_sha256):
            raise ContractError('public-drill-provenance-receipt')
        summary=json.loads(_bounded_regular_bytes(self.run_dir/'summary.json',1024*1024,'public-drill-summary'))
        if summary.get('receipt_sha256')!=receipt['content_sha256']:
            raise ContractError('public-drill-provenance-summary')
        snapshot_events=verify_receipt_tail(receipt,summary,events)
        calls=self.controller.agents.bounded_provider.calls
        trace=verify_recorded_trace(self.script,events,self.controller._live_journal_events(),
            self.context.authorization_receipts,calls,self.run_dir,self.context.admission_receipt)
        complete=trace['output_plan_complete']
        if len(self.observed)!=trace['completed_public_calls']:
            raise ContractError('public-drill-provenance-live-observations')
        result=dict(schema='factory-human-drill-controller-provenance/1',
            status='complete-public-trace' if complete else 'incomplete-public-trace',
            controller_origin_verified=True,trust_boundary='same-process-reviewed-controller-and-GitHub-runner',
            output_plan_complete=complete,receipt_sha256=receipt['content_sha256'],
            ledger_head_sha256=self.ledger.head_sha256,receipt_ledger_snapshot_sha256=receipt['ledger_head_sha256'],
            post_receipt_scan_events=len(events)-snapshot_events,output_plan_sha256=self.script['content_sha256'],
            completed_public_calls=trace['completed_public_calls'],
            unfinished_public_calls=trace['unfinished_public_calls'],accounted_calls=trace['accounted_calls'],
            external_model_calls=0,signatures_created=0,
            production_qualified=False,qualifies_for_factory_receipt=False,
            gaps=['full-production-build-receipt-route-not-integrated']+
                ([] if complete else ['public-output-plan-incomplete']))
        result['content_sha256']=canonical_hash(result)
        return result
