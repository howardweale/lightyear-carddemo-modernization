"""Synthetic stubs test the contract; these are not native qualification."""
import copy
import hashlib
import struct
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import zipfile

from tools.ms94_b06_admission import EvidenceFailure
from tools.ms94_b06_forwarding_stub import validate_stub_body as validate_stub, receipt_records, definition, validate_spec
from tools.ms94_b06_posting_replay import checked_frames, origin, CANDIDATE
from lightyear_calibration.contracts import seal
from lightyear_calibration.contracts import canonical
from tools.ms94_b06_posting_replay import replay_stream


def fixture(owner=CANDIDATE):
    entries = []
    def put(tag, raw):
        entries.append(bytes([tag]) + raw); return len(entries)
    def utf8(s):
        b=s.encode(); return put(1,struct.pack('>H',len(b))+b)
    def cls(s): return put(7,struct.pack('>H',utf8(s)))
    def nt(n,d): return put(12,struct.pack('>HH',utf8(n),utf8(d)))
    field=put(9,struct.pack('>HH',cls('tests/Generated.0x1'),nt('arg$1','Ljava/lang/String;')))
    method=put(10,struct.pack('>HH',cls(owner.replace('.','/')),nt('target','(Ljava/lang/String;)Ljava/lang/Object;')))
    code=b'\x2a\xb4'+struct.pack('>H',field)+b'\xb8'+struct.pack('>H',method)+b'\xb0'
    cp=b''.join(entries)
    raw={'definition_id':'test:stub','class':'tests.Generated/0x1','class_signature':'Ltests/Generated.0x1;',
         'method':'run','signature':'()Ljava/lang/Object;','loader':'77','class_modifiers':0x1010,
         'method_modifiers':1,'native_or_abstract':False,'constant_pool_count':len(entries)+1,
         'constant_pool_hex':cp.hex(),'constant_pool_sha256':hashlib.sha256(cp).hexdigest(),
         'bytecode_hex':code.hex(),'method_sha256':hashlib.sha256(code).hexdigest(),
         'fields':[{'name':'arg$1','signature':'Ljava/lang/String;','modifiers':0x12}]}
    frame={k:raw[k] for k in ('definition_id','class','method','signature','loader','constant_pool_sha256','method_sha256')}
    target={'definition_id':'test:host','class':owner,'method':'target','signature':'(Ljava/lang/String;)Ljava/lang/Object;',
            'loader':'77','constant_pool_sha256':'a'*64,'method_sha256':'b'*64}
    classes={owner:{'constant_pool_sha256':'a'*64,'class_sha256':'c'*64,
                    'methods':{'target(Ljava/lang/String;)Ljava/lang/Object;':'b'*64}}}
    return raw,frame,target,classes


class ForwardingTests(unittest.TestCase):
    def test_collection_failure_preserves_census_without_docker_or_trust_claim(self):
        from tools.ms94_b06_posting_broker import PostingBroker
        raw,f,t,c=fixture()
        records=[seal({'event':{'kind':'frame-definition','definition':raw}}),
                 seal({'event':{'kind':'exception','frames':[t,f]}})]
        with tempfile.TemporaryDirectory() as tmp:
            def fail(): raise RuntimeError('synthetic collection interruption')
            runner=SimpleNamespace(run=Path(tmp),owner='synthetic',
                plan={'posting_observer':{},'content_sha256':'a'*64},check_cancel=fail)
            broker=PostingBroker(runner,'oracle','synthetic-app',None)
            broker.records=records;broker.previous=records[-1]['content_sha256'];broker.host_jar_entries={}
            data=b'\n'.join(canonical(r) for r in records)+b'\n'
            (broker.private/'events.jsonl').write_bytes(data)
            signed=[]
            with patch('tools.ms94_b06_posting_broker.sign_once',side_effect=lambda p,v,s:signed.append((p,v))), \
                 patch('tools.ms94_b06_posting_broker.docker',side_effect=AssertionError('Docker forbidden')):
                broker._collect()
            self.assertTrue(broker.done.is_set());self.assertIsNotNone(broker.failure)
            census=next(v for p,v in signed if p.name=='frame-census.json')
            self.assertFalse(census['complete']);self.assertFalse(census['native_qualification'])
            self.assertEqual(census['frame_records'],receipt_records(records))
            self.assertEqual((broker.private/'events.jsonl').read_bytes(),data)

    def test_missing_return_fails_closed(self):
        raw,f,t,c=fixture()
        data=bytes.fromhex(raw['bytecode_hex'])[:-1]
        raw['bytecode_hex']=data.hex();raw['method_sha256']=hashlib.sha256(data).hexdigest()
        f['method_sha256']=raw['method_sha256']
        with self.assertRaisesRegex(EvidenceFailure,'missing-return'):validate_stub(raw,f,t,c,{})

    def test_reordered_sam_arguments_are_not_a_standard_forwarder(self):
        raw,f,t,c=fixture()
        # These loads have equal types; the order check must precede host trust.
        old=bytes.fromhex(raw['constant_pool_hex'])
        before=b'(Ljava/lang/String;)Ljava/lang/Object;'
        after=b'(Ljava/lang/String;II)Ljava/lang/Object;'
        cp=old.replace(struct.pack('>H',len(before))+before,struct.pack('>H',len(after))+after)
        raw['constant_pool_hex']=cp.hex();raw['constant_pool_sha256']=hashlib.sha256(cp).hexdigest()
        raw['signature']='(II)Ljava/lang/Object;'
        code=bytes.fromhex(raw['bytecode_hex'])
        code=code[:4]+b'\x1c\x1b'+code[4:]
        raw['bytecode_hex']=code.hex();raw['method_sha256']=hashlib.sha256(code).hexdigest()
        for k in ('constant_pool_sha256','method_sha256','signature'):f[k]=raw[k]
        with self.assertRaisesRegex(EvidenceFailure,'argument-order'):validate_stub(raw,f,t,c,{})

    def test_plan_requires_exact_policy_amendment_and_catalogued_jar_host(self):
        raw,f,t,c=fixture('org.junit.example.Host')
        spec={'forwarding_stub':{'policy':'exact-forwarding-stub-v1','adjacent_target':'younger'},
              'forwarding_amendment_sha256':'d'*64,'host_jar_entries':{
                  t['class']:{'jar':'/application/pinned.jar','member':t['class'].replace('.','/')+'.class',
                              'entry_sha256':'c'*64}}}
        validate_spec(spec,c)
        for change in ('direction','hash','path','missing-amendment'):
            s=copy.deepcopy(spec)
            if change=='direction':s['forwarding_stub']['adjacent_target']='older'
            elif change=='hash':s['host_jar_entries'][t['class']]['entry_sha256']='0'*64
            elif change=='path':s['host_jar_entries'][t['class']]['jar']='/application/../tmp/fake.jar'
            else:s.pop('forwarding_amendment_sha256')
            with self.assertRaises(EvidenceFailure):validate_spec(s,c)

    def test_real_zip_entry_probe_accepts_only_exact_bytes(self):
        from tools.ms94_b06_host_jar_probe import verify_entries
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pinned.jar'; name='org.junit.example.Host'; member=name.replace('.','/')+'.class'
            with zipfile.ZipFile(path,'w') as z:z.writestr(member,b'public synthetic class bytes')
            spec={name:{'jar':str(path),'member':member,
                        'entry_sha256':hashlib.sha256(b'public synthetic class bytes').hexdigest()}}
            # Only the Linux root predicate is mocked; real ZIP parsing and hashes run.
            with patch.object(type(path),'is_relative_to',return_value=True):
                result=verify_entries(spec)
                self.assertEqual(result[name]['jar_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
                spec[name]['entry_sha256']='0'*64
                with self.assertRaisesRegex(ValueError,'entry-changed'):verify_entries(spec)
            with self.assertRaisesRegex(ValueError,'jar-path'):verify_entries(spec)

    def test_captured_value_single_invoke_return_is_admitted(self):
        raw,f,t,c=fixture()
        proof=validate_stub(raw,f,t,c,{})
        self.assertEqual(proof['host_class'],CANDIDATE)
        self.assertEqual(proof['stub_method_sha256'],raw['method_sha256'])

    def test_no_lambda_name_allowlist(self):
        raw,f,t,c=fixture()
        self.assertNotIn('Lambda',f['class'])
        self.assertEqual(validate_stub(raw,f,t,c,{})['host_class'],CANDIDATE)

    def test_forged_lambda_extra_logic_fails_even_with_fresh_hashes(self):
        raw,f,t,c=fixture()
        for extra in (b'\x03\x57',b'\x00',b'\xa7\x00\x03',b'\x59',b'\xc0\x00\x01'):
            with self.subTest(extra=extra):
                r=copy.deepcopy(raw); frame=dict(f)
                data=extra+bytes.fromhex(r['bytecode_hex'])
                r['bytecode_hex']=data.hex();r['method_sha256']=hashlib.sha256(data).hexdigest()
                frame['method_sha256']=r['method_sha256']
                with self.assertRaises(EvidenceFailure): validate_stub(r,frame,t,c,{})

    def test_wrong_host_loader_missing_or_nonadjacent_target(self):
        raw,f,t,c=fixture()
        for change in ('host','loader','missing','method','pool','code'):
            with self.subTest(change=change):
                target=dict(t)
                if change=='host': target['class']='outside.Helper'
                elif change=='loader': target['loader']='78'
                elif change=='missing': target=None
                elif change=='method': target['method']='different'
                elif change=='pool': target['constant_pool_sha256']='d'*64
                else: target['method_sha256']='e'*64
                with self.assertRaises(EvidenceFailure): validate_stub(raw,f,target,c,{})

    def test_unbound_host_fails(self):
        raw,f,t,c=fixture()
        with self.assertRaisesRegex(EvidenceFailure,'host-unbound'): validate_stub(raw,f,t,{},{})

    def test_framework_requires_verified_jar_entry(self):
        raw,f,t,c=fixture('org.junit.example.Host')
        with self.assertRaisesRegex(EvidenceFailure,'jar-entry'):validate_stub(raw,f,t,c,{})
        entries={t['class']:{'entry_sha256':'d'*64}}
        with self.assertRaisesRegex(EvidenceFailure,'jar-entry'):validate_stub(raw,f,t,c,entries)
        entries[t['class']]['entry_sha256']='c'*64
        self.assertEqual(validate_stub(raw,f,t,c,entries)['host_class'],t['class'])

    def test_modified_raw_bytes_and_truncated_pool_fail(self):
        raw,f,t,c=fixture()
        for field in ('constant_pool_hex','bytecode_hex'):
            r=copy.deepcopy(raw);r[field]+='00'
            with self.assertRaises(EvidenceFailure):validate_stub(r,f,t,c,{})
        r=copy.deepcopy(raw);r['constant_pool_count']+=1
        with self.assertRaises(EvidenceFailure):definition(r)

    def test_synchronization_or_nonhidden_definition_fails(self):
        raw,f,t,c=fixture()
        for key,value in (('method_modifiers',0x21),('class_modifiers',0x10)):
            r=copy.deepcopy(raw);r[key]=value
            with self.assertRaises(EvidenceFailure):validate_stub(r,f,t,c,{})

    def test_binding_uses_immediately_younger_frame_and_candidate_origin(self):
        raw,f,t,c=fixture()
        # A host frame definition is needed for all frames, even ordinary ones.
        defs={raw['definition_id']:raw, t['definition_id']:t}
        # Body-only synthetic frames no longer establish generation provenance.
        with self.assertRaisesRegex(EvidenceFailure,'generation-provenance-missing'):
            checked_frames({'frames':[t,f]},c,{},defs,
                           {'policy':'exact-forwarding-stub-v1','adjacent_target':'younger'}, {})
        with self.assertRaisesRegex(EvidenceFailure,'missing-adjacent'):
            checked_frames({'frames':[f,t]},c,{},defs,
                           {'policy':'exact-forwarding-stub-v1','adjacent_target':'younger'}, {})

    def test_asserted_host_is_removed_before_origin(self):
        frame={'class':'outside.Helper','method':'run','signature':'()V','loader':'1',
               '_verified_forwarding_host':CANDIDATE}
        frames=checked_frames({'frames':[{'class':'outside.Top'},frame]}, {}, {})
        self.assertEqual(origin(frames),'outside')

    def test_receipt_census_retains_raw_stub_identity_and_both_neighbours(self):
        raw,f,t,c=fixture()
        records=[seal({'event':{'kind':'frame-definition','definition':raw}}),
                 seal({'event':{'kind':'exception','frames':[t,f]}})]
        census=receipt_records(records)
        self.assertEqual(census['definitions']['test:stub']['method_sha256'],raw['method_sha256'])
        item=next(iter(census['generated_adjacencies'].values()))
        self.assertEqual(item['observed_neighbours']['younger']['class'],CANDIDATE)
        self.assertIsNone(item['observed_neighbours']['older'])
        self.assertFalse(item['host_verified'])

    def test_offline_stream_rechecks_receipt_census_and_adjacent_host(self):
        raw,f,t,c=fixture()
        host={**raw,'definition_id':t['definition_id'],'class':t['class'],
              'class_signature':'L'+t['class'].replace('.','/')+';', 'method':t['method'],
              'signature':t['signature'],'bytecode_hex':'01b0',
              'method_sha256':hashlib.sha256(bytes.fromhex('01b0')).hexdigest()}
        t['constant_pool_sha256']=host['constant_pool_sha256']; t['method_sha256']=host['method_sha256']
        c[CANDIDATE]['constant_pool_sha256']=host['constant_pool_sha256']
        c[CANDIDATE]['methods'][t['method']+t['signature']]=host['method_sha256']
        events=[{'kind':'ready','checkpoint':False},
                {'kind':'frame-definition','definition':host,'checkpoint':False},
                {'kind':'frame-definition','definition':raw,'checkpoint':False},
                {'kind':'exception','checkpoint':True,'thread':1,'frames':[t,f],
                 'exception_class':'java.lang.NullPointerException',
                 'exception_ancestry':['java.lang.NullPointerException','java.lang.Object'],
                 'unwound_calls':[],'catch_location':None},
                {'kind':'vm-death','checkpoint':False}]
        records=[];previous=None
        for i,event in enumerate(events,1):
            item=seal({'event':{**event,'sequence':i},'previous_sha256':previous,'readback_sha256':None})
            records.append(item);previous=item['content_sha256']
        data=b'\n'.join(canonical(x) for x in records)+b'\n'
        receipt={'event_file_sha256':hashlib.sha256(data).hexdigest(),'event_count':len(records),
                 'last_event_sha256':previous,'frame_records':receipt_records(records)}
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); (folder/'events.jsonl').write_bytes(data)
            policy={'policy':'exact-forwarding-stub-v1','adjacent_target':'younger'}
            with self.assertRaisesRegex(EvidenceFailure,'generation-provenance-missing'):
                replay_stream(folder,receipt,c,'oracle',policy,{})
            broken=copy.deepcopy(receipt);broken['frame_records']['generated_adjacencies']={}
            with self.assertRaisesRegex(EvidenceFailure,'signed-frame-records'):
                replay_stream(folder,broken,c,'oracle',policy,{})
            with self.assertRaises(EvidenceFailure):
                replay_stream(folder,receipt,c,'oracle')  # no policy silently opted in


if __name__=='__main__':unittest.main()
