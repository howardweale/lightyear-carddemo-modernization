"""CI-only synthetic relation tests. No admitted context, proof, transport or billing claim."""
from copy import deepcopy
import os,unittest
from unittest.mock import patch
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_execution.configured_human_success import (
    check_successful_call_relations,verify_original_configured_success)


def relations():
    calls=[];transports=[]
    for seq,role in enumerate(('planner','failure_analyst','builder'),1):
        invocation={'call_sequence':seq,'invocation_sha256':str(seq)*64}
        for kind in ('input-token-count','responses'):
            reservation=dict(transport_kind=kind,provider='openai-responses',model='pinned-model',
                role=role,invocation=invocation,provider_attempt=1,request_sha256='a'*64,
                canonical_request_sha256='b'*64)
            observation=dict(outcome='returned',input_token_count=12,response_usage={'input_tokens':12,'output_tokens':4})
            transports.append(dict(reservation=reservation,observation=observation))
        call=dict(provider='openai-responses',model='pinned-model',role=role,call_sequence=seq,
            input_token_preflight=True,attempts=1,retry_count=0,token_count_attempts=1,
            token_count_retry_count=0,routing={'fallback':False},
            billing_policy={'observed_service_tier':'flex','billing_final':False},
            token_count_request_sha256='b'*64,request_sha256='b'*64,
            input_tokens_preflight=12,input_tokens=12,output_tokens=4)
        call['content_sha256']=canonical_hash(call);calls.append(call)
    return calls,transports


class ConfiguredSuccessRelationTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_pure_synthetic_relation_check_returns_no_authority_record(self):
        calls,transports=relations();before=deepcopy((calls,transports))
        self.assertIsNone(check_successful_call_relations(calls,transports,'pinned-model'))
        self.assertEqual((calls,transports),before)

    def test_wrong_role_retry_fallback_tier_and_reserved_charge_refused(self):
        for update in ({'role':'builder'},{'attempts':2},{'attempts':True},{'retry_count':1},
                       {'routing':{'fallback':True}},{'billing_policy':{'observed_service_tier':'default','billing_final':False}},
                       {'usage':'reserved-upper-bound'}):
            calls,transports=relations();calls[0].update(update)
            calls[0]['content_sha256']=canonical_hash(calls[0],{'content_sha256'})
            with self.assertRaisesRegex(ContractError,'native-call-relations'):
                check_successful_call_relations(calls,transports,'pinned-model')

    def test_logical_only_evidence_cannot_supply_six_physical_sends(self):
        calls,transports=relations()
        with self.assertRaisesRegex(ContractError,'six-send'):
            check_successful_call_relations(calls,transports[:-1],'pinned-model')

    def test_reordered_or_unobserved_transport_refused(self):
        for missing in (False,True):
            calls,transports=relations()
            if missing:transports[1]['observation']=None
            else:transports[0],transports[1]=transports[1],transports[0]
            with self.assertRaisesRegex(ContractError,'physical-call-relations'):
                check_successful_call_relations(calls,transports,'pinned-model')

    def test_count_request_or_usage_mismatch_refused(self):
        calls,transports=relations();transports[1]['observation']['response_usage']['input_tokens']=13
        with self.assertRaisesRegex(ContractError,'request-usage-relations'):
            check_successful_call_relations(calls,transports,'pinned-model')

    def test_self_hashed_receipt_cannot_establish_controller_origin(self):
        with patch('lightyear_factory.orchestrator._reconcile_accounting_journal') as replay:
            with self.assertRaisesRegex(ContractError,'original-controller'):
                verify_original_configured_success({'status':'passed'})
            replay.assert_not_called()
