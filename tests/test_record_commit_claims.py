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
