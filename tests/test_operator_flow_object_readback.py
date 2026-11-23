"""Untrusted REST-shaped data, real Git object bytes; no API or authority."""
import copy,os,unittest
from base64 import b64encode
from datetime import datetime,timezone
import test_operator_flow_publication_objects as fixtures
from tools.ci.operator_flow_publication_objects import (verify_object_readback,verify_ref_readback,MODES,tree_entries)

class ObjectReadback(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.fixture=fixtures.PublicationObjects();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.candidate=self.fixture.candidate
    def response(self,oid):
        kind,raw=self.candidate['objects'][oid];out={'sha':oid}
        if kind=='blob':out.update(encoding='base64',size=len(raw),content=b64encode(raw).decode()+'\n')
        elif kind=='tree':
            out.update(truncated=False,tree=[dict(path=n.decode(),mode='040000' if m=='40000' else m,type=MODES[m],sha=s) for n,m,s in tree_entries(raw)])
        else:
            person=dict(name='Codex',email='codex@openai.com',date=datetime.fromtimestamp(self.candidate['commit_epoch'],timezone.utc).isoformat().replace('+00:00','Z'))
            from tools.ci.operator_flow_metadata import MESSAGE
            out.update(tree={'sha':self.candidate['tree']},parents=[{'sha':self.candidate['parent']}],author=dict(person),committer=dict(person),message=MESSAGE)
        return out
    def oid(self,kind):return next(k for k,v in self.candidate['objects'].items() if v[0]==kind)
    def test_every_original_git_object_roundtrips_without_authority(self):
        before=copy.deepcopy(self.candidate)
        for oid in self.candidate['objects']:
            self.assertEqual(verify_object_readback(self.candidate,oid,self.response(oid)),oid)
        self.assertEqual(self.candidate,before);self.assertFalse(self.candidate['publication_authorized'])
    def test_returned_id_substitution_refuses_even_correct_body(self):
        for oid in self.candidate['objects']:
            row=self.response(oid);row['sha']='0'*40
            with self.assertRaisesRegex(ValueError,'returned-id'):verify_object_readback(self.candidate,oid,row)
    def test_blob_body_encoding_and_boolean_size_refuse(self):
        oid=self.oid('blob');row=self.response(oid)
        for changes in ({'content':b64encode(b'changed').decode()},{'content':'!!!'},{'size':True},{'encoding':'utf-8'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):verify_object_readback(self.candidate,oid,dict(row,**changes))
    def test_incomplete_reordered_duplicate_and_changed_tree_refuse(self):
        oid=self.candidate['tree'];row=self.response(oid)
        changed=copy.deepcopy(row);changed['tree'][0]['mode']='100755'
        duplicate=copy.deepcopy(row);duplicate['tree'].append(duplicate['tree'][0])
        for value in (dict(row,truncated=True),dict(row,tree=[]),dict(row,tree=list(reversed(row['tree']))),changed,duplicate):
            with self.assertRaises(ValueError):verify_object_readback(self.candidate,oid,value)
    def test_commit_parent_tree_message_and_extra_parent_refuse(self):
        oid=self.candidate['commit'];row=self.response(oid)
        for changes in ({'tree':{'sha':'0'*40}},{'parents':[{'sha':'0'*40}]},{'parents':row['parents']*2},{'message':row['message']+' '}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):verify_object_readback(self.candidate,oid,dict(row,**changes))
    def test_commit_identity_timezone_and_epoch_substitutions_refuse(self):
        oid=self.candidate['commit'];row=self.response(oid)
        for changes in ({'name':'Other'},{'email':'other@example.invalid'},{'date':'2026-01-01T00:00:00'},{'date':'2026-01-01T00:00:00+01:00'},{'date':'invalid'}):
            value=copy.deepcopy(row);value['author'].update(changes)
            with self.assertRaises(ValueError):verify_object_readback(self.candidate,oid,value)
    def test_supplied_candidate_cannot_change_bytes_under_expected_id(self):
        oid=self.oid('blob');row=self.response(oid);kind,raw=self.candidate['objects'][oid]
        self.candidate['objects'][oid]=(kind,raw+b' ')
        with self.assertRaisesRegex(ValueError,'original-object'):verify_object_readback(self.candidate,oid,row)
    def test_ref_wrong_name_type_or_head_refuses(self):
        ref='refs/heads/codex/disposable-test';head=self.candidate['commit']
        row=dict(ref=ref,object=dict(type='commit',sha=head))
        self.assertEqual(verify_ref_readback(row,branch_ref=ref,metadata_head=head),head)
        for value in (dict(row,ref='refs/heads/main'),dict(row,object=dict(type='tag',sha=head)),dict(row,object=dict(type='commit',sha='0'*40))):
            with self.assertRaises(ValueError):verify_ref_readback(value,branch_ref=ref,metadata_head=head)
        with self.assertRaises(ValueError):verify_ref_readback(row,branch_ref='refs/tags/nonce',metadata_head=head)
