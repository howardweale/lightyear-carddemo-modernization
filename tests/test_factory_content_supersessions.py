"""CI-only disposable-journal tests; never touches installed Factory state."""
import copy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from tests import test_decision_console_factory as fixtures
from lightyear_control_tower.decisions import canonical, digest
from lightyear_control_tower.factory_import import import_request
from lightyear_control_tower.factory_order import bind_predecessor
from lightyear_control_tower.factory_supersessions import identity, normalized_hash
from tools import appl_contract_selection

ROOT=Path(__file__).resolve().parents[1]

class ContentSupersessionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.FactoryTests('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.base=Path(self.fixture.temp.name)

    def trust(self):
        journal=self.fixture.service.export_session(self.fixture.token)
        return dict(journal=journal,public_key=self.fixture.service.public_key,
                    trusted_head=journal['journal_head_sha256'])

    def assert_no_write(self,contract,pattern,repository=ROOT,**trust):
        target=self.base/'refused'
        with self.assertRaisesRegex(ValueError,pattern):
            import_request(repository,target,contract,**trust)
        self.assertFalse(target.exists())

    def test_retired_and_changed_serialized_same_item_set_refused(self):
        contract=json.loads((ROOT/'docs/factory/appl-result-signing-2026-10-16/INTCALC/contract.json').read_bytes())
        self.assert_no_write(contract,'superseded-content',**self.trust())
        for field,value in [('packet_sha256','e'*64),('reviewer_type','AI-assisted'),('claim_scope','zos-facing')]:
            bad=json.loads(json.dumps(contract,indent=4));bad['details'][field]=value
            bad['details']['items'].reverse()
            self.assert_no_write(bad,'superseded-content',**self.trust())
        chosen=json.loads((ROOT/'docs/factory/intcalc-02-appl-result-class-request-2026-10-17.json').read_bytes())
        chosen['details']['packet_sha256']='d'*64
        self.assert_no_write(chosen,'superseded-content',**self.trust())

    def test_actual_selected_contracts_import_and_order_is_still_required(self):
        selection=appl_contract_selection.load(ROOT)
        for row in selection['records']:
            contract=json.loads((ROOT/row['path']).read_bytes())
            if row['program']=='INTCALC':
                self.assert_no_write(contract,'signing-order-predecessor-required',**self.trust())
                self.fixture.service.grant_roles('howard',['operator','qualification-approver','business-owner','campaign-authorizer'],
                    reason='Disposable CI only',workloads=['factory:INTCALC','factory:POSTTRAN','factory:factory'])
                previous=json.loads((ROOT/'docs/factory/intcalc-01-loader-domain-request-2026-10-17.json').read_bytes())
                for source in previous['sources']:
                    dest=self.fixture.root/source['path'];dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(ROOT/source['path'],dest)
                proof,_,_=self.fixture.decide(previous)
                contract=bind_predecessor(contract,proof)
                self.assertNotEqual(row['template_queue_sha256'],digest(contract))
                self.assertEqual(row['normalized_contract_sha256'],normalized_hash(contract))
            target=self.base/row['program']
            item=import_request(ROOT,target,contract,**self.trust())
            self.assertEqual('factory-'+digest(contract),item['id'])
            self.assertEqual(item,import_request(ROOT,target,contract,**self.trust()))
            for source in contract['sources']:
                self.assertEqual(source['sha256'],sha256((target/source['path']).read_bytes()).hexdigest())

    def repo_contract(self):
        repo=self.base/'repo';repo.mkdir()
        def git(*args):
            return subprocess.check_output(['git','-c','core.autocrlf=false','-c','commit.gpgsign=false',
                '-c','user.name=CI','-c','user.email=ci@example.invalid',*args],cwd=repo)
        git('init')
        path='docs/factory/public.json';dest=repo/path;dest.parent.mkdir(parents=True)
        dest.write_bytes(self.fixture.source.read_bytes())
        git('add','.');git('commit','-m','Synthetic public CI evidence')
        contract=self.fixture.contract('equivalence-review')
        contract['sources'][0]['commit']=git('rev-parse','HEAD').decode().strip()
        return repo,contract,git

    def test_missing_wrong_and_stale_external_trust_refused(self):
        repo,contract,_=self.repo_contract()
        self.assert_no_write(contract,'trusted-journal-required',repository=repo)
        trust=self.trust();trust['trusted_head']='e'*64
        self.assert_no_write(contract,'.',repository=repo,**trust)
        trust=self.trust();trust['public_key']=b'not a public key'
        self.assert_no_write(contract,'.',repository=repo,**trust)
        old=self.trust();self.fixture.decide(contract)
        old['trusted_head']=self.trust()['trusted_head']
        self.assert_no_write(contract,'.',repository=repo,**old)

    def test_decided_item_set_requires_committed_dated_successor(self):
        repo,contract,git=self.repo_contract()
        proof,_,_=self.fixture.decide(contract)
        successor=copy.deepcopy(contract);successor['details']['reviewer_type']='AI-assisted'
        self.assert_no_write(successor,'already-decided',repository=repo,**self.trust())
        path='docs/factory/appl-result-supersession-2026-10-18-fixture.json'
        record=dict(schema='appl-result-content-supersession/1',prepared_on='2026-10-18',program=contract['program'],
            item_set_sha256=identity(contract),predecessor_contract_sha256=normalized_hash(contract),
            successor_contract_sha256=normalized_hash(successor),predecessor_decision_sha256=proof['decision_sha256'])
        (repo/path).write_bytes(canonical(record));git('add','.');git('commit','-m','Unsigned CI successor record')
        ref=dict(path=path,sha256=sha256((repo/path).read_bytes()).hexdigest(),commit=git('rev-parse','HEAD').decode().strip())
        successor['supersession']=ref;successor['sources'].append(ref)
        request=import_request(repo,self.base/'successor',successor,**self.trust())
        self.assertEqual('factory-'+digest(successor),request['id'])
        for field,value in [('reviewer_type','human'),('packet_sha256','c'*64)]:
            bad=copy.deepcopy(successor);bad['details'][field]=value
            self.assert_no_write(bad,'supersession-content-binding',repository=repo,**self.trust())
        bad=copy.deepcopy(successor);bad['supersession']['sha256']='0'*64
        # Deepcopy retains the shared reference in both fields.
        self.assert_no_write(bad,'supersession-file-hash',repository=repo,**self.trust())
        record['prepared_on']='2026-10-17'
        (repo/path).write_bytes(canonical(record));git('add','.');git('commit','-m','Invalid date fixture')
        ref.update(sha256=sha256((repo/path).read_bytes()).hexdigest(),commit=git('rev-parse','HEAD').decode().strip())
        self.assert_no_write(successor,'supersession-content-binding',repository=repo,**self.trust())

    def test_selection_text_changes_with_input_and_documents_agree(self):
        record=appl_contract_selection.load(ROOT);text=appl_contract_selection.markdown(record)
        for path in ['docs/factory/current-status.md','docs/factory/appl-result-signing-2026-10-18.md',
                     'docs/factory/howard-decision-packet-2026-10-18-appl-selection.md']:
            self.assertIn(text,(ROOT/path).read_text(encoding='utf-8'))
        for field,value in [('members',999),('review_required',False),('class_proof_sha256','f'*64),('reason','Changed input explanation')]:
            changed=copy.deepcopy(record);changed['records'][0][field]=value
            self.assertNotEqual(text,appl_contract_selection.markdown(changed))
        from tools.release_status_records import load,render
        model=load(ROOT);before=render(model)
        model['appl_contract_selection']['records'][0]['reason']='Changed selection'
        self.assertNotEqual(before[1],render(model)[1])
        from tools.build_release_packet import build
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'docs/factory').mkdir(parents=True)
            with patch('tools.build_release_packet.load',return_value=model):build(root=root)
            self.assertIn('Changed selection',next((root/'docs/factory').glob('howard-decision-packet-*.md')).read_text(encoding='utf-8'))

    def test_status_overlay_preserves_selected_contract_and_packet_bytes(self):
        from tools.render_oct16_status import overlay_projections
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'root';out=Path(temp)/'generated';out.mkdir()
            folder=root/'docs/factory';folder.mkdir(parents=True)
            (folder/'appl-result-contract-selection-2026-10-18.json').write_text('{}')
            names=['intcalc-02-appl-result-class-request-2026-10-17.json','intcalc-signing-order-2026-10-17.json']
            for name in names:
                (folder/name).write_bytes(b'committed selected bytes');(out/name).write_bytes(b'rebound rehearsal bytes')
            (out/'intcalc-review-verdict-2026-10-17.json').write_bytes(b'new measured projection')
            overlay_projections(out,root)
            for name in names:self.assertEqual(b'committed selected bytes',(folder/name).read_bytes())
            self.assertEqual(b'new measured projection',(folder/'intcalc-review-verdict-2026-10-17.json').read_bytes())
