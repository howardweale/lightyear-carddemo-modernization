"""Synthetic hostile-evidence tests plus separately labelled local JDI checks."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import unittest
from tools.b06_host_probe.generation_replay import class_file, lambda_linkage, lambda_body, adjacent_target


def fixture():
    entries=[]
    def put(tag,data):
        entries.append(bytes([tag])+data);return len(entries)
    def u(s):
        b=s.encode();return put(1,struct.pack('>H',len(b))+b)
    def cls(s):return put(7,struct.pack('>H',u(s)))
    def nt(n,d):return put(12,struct.pack('>HH',u(n),u(d)))
    def ref(c,n,d):return put(10,struct.pack('>HH',cls(c),nt(n,d)))
    owner='tests/Ordinary'
    this,parent=cls(owner),cls('java/lang/Object')
    codeattr=u('Code');bootattr=u('BootstrapMethods')
    target_name,target_desc=u('target'),u('()V')
    factory_name,factory_desc=u('factory'),u('()Ljava/lang/Runnable;')
    target=ref(owner,'target','()V')
    targethandle=put(15,struct.pack('>BH',6,target))
    bsm=ref('java/lang/invoke/LambdaMetafactory','metafactory','(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;')
    bsmhandle=put(15,struct.pack('>BH',6,bsm))
    typ=put(16,struct.pack('>H',u('()V')))
    indy=put(18,struct.pack('>HH',0,nt('run','()Ljava/lang/Runnable;')))
    initref=ref('java/lang/Object','<init>','()V')
    cp=b''.join(entries)
    def attribute(name,data):return struct.pack('>HI',name,len(data))+data
    def method(flags,name,desc,code):
        body=struct.pack('>HHI',2,1,len(code))+code+struct.pack('>HH',0,0)
        return struct.pack('>HHHH',flags,name,desc,1)+attribute(codeattr,body)
    factorycode=b'\xba'+struct.pack('>H',indy)+b'\x00\x00\xb0'
    raw=struct.pack('>IHHH',0xcafebabe,0,65,len(entries)+1)+cp
    raw+=struct.pack('>HHHHHH',0x21,this,parent,0,0,2)
    raw+=method(9,target_name,target_desc,b'\xb1')+method(9,factory_name,factory_desc,factorycode)
    raw+=struct.pack('>H',1)+attribute(bootattr,struct.pack('>HHHHHH',1,bsmhandle,3,typ,targethandle,typ))
    def runtime_method(name,signature,flags,code):
        return {'name':name,'signature':signature,'modifiers':flags,'bytecode_hex':code.hex(),'sha256':hashlib.sha256(code).hexdigest()}
    obs={'class':'tests.Ordinary','class_object_id':11,'loader':'L','signature':'Ltests/Ordinary;',
         'constant_pool_count':len(entries)+1,'constant_pool_hex':cp.hex(),'constant_pool_sha256':hashlib.sha256(cp).hexdigest(),
         'methods':[runtime_method('target','()V',9,b'\xb1'),runtime_method('factory','()Ljava/lang/Runnable;',9,factorycode)]}
    generated={**obs,'class':'tests.Anything/abc','class_object_id':12,'signature':'Ltests/Anything.abc;','fields':[],
               'methods':[runtime_method('<init>','()V',2,b'\x2a\xb7'+struct.pack('>H',initref)+b'\xb1'),runtime_method('run','()V',1,b'\xb8'+struct.pack('>H',target)+b'\xb1')]}
    host={'class':'tests.Ordinary','class_object_id':11,'loader':'L','signature':'Ltests/Ordinary;'}
    def mt(ret):return {'class':'java.lang.invoke.MethodType','fields':{'java.lang.invoke.MethodType.ptypes':[],'java.lang.invoke.MethodType.rtype':{'signature':ret}}}
    f={'targetClass':host,'factoryType':mt('Ljava/lang/Runnable;'),'interfaceMethodName':'run','interfaceMethodType':mt('V'),
       'dynamicMethodType':mt('V'),'implInfo':{'fields':{'java.lang.invoke.InfoFromMemberName.referenceKind':'6',
          'java.lang.invoke.InfoFromMemberName.member':{'fields':{'java.lang.invoke.MemberName.clazz':host,'java.lang.invoke.MemberName.name':'target'}}}},
       'implClass':host,'implMethodName':'target','implMethodDesc':'()V','implKind':'6','isSerializable':'false','altInterfaces':[],
       'altMethods':[],'useImplMethodHandle':'false','argNames':[],'argDescs':[]}
    record={'entry_method':'java.lang.invoke.InnerClassLambdaMetafactory.spinInnerClass()Ljava/lang/Class;',
            'lambda_factory':f,'returned_class':{'class':'tests.Anything/abc','class_object_id':12,'loader':'L'},
            'stack':[{'class':'tests.Ordinary','class_object_id':11,'loader':'L','method':'factory','signature':'()Ljava/lang/Runnable;','code_index':0}]}
    frames=[{'class':'tests.Ordinary','class_object_id':11,'loader':'L','method':'target','signature':'()V'},
            {'class':'tests.Anything/abc','class_object_id':12,'loader':'L','method':'run','signature':'()V'}]
    return raw,record,{'11':obs,'12':generated},frames


class SyntheticGeneratedTests(unittest.TestCase):
    def proof(self,raw,r,d,frames):
        return adjacent_target(lambda_body(r,d,lambda_linkage(r,d,raw)),frames)

    def test_full_linkage_without_lambda_name_pattern(self):
        p=self.proof(*fixture())
        self.assertTrue(p['adjacent_target_verified']);self.assertFalse(p['native_admission'])
    def test_extra_logic_rejected_with_consistent_new_hash(self):
        for extra in (b'\x00',b'\x03\x57',b'\xa7\x00\x03'):
            raw,r,d,f=fixture();m=d['12']['methods'][1]
            b=extra+bytes.fromhex(m['bytecode_hex']);m['bytecode_hex']=b.hex();m['sha256']=hashlib.sha256(b).hexdigest()
            with self.assertRaisesRegex(ValueError,'extra-logic'):self.proof(raw,r,d,f)
    def test_wrong_host_loader_and_site_are_rejected(self):
        for change in ('host','loader','site','target','generator'):
            raw,r,d,f=fixture()
            if change=='host':r['lambda_factory']['targetClass']['class']='tests.Forged'
            elif change=='loader':r['returned_class']['loader']='wrong'
            elif change=='site':r['stack'][0]['code_index']=1
            elif change=='target':r['lambda_factory']['implMethodName']='different'
            else:r['entry_method']='candidate.Fake.spinInnerClass()Ljava/lang/Class;'
            with self.assertRaises(ValueError):self.proof(raw,r,d,f)
    def test_missing_wrong_or_older_adjacent_target_rejected(self):
        for change in ('missing','wrong','older','loader'):
            raw,r,d,f=fixture()
            if change=='missing':f=f[1:]
            elif change=='wrong':f[0]['method']='forged'
            elif change=='older':f.reverse()
            else:f[0]['loader']='other'
            with self.assertRaises(ValueError):self.proof(raw,r,d,f)
    def test_added_method_and_changed_constructor_rejected(self):
        for change in ('extra','constructor'):
            raw,r,d,f=fixture()
            if change=='extra':d['12']['methods'].append(copy.deepcopy(d['12']['methods'][1]))
            else:d['12']['methods'][0]['modifiers']=1
            with self.assertRaises(ValueError):self.proof(raw,r,d,f)
    def test_method_flags_and_unknown_wire_bits_rejected(self):
        for bits in (0x20,0x10000,0x10000000):
            raw,r,d,f=fixture();d['11']['methods'][0]['modifiers'] |= bits
            with self.assertRaisesRegex(ValueError,'flags'):self.proof(raw,r,d,f)
    def test_pool_and_method_bytes_rehashed_changes_rejected(self):
        raw,r,d,f=fixture();m=d['11']['methods'][0];m['bytecode_hex']='00b1';m['sha256']=hashlib.sha256(bytes.fromhex(m['bytecode_hex'])).hexdigest()
        with self.assertRaisesRegex(ValueError,'methods'):self.proof(raw,r,d,f)
    def test_source_truncation_fails(self):
        raw,_,_,_=fixture()
        for n in (1,5,10):
            with self.assertRaises(Exception):class_file(raw[:-n])


ROOT=Path(__file__).resolve().parents[1]
AREA=ROOT/'work/b06-observer-v2-host'
OBSERVATION=AREA/'generation-proof-attempt7/observations.json'


@unittest.skipUnless(OBSERVATION.is_file(),'local external-JDI evidence absent; no synthetic replacement')
class LocalJdiGeneratedTests(unittest.TestCase):
    def test_all_framework_lambdas_and_public_role_lambdas(self):
        d=json.loads(OBSERVATION.read_text(encoding='utf-8'));self.assertTrue(d['complete'])
        base=AREA/'pool-probe-inputs/surefire59';interface=(base/'org/junit/platform/engine/TestEngine.class').read_bytes()
        framework=0;roles=[]
        for r in d['records']:
            if not r.get('entry_method','').endswith('spinInnerClass()Ljava/lang/Class;'):continue
            host=r['lambda_factory']['targetClass']['class']
            if host.startswith('org.junit.'):
                raw=(base/(host.replace('.','/')+'.class')).read_bytes();framework+=1
            elif host.startswith('HostGenerationTarget$'):
                raw=(AREA/'generation-proof-build4'/(host+'.class')).read_bytes()
            else:continue
            p=lambda_body(r,d['definitions'],lambda_linkage(r,d['definitions'],raw,test_engine=interface))
            self.assertTrue(p['adapter_body_verified']);self.assertFalse(p['native_admission'])
            if host.startswith('HostGenerationTarget$'):
                stacks=[v['stack'] for v in d['records'] if v['kind']=='target-checkpoint' and any(f['class_object_id']==p['generated_class_object_id'] for f in v['stack'])]
                self.assertEqual(len(stacks),1);adjacent_target(p,stacks[0]);roles.append(host)
        self.assertEqual(framework,24)
        self.assertEqual(set(roles),{'HostGenerationTarget$Candidate','HostGenerationTarget$Support','HostGenerationTarget$Outside'})


if __name__=='__main__':unittest.main()
