"""Actual member/frame binding rejects name-only and deep-frame substitution."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from tools.b06_host_probe.lambda_form_replay import observed_dynamic_target
from tools.b06_host_probe.generation_replay import ordinary_definition


def fixture():
    graph={'root':'handle','nodes':{
        'handle':{'class':'java.lang.invoke.DirectMethodHandle','fields':{'member':{'ref':'member'}}},
        'member':{'class':'java.lang.invoke.MemberName','fields':{
            'java.lang.invoke.MemberName.clazz':{'ref':'class'},
            'java.lang.invoke.MemberName.name':{'ref':'name'},
            'java.lang.invoke.MemberName.type':{'ref':'type'},
            'java.lang.invoke.MemberName.flags':str(6<<24)}},
        'class':{'class':'java.lang.Class','value':{'class':'test.Candidate','class_object_id':7,'loader':'4'}},
        'name':{'class':'java.lang.String','value':'target'},
        'type':{'class':'java.lang.String','value':'()V'}}}
    frames=[{'class_object_id':7,'class':'test.Candidate','method':'target','signature':'()V','loader':'4'}]
    definitions={'7':{'methods':[{'name':'target','signature':'()V','sha256':'a'*64}]}}
    bindings={'7':{'class':'test.Candidate','loader':'4','class_sha256':'b'*64,'methods':{'target()V':'a'*64}}}
    return graph,frames,definitions,bindings,set()


class DynamicTargetTests(unittest.TestCase):
    def test_member_and_actual_frame_are_both_required(self):
        p=observed_dynamic_target(*fixture())
        self.assertTrue(p['member_graph_and_actual_frame_agree'])
        self.assertFalse(p['resolved_vm_pointer_claimed'])
        self.assertFalse(p['native_admission'])

    def test_wrong_host_loader_member_bytes_and_missing_frame_fail(self):
        for change in ('host','loader','method','bytes','missing','recursive','unbound'):
            g,f,d,b,j=fixture()
            if change=='host':g['nodes']['class']['value']['class']='java.Forged'
            elif change=='loader':g['nodes']['class']['value']['loader']='99'
            elif change=='method':g['nodes']['name']['value']='different'
            elif change=='bytes':d['7']['methods'][0]['sha256']='c'*64
            elif change=='missing':f=[]
            elif change=='recursive':f=f*2
            else:b={}
            with self.subTest(change=change), self.assertRaises(ValueError):
                observed_dynamic_target(g,f,d,b,j)

    def test_unreachable_member_cannot_supply_target(self):
        g,f,d,b,j=fixture();g['nodes']['handle']['fields']={}
        with self.assertRaisesRegex(ValueError,'missing-or-ambiguous'):
            observed_dynamic_target(g,f,d,b,j)


AREA=Path(__file__).resolve().parents[1]/'work/b06-observer-v2-host'
OBS=AREA/'generation-proof-attempt11/observations.json'


@unittest.skipUnless(OBS.exists(),'local external-JDI evidence absent')
class LocalDefinitionTests(unittest.TestCase):
    def test_original_junit_and_fixture_definition_returns(self):
        d=json.loads(OBS.read_text(encoding='utf-8'))
        base=AREA/'pool-probe-inputs/surefire59';fixture=AREA/'generation-proof-build4'
        interface=(base/'org/junit/platform/engine/TestEngine.class').read_bytes()
        count=0;unprepared=0;unapproved=0
        for r in d['records']:
            if r['kind']!='ordinary-definition':continue
            name=r['returned_class']['class'];directory=fixture if name.startswith('Host') else base
            path=directory/(name.replace('.','/')+'.class')
            self.assertTrue(path.is_file(),name)
            origin={'protocol':'file','host':'','port':'-1','file':'/'+directory.resolve().as_posix()+'/'}
            raw=path.read_bytes();runtime=d['definitions'][str(r['returned_class']['class_object_id'])]
            if runtime.get('prepared') is False:
                with self.assertRaisesRegex(ValueError,'unprepared'):
                    ordinary_definition(r,runtime,raw,origin,test_engine=interface)
                unprepared+=1;continue
            if name=='org.junit.platform.engine.support.descriptor.AbstractTestDescriptor':
                with self.assertRaisesRegex(ValueError,'unapproved-pool-reconstitution'):
                    ordinary_definition(r,runtime,raw,origin,test_engine=interface)
                self.assertFalse(any(f['class']==name for event in d['records'] for f in event.get('stack',[])))
                unapproved+=1;continue
            p=ordinary_definition(r,runtime,raw,origin,test_engine=interface)
            self.assertTrue(p['definition_return_verified']);count+=1
            for change in ('return','loader','origin','bytes'):
                bad=copy.deepcopy(r)
                if change=='return':bad['returned_class']['class_object_id']+=1
                elif change=='loader':bad['defining_loader']='wrong'
                elif change=='origin':bad['code_source']['file']='/candidate/forged/'
                else:
                    b=bytes.fromhex(bad['definition_input_hex'])+b'\0'
                    bad['definition_input_hex']=b.hex();bad['definition_input_sha256']=hashlib.sha256(b).hexdigest()
                with self.assertRaises(ValueError):ordinary_definition(bad,runtime,raw,origin,test_engine=interface)
        self.assertEqual(count,51);self.assertEqual(unprepared,5);self.assertEqual(unapproved,1)


if __name__=='__main__':unittest.main()
