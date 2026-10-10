import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from tools.ms94_b06_observer_audit import Audit, POLICY


def record(index, action, position, detail, set_id=1):
    return dict(kind='observer-audit', policy=POLICY, checkpoint=False,
                sequence=index, audit_index=index, event_set_id=set_id, event_position=position,
                action=action, detail=detail)


class AuditTests(unittest.TestCase):
    def opened(self):
        audit = Audit()
        audit.event(record(1, 'event-set-open', -1, dict(size=1, suspend_policy=2)))
        return audit

    def test_suspend_resume_order_and_bounds(self):
        audit = self.opened()
        audit.event(record(2, 'jdi-event', 0, dict(event_type='vm-start', request_id=0)))
        audit.event(record(3, 'resume-requested', 0, dict(scope='event-set')))
        audit.event(record(4, 'resume-completed', 0, dict(scope='event-set')))
        self.assertTrue(audit.resumed)
        for malformed in (record(2,'resume-completed',-1,{}),
                          record(2,'resume-requested',-1,{}),
                          record(2,'jdi-event',1,dict(event_type='vm-start',request_id=0)),
                          record(4,'jdi-event',0,dict(event_type='vm-start',request_id=0))):
            with self.assertRaises(ValueError): self.opened().event(malformed)
        with patch('tools.ms94_b06_observer_audit.MAX_BYTES', 1):
            with self.assertRaises(ValueError): self.opened()
        with patch('tools.ms94_b06_observer_audit.MAX_EVENTS', 0):
            with self.assertRaises(ValueError): self.opened()

    def test_refusal_cannot_be_claimed_complete(self):
        audit = self.opened()
        audit.event(record(2,'jdi-event',0,dict(event_type='breakpoint',request_id=7)))
        audit.event(record(3,'dispatch-refused',0,dict(exception_class='java.lang.IllegalStateException')))
        with self.assertRaises(ValueError): audit.complete()
        with self.assertRaises(ValueError): audit.event(record(4,'resume-requested',0,{}))


def host_capture(java, javac, source, out, *, fault=False, diagnostic=False):
    """Public diagnostic fixture only. Fault is injected in a temporary source copy."""
    out.mkdir()
    if fault:
        needle = 'generation.atReturn(vm,event);return;'
        if source.count(needle) != 1: raise ValueError('fault hook missing')
        source = source.replace(needle, 'generation.pending.clear();generation.atReturn(vm,event);return;')
    if diagnostic:
        # Suppress ONLY selected outer entry delivery in the disposable host fixture.
        import re
        source,n=re.subn(r'if\(generation.selected\(event.location\(\).method\(\)\)\)',
            'if(generation.selected(event.location().method()) && !event.location().method().name().equals("spinInnerClass"))',source)
        if n!=1: raise ValueError('diagnostic entry-delivery fixture hook missing')
    (out/'PostingObserver.java').write_text(source)
    (out/'Probe.java').write_text('''package fixture;
import java.lang.invoke.*;
public class Probe {
 public static void target() {}
 public static void main(String[] args)throws Throwable {
  Thread.currentThread().setName("PRIVATE-CUSTOMER-VALUE");
  var lookup=MethodHandles.lookup();
  var target=lookup.findStatic(Probe.class,"target",MethodType.methodType(void.class));
  for(int i=0;i<40;i++) {
   var site=LambdaMetafactory.metafactory(lookup,"run",MethodType.methodType(Runnable.class),MethodType.methodType(void.class),target,MethodType.methodType(void.class));
   ((Runnable)site.getTarget().invokeExact()).run();
  }
 }
}''')
    subprocess.run([str(javac),'--add-modules','jdk.jdi','-d',str(out),str(out/'PostingObserver.java'),str(out/'Probe.java')],check=True,capture_output=True,timeout=45)
    started=time.perf_counter()
    target=subprocess.Popen([str(java),'-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:0','-cp',str(out),'fixture.Probe'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        port=target.stdout.readline().strip().rsplit(':',1)[-1].strip()
        if not port.isdigit(): raise ValueError('no host listener')
        observed=subprocess.run([str(java),'--add-modules','jdk.jdi','-cp',str(out),'lightyear.observer.PostingObserver','127.0.0.1',port,'observer-binding-v2',*(['diagnostic-unmatched-return-v1'] if diagnostic else [])],input='',capture_output=True,text=True,timeout=60)
        elapsed=time.perf_counter()-started
        events=[json.loads(line) for line in observed.stdout.splitlines()]
        return observed, events, elapsed
    finally:
        if target.poll() is None: target.terminate()
        target.communicate(timeout=10)


@unittest.skipUnless(os.environ.get('B06_HOST_JDK'), 'host JDK explicitly enabled')
class AuditHostTests(unittest.TestCase):
    def test_real_jdi_and_failure_context_before_refusal(self):
        java=Path(os.environ['B06_HOST_JDK'])/'bin'/('java.exe' if os.name=='nt' else 'java')
        javac=java.with_name('javac.exe' if os.name=='nt' else 'javac')
        source=(Path(__file__).resolve().parents[1]/'factory/idempiere/b06-observer/PostingObserver.java').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            for fault in (False,True):
                observed,events,_=host_capture(java,javac,source,Path(tmp)/str(fault),fault=fault)
                audit=Audit()
                for event in events:
                    if event['kind']=='observer-audit': audit.event(event)
                if fault:
                    self.assertNotEqual(observed.returncode,0)
                    self.assertIn('generation return arm without matching activation',observed.stderr)
                    self.assertEqual(events[-1]['action'],'dispatch-refused')
                    previous=events[-2]
                    self.assertEqual(previous['action'],'jdi-event')
                    detail=previous['detail']
                    self.assertTrue(detail['return_breakpoint'])
                    self.assertGreater(detail['depth'],0)
                    self.assertGreater(detail['request_id'],0)
                    self.assertTrue(detail['pending'])
                    self.assertIn('top_location',detail)
                    with self.assertRaises(ValueError): audit.complete()
                else:
                    self.assertEqual(observed.returncode,0,observed.stderr)
                    audit.complete()
                    self.assertEqual(events[-1]['kind'],'vm-death')
                self.assertNotIn('PRIVATE-CUSTOMER-VALUE',observed.stdout)
