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

    def test_direct_writer_cannot_bypass_live_overlap_or_journal_guard(self):
        from lightyear_control_tower.factory_policy import write_request
        contract=self.fixture.contract('equivalence-review')
        before={p.relative_to(self.fixture.root).as_posix():p.read_bytes()
                for p in self.fixture.root.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError,'trusted-journal-required'):
            write_request(self.fixture.root,contract)
        self.assertEqual(before,{p.relative_to(self.fixture.root).as_posix():p.read_bytes()
                                 for p in self.fixture.root.rglob('*') if p.is_file()})
        request=write_request(self.fixture.root,contract,**self.trust())
        self.assertEqual(request,write_request(self.fixture.root,contract,**self.trust()))
        before={p.relative_to(self.fixture.root).as_posix():p.read_bytes()
                for p in self.fixture.root.rglob('*') if p.is_file()}
        successor=copy.deepcopy(contract);successor['details']['items']=['mutant-2','new']
        with self.assertRaisesRegex(ValueError,'live-overlap'):
            write_request(self.fixture.root,successor,**self.trust())
        self.assertEqual(before,{p.relative_to(self.fixture.root).as_posix():p.read_bytes()
                                 for p in self.fixture.root.rglob('*') if p.is_file()})

    def test_live_subset_superset_and_partial_overlap_refused_before_writes(self):
        repo, contract, _ = self.repo_contract()
        target = self.base / 'live'
        imported = import_request(repo, target, contract, **self.trust())
        before = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob('*') if p.is_file()}
        self.assertEqual(imported, import_request(repo, target, contract, **self.trust()))
        for items in (['mutant-1'], ['mutant-1', 'mutant-2', 'extra'], ['mutant-2', 'extra']):
            with self.subTest(items=items):
                successor = copy.deepcopy(contract)
                successor['details']['items'] = items
                with self.assertRaisesRegex(ValueError, 'live-overlap'):
                    import_request(repo, target, successor, **self.trust())
                self.assertEqual(before, {p.relative_to(target).as_posix(): p.read_bytes()
                                          for p in target.rglob('*') if p.is_file()})
        disjoint = copy.deepcopy(contract);disjoint['details']['items'] = ['disjoint']
        import_request(repo, target, disjoint, **self.trust())
        other = copy.deepcopy(contract);other['program'] = 'INTCALC'
        import_request(repo, target, other, **self.trust())

    def test_decided_partial_overlap_and_complete_multi_predecessor_record(self):
        repo, contract, git = self.repo_contract()
        proof, _, _ = self.fixture.decide(contract)
        target = self.base / 'overlap'
        live = copy.deepcopy(contract);live['details']['items'] = ['live-only']
        import_request(repo, target, live, **self.trust())
        successor = copy.deepcopy(contract);successor['details']['items'] = ['mutant-2', 'live-only']
        self.assert_no_write(successor, 'already-decided', repository=repo, **self.trust())
        from lightyear_control_tower.factory_supersessions import predecessor_row
        predecessors = sorted([predecessor_row(contract, 'decided', proof['decision_sha256']),
                               predecessor_row(live, 'live')], key=lambda r: (r['state'], r['request_sha256']))
        path = 'docs/factory/appl-result-supersession-2026-10-20-fixture.json'
        record = dict(schema='appl-result-content-supersession/2', prepared_on='2026-10-20',
                      program=contract['program'], item_set_sha256=identity(successor),
                      successor_contract_sha256=normalized_hash(successor), predecessors=predecessors)
        def bind(row):
            (repo/path).write_bytes(canonical(row));git('add', '.');git('commit', '-m', 'Unsigned CI supersession')
            value = copy.deepcopy(successor)
            ref = dict(path=path,sha256=sha256((repo/path).read_bytes()).hexdigest(),
                       commit=git('rev-parse','HEAD').decode().strip())
            value['supersession']=ref;value['sources'].append(ref)
            return value
        before={p.relative_to(target).as_posix():p.read_bytes() for p in target.rglob('*') if p.is_file()}
        for variant in ('missing', 'stale'):
            bad=copy.deepcopy(record)
            if variant=='missing':bad['predecessors'].pop()
            else:bad['predecessors'][0]['decision_sha256']='f'*64
            with self.assertRaisesRegex(ValueError,'supersession-content-binding'):
                import_request(repo,target,bind(bad),**self.trust())
            self.assertEqual(before,{p.relative_to(target).as_posix():p.read_bytes() for p in target.rglob('*') if p.is_file()})
        accepted=bind(record)
        request=import_request(repo,target,accepted,**self.trust())
        self.assertEqual('factory-'+digest(accepted),request['id'])
        self.assertEqual(request,import_request(repo,target,accepted,**self.trust()))

    def test_selection_text_changes_with_input_and_documents_agree(self):
        record=appl_contract_selection.load(ROOT);text=appl_contract_selection.markdown(record)
        for path in ['docs/factory/appl-result-signing-2026-10-18.md',
                     'docs/factory/howard-decision-packet-2026-10-18-appl-selection.md']:
            self.assertIn(text,(ROOT/path).read_text(encoding='utf-8'))
        for field,value in [('members',999),('review_required',False),('class_proof_sha256','f'*64),('reason','Changed input explanation')]:
            changed=copy.deepcopy(record);changed['records'][0][field]=value
            self.assertNotEqual(text,appl_contract_selection.markdown(changed))
        from tools.release_status_records import load,render
        model=load(ROOT);before=render(model)
        self.assertIn(text, before[1])  # Current output is rendered in CI, never assumed committed.
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

    def test_status_input_inventory_contains_the_selected_contract_bytes(self):
        from tools.release_status_records import inputs
        record=appl_contract_selection.load(ROOT);paths=inputs(ROOT)
        self.assertIn(appl_contract_selection.PATH,paths)
        for row in record['records']:self.assertIn(row['path'],paths)


    def test_intake_selection_requires_committed_record_and_contract_bytes(self):
        from lightyear_control_tower.factory_selection import load_selection
        repo, _, git = self.repo_contract()
        record = appl_contract_selection.load(ROOT)
        selected_path = 'docs/factory/appl-result-contract-selection-' + record['prepared_on'] + '.json'
        for name in [selected_path, *[r['path'] for r in record['records']]]:
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        git('add', '.');git('commit', '-m', 'Unsigned selection fixture')
        self.assertEqual(record, load_selection(repo, committed_only=True))
        (repo / selected_path).unlink()
        with self.assertRaisesRegex(ValueError, 'selection-uncommitted'):
            load_selection(repo, committed_only=True)
        (repo / selected_path).write_bytes((ROOT / selected_path).read_bytes())
        later = copy.deepcopy(record);later['prepared_on'] = '2099-01-01'
        later_path = repo / 'docs/factory/appl-result-contract-selection-2099-01-01.json'
        later_path.write_bytes(canonical(later))
        with self.assertRaisesRegex(ValueError, 'selection-uncommitted'):
            load_selection(repo, committed_only=True)
        later_path.unlink()
        changed = copy.deepcopy(record);changed['records'][0]['reason'] = 'Uncommitted selection'
        (repo / selected_path).write_bytes(canonical(changed))
        with self.assertRaisesRegex(ValueError, 'selection-uncommitted'):
            load_selection(repo, committed_only=True)
        (repo / selected_path).write_bytes((ROOT / selected_path).read_bytes())
        row = record['records'][0]
        contract = json.loads((repo / row['path']).read_bytes())
        contract['details']['reviewer_type'] = 'human' if contract['details']['reviewer_type'] == 'AI-assisted' else 'AI-assisted'
        (repo / row['path']).write_bytes(canonical(contract))
        with self.assertRaisesRegex(ValueError, 'selection-uncommitted'):
            load_selection(repo, committed_only=True)

    def test_guide_links_follow_selected_record_date(self):
        from tools.release_status_records import load, render
        model = load(ROOT)
        model['appl_contract_selection']['prepared_on'] = '2026-10-20'
        text = render(model)[1]
        self.assertIn('(appl-result-signing-2026-10-20.md)', text)
        self.assertIn('(howard-decision-packet-2026-10-20-appl-selection.md)', text)


class OrderedReviewPacketTests(unittest.TestCase):
    """Validate the unsigned review aid against retained evidence in CI only."""
    PACKET = 'docs/factory/appl-result-ordered-review-2026-10-20/INTCALC/unsigned-review.json'

    def test_selected_ordered_review_sample_has_exact_source_bindings(self):
        raw = (ROOT / self.PACKET).read_bytes()
        self.assertLess(len(raw), 50000)
        packet = json.loads(raw)
        seal = packet.pop('content_sha256')
        self.assertEqual(seal, digest(packet))
        self.assertEqual('unsigned-ordered-class-review/1', packet['schema'])
        self.assertEqual('unsigned', packet['signature_status'])
        for field in ('review_completed', 'execution_authorized', 'qualification_credit'):
            self.assertIs(False, packet[field])
        selected = appl_contract_selection.load(ROOT)
        row = next(r for r in selected['records'] if r['program'] == 'INTCALC')
        self.assertEqual(row, packet['selected_contract'])
        contract_raw = (ROOT / row['path']).read_bytes()
        self.assertEqual(row['file_sha256'], sha256(contract_raw).hexdigest())
        contract = json.loads(contract_raw)
        self.assertEqual(contract['details']['packet_sha256'], packet['ordered_packet_sha256'])
        self.assertEqual(contract['details']['class_proof_sha256'], packet['ordered_class_proof_sha256'])

        def blob(path, commit=packet['binding_commit']):
            return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)

        self.assertEqual(packet['selection']['sha256'], sha256(blob(packet['selection']['path'])).hexdigest())
        for ref in contract['sources']:
            self.assertEqual(ref['sha256'], sha256(blob(ref['path'], ref['commit'])).hexdigest())
        census_ref = packet['reference_census']
        census_raw = blob(census_ref['path'])
        self.assertEqual(census_ref['file_sha256'], sha256(census_raw).hexdigest())
        census = json.loads(census_raw)
        census_seal = census.pop('content_sha256')
        self.assertEqual(census_seal, digest(census))
        self.assertEqual(census_seal, packet['ordered_class_proof_sha256'])
        self.assertEqual(census_seal, census_ref['content_sha256'])
        self.assertTrue(census['passed'])
        self.assertEqual([], census['raw_consumers'])
        source = blob(packet['source']['path'])
        self.assertEqual(census['source_sha256'], sha256(source).hexdigest())
        self.assertEqual(packet['source']['sha256'], sha256(source).hexdigest())
        source_lines = source.decode().splitlines()
        evidence = packet['member_evidence']
        self.assertEqual(contract['sources'][0], evidence)
        results = {r['id']: r for r in json.loads(blob(evidence['path'], evidence['commit']))}
        matches_ref = packet['historical_match_comparison']
        matches_raw = blob(matches_ref['path'])
        self.assertEqual(matches_ref['sha256'], sha256(matches_raw).hexdigest())
        matches = json.loads(matches_raw)['matches']
        members = sorted(contract['details']['items'])
        self.assertEqual(81, len(set(members)))
        self.assertEqual(members, packet['members'])
        self.assertEqual(set(members), set(matches))
        for mid in members:
            self.assertEqual(matches[mid]['mutant_sha256'], digest(results[mid]['mutant']))
            self.assertEqual(census_seal, matches[mid]['census_sha256'])
        seed = row['template_queue_sha256'] + ':' + census_seal
        self.assertEqual(seed, packet['sample_seed'])
        expected = sorted(members, key=lambda mid: sha256((seed + ':' + mid).encode()).hexdigest())[:30]
        self.assertEqual(30, packet['sample_size'])
        self.assertEqual(expected, [s['id'] for s in packet['sample']])
        contexts = set()
        for sample in packet['sample']:
            result = results[sample['id']]
            mutant, argument = result['mutant'], result['argument']
            self.assertEqual(digest(mutant), sample['mutant_sha256'])
            self.assertEqual(digest(argument), sample['argument_sha256'])
            self.assertEqual(argument['argument'], sample['argument'])
            self.assertEqual(mutant['original'], source_lines[mutant['line'] - 1])
            self.assertEqual(mutant['original'].rstrip(), sample['original'])
            self.assertEqual(mutant['replacement'].rstrip(), sample['replacement'])
            locations = sorted(set(argument['supporting_source_lines'] + [argument['source_line']]))
            self.assertEqual(locations, sample['source_context_lines'])
            contexts.update(locations)
        self.assertEqual([dict(line=n, text=source_lines[n-1].rstrip()) for n in sorted(contexts)], packet['source_context'])
