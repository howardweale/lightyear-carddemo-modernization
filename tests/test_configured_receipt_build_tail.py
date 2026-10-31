"""CI-only untrusted relationship examples; no controller/admission fixtures."""
import copy,json,os,unittest
from hashlib import sha256
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_execution.configured_receipt_tail import verify_configured_receipt_tail
from lightyear_execution.public_drill_runtime import verify_receipt_tail

def hashed(value):
    value=dict(value);value['content_sha256']=canonical_hash(value,{'content_sha256'});return value

def scan(name,value):
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False).encode('utf-8')
    row=dict(kind='model_isolation_scan_passed',state='RUNNING',
        payload=dict(status='passed',scanned=[dict(artifact=name,sha256=sha256(raw).hexdigest())]))
    row['event_sha256']=canonical_hash(row)
    return row

def records(passed=True):
    events=[dict(kind='untrusted-prefix',state='VERIFYING',payload={},event_sha256='a'*64)]
    build=hashed(dict(schema='factory-build-receipt/1',run_id='untrusted-example',
        work_order_sha256='b'*64,status='passed' if passed else 'blocked',
        qualifies_for_factory_receipt=passed,ledger_event_count=1,ledger_prefix_sha256='a'*64))
    events.append(scan('factory-build-receipt',build))
    events.append(dict(kind='factory_build_receipt_computed',state='VERIFYING',
        payload=build,event_sha256='c'*64))
    receipt=hashed(dict(factory_build_receipt=build,run_id='untrusted-example',
        work_order_sha256='b'*64,status=build['status'],event_count=3,ledger_head_sha256='c'*64))
    summary=dict(receipt_sha256=receipt['content_sha256'],status=receipt['status'])
    events.extend([scan('run-receipt',receipt),scan('run-summary',summary)])
    return receipt,summary,events

class ConfiguredReceiptTail(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
    def test_two_scan_passed_and_blocked_full_build_relationships(self):
        for passed in (True,False):
            original=records(passed);saved=copy.deepcopy(original)
            self.assertEqual(verify_configured_receipt_tail(*original),3)
            self.assertEqual(original,saved)
    def test_original_public_three_scan_verifier_refuses_full_build_tail(self):
        with self.assertRaisesRegex(ContractError,'unexpected-receipt-tail'):
            verify_receipt_tail(*records())
    def test_no_build_early_refusal_delegates_unchanged(self):
        receipt={'ledger_head_sha256':'a'*64};summary={}
        events=[{'event_sha256':'a'*64}]
        self.assertEqual(verify_configured_receipt_tail(receipt,summary,events),
            verify_receipt_tail(receipt,summary,events))
        with self.assertRaisesRegex(ContractError,'snapshot-missing'):
            verify_configured_receipt_tail(receipt,summary,[])
    def test_missing_extra_and_reordered_final_scans_refuse(self):
        for change in ('missing','extra','reverse'):
            receipt,summary,events=records()
            if change=='missing':events.pop()
            elif change=='extra':events.append(scan('run-summary',summary))
            else:events[-2:]=reversed(events[-2:])
            with self.subTest(change=change),self.assertRaises(ContractError):
                verify_configured_receipt_tail(receipt,summary,events)
    def test_snapshot_count_boolean_or_wrong_prefix_refuses(self):
        for field,value in [('event_count',True),('event_count',2),('ledger_head_sha256','d'*64)]:
            receipt,summary,events=records();receipt[field]=value;receipt=hashed(receipt)
            summary['receipt_sha256']=receipt['content_sha256']
            with self.subTest(field=field),self.assertRaises(ContractError):
                verify_configured_receipt_tail(receipt,summary,events)
        receipt,summary,events=records();events[0]['event_sha256']='d'*64
        with self.assertRaisesRegex(ContractError,'build-prefix'):
            verify_configured_receipt_tail(receipt,summary,events)
    def test_computed_payload_or_duplicate_event_refuses(self):
        receipt,summary,events=records()
        events[2]=copy.deepcopy(events[2]);events[2]['payload']['qualifies_for_factory_receipt']=1
        with self.assertRaisesRegex(ContractError,'computed-binding'):
            verify_configured_receipt_tail(receipt,summary,events)
        receipt,summary,events=records();events.append(copy.deepcopy(events[2]))
        with self.assertRaises(ContractError):verify_configured_receipt_tail(receipt,summary,events)
    def test_each_scan_is_bound_to_exact_original_json_bytes(self):
        for index in (1,3,4):
            receipt,summary,events=records()
            events[index]['payload']['scanned'][0]['sha256']='0'*64
            with self.subTest(index=index),self.assertRaisesRegex(ContractError,'scan-binding'):
                verify_configured_receipt_tail(receipt,summary,events)
    def test_build_identity_status_and_digest_substitutions_refuse(self):
        for field,value in [('run_id','other'),('work_order_sha256','d'*64),
            ('status','blocked'),('qualifies_for_factory_receipt',1),('content_sha256','0'*64)]:
            receipt,summary,events=records();receipt=copy.deepcopy(receipt)
            receipt['factory_build_receipt'][field]=value
            if field!='content_sha256':receipt['factory_build_receipt']=hashed(receipt['factory_build_receipt'])
            receipt=hashed(receipt);summary['receipt_sha256']=receipt['content_sha256']
            with self.subTest(field=field),self.assertRaisesRegex(ContractError,'build-binding'):
                verify_configured_receipt_tail(receipt,summary,events)
