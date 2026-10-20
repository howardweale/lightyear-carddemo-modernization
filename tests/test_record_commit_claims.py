from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.check_record_commit_claims import check,validate_claim,CLAIMS,resolve,references


class RecordCommitTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.git('init','-q');self.git('config','user.email','fixture@example.invalid');self.git('config','user.name','CI fixture')
        (self.root/'source.txt').write_bytes(b'original\n');self.commit('baseline')
        self.base=self.git('rev-parse','HEAD').strip()
        self.claim=dict(reference=self.base,commit=self.base,role='source',source_path='source.txt',
                        source_sha256=sha256(b'original\n').hexdigest())

    def git(self,*args):
        return subprocess.check_output(['git','-c','commit.gpgsign=false',*args],cwd=self.root,text=True)

    def commit(self,message):
        self.git('add','.');self.git('commit','-qm',message)

    def test_resolves_and_verifies_source_bytes(self):
        self.assertEqual(self.base,validate_claim(self.root,self.claim))
        with self.assertRaisesRegex(ValueError,'source-mismatch'):
            validate_claim(self.root,dict(self.claim,source_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'unresolved'):resolve(self.root,'f'*40)
        with self.assertRaisesRegex(ValueError,'merge-parents'):
            validate_claim(self.root,dict(self.claim,role='merge',parents=[],head_commit=self.base,pr=1))

    def test_new_record_requires_specific_claim_and_historical_record_is_untouched(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        (directory/'preserved-2026-10-16.md').write_text('Historical unresolved `ffffffff`.\n')
        self.commit('preserved historical record')
        baseline=self.git('rev-parse','HEAD').strip()
        name='docs/factory/receipt-2026-10-17.md'
        (self.root/name).write_text('Source revision `'+self.base+'`.\n')
        self.commit('new records')
        with self.assertRaisesRegex(ValueError,'claim-required'):check(self.root,baseline)
        (self.root/CLAIMS).write_text(json.dumps(dict(claims=[dict(self.claim,record=name)])))
        self.commit('bound source claim')
        self.assertEqual(1,len(check(self.root,baseline)))

    def test_resolving_wrong_commit_does_not_validate_claim(self):
        (self.root/'source.txt').write_bytes(b'different\n');self.commit('changed source')
        head=self.git('rev-parse','HEAD').strip()
        with self.assertRaisesRegex(ValueError,'source-mismatch'):
            validate_claim(self.root,dict(self.claim,reference=head,commit=head))

    def test_full_content_hash_and_its_short_prefix_are_not_commit_claims(self):
        content='abcdef12'+'3'*56
        self.assertEqual(set(),references([content]))
        self.assertEqual(set(),references(['Evidence digest `abcdef12`.']))
        self.assertEqual(set(),references(['Archive `abcdef12`.'],record='SHA-256: '+content))
        self.assertEqual({'abcdef12'},references(['Commit `abcdef12`.'],record='SHA-256: '+content))
        self.assertEqual({'deadbeef'},references(['SHA-256: '+content+'; head `deadbeef`.']))
        self.assertEqual({'abcdef12'},references(['Unlabelled revision `abcdef12`.']))

    def test_new_past_dated_record_still_requires_a_claim(self):
        name='docs/factory/new-record-2020-01-01.md'
        (self.root/name).parent.mkdir(parents=True)
        (self.root/name).write_text('Source commit `'+self.base+'`.\n')
        self.commit('new record with old date')
        with self.assertRaisesRegex(ValueError,'claim-required'):
            check(self.root,self.base)
        (self.root/CLAIMS).write_text(json.dumps(dict(claims=[dict(self.claim,record=name)])))
        self.commit('bind source')
        self.assertEqual(1,len(check(self.root,self.base)))

    def test_hash_prefix_record_does_not_need_git_resolution(self):
        name='docs/factory/hash-record-2020-01-01.json'
        (self.root/name).parent.mkdir(parents=True)
        (self.root/name).write_text(json.dumps({'sha256':'abcdef12'+'3'*56,'display':'abcdef12'}))
        self.commit('content hash record')
        self.assertEqual([],check(self.root,self.base))


    def test_publication_role_binds_snapshot_bytes_without_source_claim(self):
        claim=dict(reference=self.base,commit=self.base,role='publication',publication_path='source.txt',
                   publication_sha256=sha256(b'original\n').hexdigest())
        self.assertEqual(self.base,validate_claim(self.root,claim))
        with self.assertRaisesRegex(ValueError,'source-mismatch'):
            validate_claim(self.root,dict(claim,publication_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'source-path'):
            validate_claim(self.root,dict(claim,publication_path='../outside'))

    def test_dated_role_correction_preserves_registry_and_cannot_change_evidence(self):
        from tools.check_record_commit_claims import ROLE_CORRECTIONS,current_claims
        old=dict(self.claim,record='docs/factory/old.json')
        registry=self.root/CLAIMS;registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({'claims':[old]}));before=registry.read_bytes()
        new={k:v for k,v in old.items() if k not in ('role','source_path','source_sha256')}
        new.update(role='publication',publication_path=old['source_path'],publication_sha256=old['source_sha256'])
        correction=dict(record=old['record'],reference=old['reference'],
                        previous_claim_sha256=sha256(json.dumps(old,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                        replacement=new)
        data=dict(schema='record-commit-role-corrections/1',prepared_on='2026-10-18',corrections=[correction])
        path=self.root/ROLE_CORRECTIONS;path.write_text(json.dumps(data))
        self.assertEqual([new],current_claims(self.root));self.assertEqual(before,registry.read_bytes())
        new['publication_sha256']='0'*64;path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'changes-evidence'):current_claims(self.root)
        new['publication_sha256']=old['source_sha256'];correction['previous_claim_sha256']='0'*64
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'correction-binding'):current_claims(self.root)

    def test_new_dated_manifest_preserves_old_and_checks_changed_inputs(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        name='docs/factory/current-status.json'
        (self.root/name).write_text(json.dumps({'source':self.base}))
        original=json.dumps({'claims':[]}).encode()
        (self.root/CLAIMS).write_bytes(original)
        newer=directory/'commit-claims-2026-10-19.json'
        newer.write_text(json.dumps({'claims':[dict(self.claim,record=name)]}))
        self.commit('new dated claims')
        self.assertEqual(1,len(check(self.root,self.base)))
        self.assertEqual(original,(self.root/CLAIMS).read_bytes())
        newer.write_text(json.dumps({'claims':[dict(self.claim,record=name,source_sha256='0'*64)]}))
        self.commit('wrong new claim')
        with self.assertRaisesRegex(ValueError,'source-mismatch'):check(self.root,self.base)


    def test_duplicate_claim_across_dated_manifests_is_refused(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        name='docs/factory/current-status.json'
        (self.root/name).write_text(json.dumps({'source':self.base}))
        content=json.dumps({'claims':[dict(self.claim,record=name)]})
        (self.root/CLAIMS).write_text(content)
        (directory/'commit-claims-2026-10-19.json').write_text(content)
        self.commit('ambiguous claim')
        with self.assertRaisesRegex(ValueError,'claim-required'):check(self.root,self.base)


    def test_non_dated_registry_is_read_and_checked_without_prose_change(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        registry=directory/'commit-claims-additional.json'
        registry.write_text(json.dumps({'claims':[dict(self.claim,record='docs/factory/old.md')]}))
        self.commit('additional registry')
        self.assertEqual([],check(self.root,self.base))
        baseline=self.git('rev-parse','HEAD').strip()
        registry.write_text(json.dumps({'claims':[dict(self.claim,record='docs/factory/old.md',source_sha256='0'*64)]}))
        self.commit('bad assertion without prose edit')
        with self.assertRaisesRegex(ValueError,'source-mismatch'):check(self.root,baseline)

    def test_later_correction_uses_filename_date_and_later_registry(self):
        from tools.check_record_commit_claims import current_claims
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        old=dict(self.claim,record='docs/factory/prior.md')
        registry=directory/'commit-claims-2026-11-03.json'
        registry.write_text(json.dumps({'claims':[old]}));before=registry.read_bytes()
        new={k:v for k,v in old.items() if k not in ('role','source_path','source_sha256')}
        new.update(role='publication',publication_path=old['source_path'],publication_sha256=old['source_sha256'])
        row=dict(record=old['record'],reference=old['reference'],
                 previous_claim_sha256=sha256(json.dumps(old,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                 replacement=new)
        data=dict(schema='record-commit-role-corrections/1',prepared_on='2026-11-04',corrections=[row])
        correction=directory/'commit-claim-role-corrections-2026-11-04.json'
        correction.write_text(json.dumps(data))
        self.assertEqual([new],current_claims(self.root));self.assertEqual(before,registry.read_bytes())
        self.commit('later correction and registry')
        self.assertEqual([],check(self.root,self.base))
        data['prepared_on']='2026-10-18';correction.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'correction-schema'):current_claims(self.root)
        data['prepared_on']='2026-11-04';correction.write_text(json.dumps(data))
        data['prepared_on']='2026-11-05'
        (directory/'commit-claim-role-corrections-2026-11-05.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'correction-duplicate'):current_claims(self.root)

    def test_malformed_registry_and_correction_metadata_fail_closed(self):
        from tools.check_record_commit_claims import current_claims
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        registry=directory/'commit-claims-future.json'
        for data in ([],{}, {'claims':{}}, {'claims':[1]}):
            with self.subTest(registry=data):
                registry.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'claims-schema'):current_claims(self.root)
        registry.write_text(json.dumps({'claims':[]}))
        for filename,prepared in (('bad','2026-11-04'),('2026-02-30','2026-02-30')):
            correction=directory/('commit-claim-role-corrections-'+filename+'.json')
            correction.write_text(json.dumps(dict(schema='record-commit-role-corrections/1',prepared_on=prepared,corrections=[])))
            with self.assertRaisesRegex(ValueError,'correction-date'):current_claims(self.root)
            correction.unlink()
        correction=directory/'commit-claim-role-corrections-2026-11-04.json'
        for data in ([],{},dict(schema='record-commit-role-corrections/1',prepared_on='2026-11-04',corrections={}),
                     dict(schema='record-commit-role-corrections/1',prepared_on='2026-11-04',corrections=[1])):
            with self.subTest(correction=data):
                correction.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'correction-schema'):current_claims(self.root)

    def test_named_dated_manifest_preserves_both_existing_dated_files(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        name='docs/factory/retention-summary-2026-10-19.md'
        (self.root/name).write_text('Source revision `'+self.base+'`.\n')
        frozen={self.root/CLAIMS:b'{"claims": []}\n',
                directory/'commit-claims-2026-10-19.json':b'{"claims":[]}\n'}
        for path,raw in frozen.items():path.write_bytes(raw)
        newer=directory/'commit-claims-intcalc-retention-2026-10-19.json'
        newer.write_text(json.dumps({'claims':[dict(self.claim,record=name)]}))
        self.commit('named dated claims')
        self.assertEqual(1,len(check(self.root,self.base)))
        for path,raw in frozen.items():self.assertEqual(raw,path.read_bytes())
        newer.write_text(json.dumps({'claims':[dict(self.claim,record=name,source_sha256='0'*64)]}))
        self.commit('invalid named claim')
        with self.assertRaisesRegex(ValueError,'source-mismatch'):check(self.root,self.base)
        for path,raw in frozen.items():self.assertEqual(raw,path.read_bytes())

    def test_named_and_bare_dated_duplicate_claims_remain_ambiguous(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        name='docs/factory/current-status.json'
        (self.root/name).write_text(json.dumps({'source':self.base}))
        content=json.dumps({'claims':[dict(self.claim,record=name)]})
        for filename in ('commit-claims-2026-10-19.json','commit-claims-intcalc-retention-2026-10-19.json'):
            (directory/filename).write_text(content)
        self.commit('duplicate across named and bare dated manifests')
        with self.assertRaisesRegex(ValueError,'claim-required'):check(self.root,self.base)
