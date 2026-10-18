"""CI-only CLI rehearsal with disposable authority and synthetic request bodies."""
import copy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from tests import test_decision_console_factory as fixtures
from lightyear_control_tower.decisions import canonical,digest
from lightyear_control_tower.factory_order import body_hash
from tools.bind_next_intcalc_request import templates,ROOT

class BindNextTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.FactoryTests('runTest');self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.service.grant_roles('howard',['operator','qualification-approver','business-owner','campaign-authorizer'],
            reason='Disposable CI only',workloads=['factory:INTCALC','factory:factory'])
        self.base=Path(self.fixture.temp.name);self.repo=self.base/'repo';self.repo.mkdir()
        contracts=[]
        for position in range(1,7):
            c=self.fixture.contract('equivalence-review');c['program']='INTCALC'
            c['details']['items']=[f'CI-round-{position}'];contracts.append(c)
        hashes=[body_hash(c) for c in contracts];packet=digest(hashes);rows=[]
        for position,c in enumerate(contracts,1):
            c['signing_order']=dict(packet_sha256=packet,position=position,
                predecessor_contract_sha256=hashes[position-2] if position>1 else None,predecessor_decision_sha256=None)
            raw=canonical(c);path=f'round-{position}.json';(self.repo/path).write_bytes(raw)
            rows.append(dict(order=position,path=path,sha256=sha256(raw).hexdigest(),kind=c['kind']))
        (self.repo/'packet.json').write_text(json.dumps(dict(schema='factory-unsigned-signing-order/1',program='INTCALC',signed=False,items=rows)),encoding='utf-8')
        self.public=self.base/'public.pem';self.public.write_bytes(self.fixture.service.public_key)

    def command(self,proof,position,output,*,head=None):
        path=self.base/'proof.json';path.write_text(json.dumps(proof),encoding='utf-8')
        journal=proof.get('journal',proof)
        env=dict(os.environ,PYTHONPATH=str(ROOT/'src')+os.pathsep+str(ROOT))
        return subprocess.run([sys.executable,'-B','-m','tools.bind_next_intcalc_request','--proof',str(path),
            '--public-key',str(self.public),'--trusted-head',head or journal['journal_head_sha256'],
            '--position',str(position),'--output',str(output),'--repository',str(self.repo),'--packet','packet.json'],
            cwd=ROOT,env=env,capture_output=True,text=True)

    def test_all_six_rounds_through_cli_and_skipped_position_refused(self):
        proof=self.fixture.service.export_session(self.fixture.token)
        for position in range(1,7):
            output=self.base/f'output-{position}'
            result=self.command(proof,position,output);self.assertEqual(0,result.returncode,result.stderr)
            receipt=json.loads(result.stdout);raw=Path(receipt['path']).read_bytes();contract=json.loads(raw)
            self.assertEqual(sha256(raw).hexdigest(),receipt['file_sha256'])
            self.assertEqual('factory-'+digest(contract),receipt['queue_id']);self.assertFalse(receipt['signed'])
            proof,_,_=self.fixture.decide(contract)
            if position<5:
                refused=self.base/f'skip-{position}'
                self.assertNotEqual(0,self.command(proof,position+2,refused).returncode)
                self.assertFalse(refused.exists())
        self.assertEqual(6,contract['signing_order']['position'])
        self.assertNotEqual(0,self.command(proof,6,self.base/'output-6').returncode)

    def test_wrong_head_tampered_proof_private_key_and_packet_refused_without_output(self):
        journal=self.fixture.service.export_session(self.fixture.token)
        output=self.base/'refused'
        self.assertNotEqual(0,self.command(journal,1,output,head='e'*64).returncode)
        changed=copy.deepcopy(journal);changed['journal_head_sha256']='f'*64
        self.assertNotEqual(0,self.command(changed,1,output).returncode)
        self.public.write_bytes(b'-----BEGIN PRIVATE KEY-----')
        self.assertNotEqual(0,self.command(journal,1,output).returncode)
        self.public.write_bytes(self.fixture.service.public_key)
        (self.repo/'round-1.json').write_bytes(b'{}')
        self.assertNotEqual(0,self.command(journal,1,output).returncode)
        self.assertFalse(output.exists())

    def test_committed_templates_are_verified_without_claiming_final_conditions_met(self):
        contracts=templates(ROOT,'docs/factory/intcalc-signing-order-2026-10-17.json')
        self.assertEqual(6,len(contracts));self.assertEqual('unconditional',contracts[-1]['details']['effective_condition'])
        self.assertTrue(any(r['state']=='not-met' for r in contracts[-1]['details']['conditions']))
