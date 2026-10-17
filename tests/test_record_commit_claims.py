from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from tools.check_record_commit_claims import check,validate_claim,CLAIMS,resolve


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
        name='docs/factory/receipt-2026-10-17.md'
        (self.root/name).write_text('Source revision `'+self.base+'`.\n')
        (directory/'preserved-2026-10-16.md').write_text('Historical unresolved `ffffffff`.\n')
        self.commit('new records')
        with self.assertRaisesRegex(ValueError,'claim-required'):check(self.root,self.base)
        (self.root/CLAIMS).write_text(json.dumps(dict(claims=[dict(self.claim,record=name)])))
        self.commit('bound source claim')
        self.assertEqual(1,len(check(self.root,self.base)))

    def test_resolving_wrong_commit_does_not_validate_claim(self):
        (self.root/'source.txt').write_bytes(b'different\n');self.commit('changed source')
        head=self.git('rev-parse','HEAD').strip()
        with self.assertRaisesRegex(ValueError,'source-mismatch'):
            validate_claim(self.root,dict(self.claim,reference=head,commit=head))
