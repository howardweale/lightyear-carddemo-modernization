import unittest
from tools.b06_host_probe.audit_compatibility import compare_events,error_summary
from tools.ms94_b06_observer_audit import Audit
from lightyear_calibration.contracts import canonical

def event(index,action,position,detail,set_id=1):
    return dict(kind='observer-audit',policy='structural-jdi-v1',checkpoint=False,sequence=index,
                audit_index=index,event_set_id=set_id,event_position=position,action=action,detail=detail)

def prefix(refused):
    records=[event(1,'event-set-open',-1,dict(size=1,suspend_policy=2)),
             event(2,'jdi-event',0,dict(event_type='vm-start',request_id=0)),
             event(3,'dispatch-completed',0,dict(pending_generation_ids=[])),
             event(4,'resume-requested',0,dict(scope='event-set')),
             event(5,'resume-completed',0,dict(scope='event-set')),
             event(6,'event-set-open',-1,dict(size=1,suspend_policy=2),2),
             event(7,'jdi-event',0,dict(event_type='breakpoint',request_id=11),2)]
    if refused:records.append(event(8,'dispatch-refused',0,dict(exception_class='java.lang.IllegalStateException'),2))
    return records

class AuditCompatibilityTests(unittest.TestCase):
    def test_legacy_refusal_and_truncated_prefixes_remain_incomplete(self):
        for refused in (False,True):
            with self.subTest(refused=refused):
                records=prefix(refused);audit=Audit()
                for record in records:audit.event(record)
                self.assertEqual(audit.count,8 if refused else 7)
                self.assertEqual(audit.bytes,sum(len(canonical({k:v for k,v in r.items() if k not in ('sequence','checkpoint')})) for r in records))
                self.assertEqual((audit.set_id,audit.position,audit.size),(2,0,1))
                self.assertEqual(audit.refused,refused);self.assertTrue(audit.vm_started);self.assertFalse(audit.vm_died)
                with self.assertRaisesRegex(ValueError,'observer-audit-incomplete'):audit.complete()
    def test_legacy_refusal_is_terminal(self):
        audit=Audit()
        for record in prefix(True):audit.event(record)
        with self.assertRaisesRegex(ValueError,'observer-audit-after-refusal'):
            audit.event(event(9,'resume-requested',0,dict(scope='event-set'),2))
    def test_comparator_detects_accidental_completion_upgrade(self):
        class InvalidPromotion(Audit):
            def complete(self):pass
        result=compare_events(iter(prefix(False)),Audit,InvalidPromotion)
        self.assertFalse(result['equivalent']);self.assertEqual(result['old']['completion_error']['code'],'observer-audit-incomplete')
        self.assertIsNone(result['new']['completion_error']);self.assertFalse(result['qualification_credit'])
    def test_error_export_does_not_publish_arbitrary_values(self):
        value=error_summary(ValueError('PRIVATE INPUT: do not export'))
        self.assertNotIn('code',value);self.assertEqual(len(value['message_sha256']),64)

if __name__=='__main__':unittest.main()
