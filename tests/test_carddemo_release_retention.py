"""Offline CI fixtures: no GitHub network, provider, signing or activation."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from tools.carddemo_release_retention import (ARCHIVES,JOBS,REPO,digest,inspect_archive,
    metadata,mutation_counts,retain,validate_run)

XML=b'<mutations><mutation status="KILLED"/><mutation status="TIMED_OUT"/></mutations>'


def zipped(name='proof.txt',raw=b'public fixture'):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:z.writestr(name,raw)
    return out.getvalue()


class FakeGithub:
    def __init__(self):
        self.run=dict(id=123,conclusion='success',status='completed',event='pull_request',
                      path='.github/workflows/carddemo-web.yml',repository=dict(full_name=REPO,private=False),
                      head_repository=dict(full_name=REPO),head_sha='a'*40,run_attempt=1,
                      run_started_at='2026-10-19T12:00:00Z',html_url='https://github.com/'+REPO+'/actions/runs/123')
        self.jobs=[dict(name=n,status='completed',conclusion='success') for n in sorted(JOBS)]
        self.originals={};self.artifacts=[];self.assets={};self.release_row=None;self.uploads=[];self.zip_reads=0
        for i,name in enumerate(sorted(ARCHIVES),1):
            raw=zipped('pit-reports/mutations.xml',XML) if name=='carddemo-proof-mutation' else zipped()
            self.originals[i]=raw
            self.artifacts.append(dict(id=i,name=name,size_in_bytes=len(raw),digest='sha256:'+digest(raw),expired=False,workflow_run=dict(id=123)))

    def api(self,path,method='GET',**fields):
        if path=='actions/runs/123':return copy.deepcopy(self.run)
        if path.startswith('git/ref/tags/'):return dict(object=dict(sha=self.run['head_sha'],type='commit',url='fixture'))
        if path=='releases/42' and method=='PATCH':
            self.release_row.update(fields);return dict(self.release_row)
        raise AssertionError(path)

    def pages(self,path,key=None):
        if '/jobs' in path:return copy.deepcopy(self.jobs)
        if path=='actions/runs/123/artifacts':return copy.deepcopy(self.artifacts)
        if path=='releases/42/assets':return [dict(id=i,name=name,size=len(raw),digest='sha256:'+digest(raw)) for i,(name,raw) in enumerate(self.assets.items(),100)]
        raise AssertionError(path)

    def download(self,path):
        if path.startswith('actions/artifacts/'):
            self.zip_reads+=1;return self.originals[int(path.split('/')[2])]
        if path.startswith('releases/assets/'):
            index=int(path.rsplit('/',1)[1])-100;return list(self.assets.values())[index]
        raise AssertionError(path)

    def release(self,tag):return copy.deepcopy(self.release_row)
    def create(self,tag,head):
        if self.release_row:raise AssertionError('duplicate creation')
        self.release_row=dict(id=42,tag_name=tag,draft=True)
    def upload(self,tag,path):
        if path.name in self.assets:raise AssertionError('overwrite')
        self.assets[path.name]=path.read_bytes();self.uploads.append(path.name)


class RetentionTests(unittest.TestCase):
    def test_originals_retained_and_only_two_small_metadata_files_published(self):
        client=FakeGithub()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);result=retain(client,123,root)
            self.assertEqual(10,len(client.assets));self.assertFalse(client.release_row['draft'])
            files=list((root/'publication').iterdir());self.assertEqual(2,len(files))
            self.assertTrue(all(p.suffix=='.json' and p.stat().st_size<50_000 for p in files))
            manifest=json.loads(next(p for p in files if p.name.startswith('evidence-retention')).read_bytes())
            self.assertEqual('public-evidence-retention/1',manifest['schema'])
            self.assertEqual(8,len(manifest['assets']));self.assertEqual('a'*40,result['source_head'])
            for a in client.artifacts:self.assertEqual(client.originals[a['id']],client.assets[a['name']+'.zip'])
            counts=json.loads(client.assets['proof-summary.json'])['mutation']
            self.assertEqual(1,counts['killed']);self.assertEqual(2,counts['total']);self.assertFalse(counts['timeout_credit'])

    def test_completed_release_reused_without_archive_redownload_or_upload(self):
        client=FakeGithub()
        with tempfile.TemporaryDirectory() as td:
            retain(client,123,Path(td)/'first');before=(client.zip_reads,list(client.uploads))
            retain(client,123,Path(td)/'second');self.assertEqual(before,(client.zip_reads,client.uploads))

    def test_wrong_run_fork_failure_and_missing_artifact_refused(self):
        for mutate in [lambda c:c.run.update(conclusion='failure'),lambda c:c.run['head_repository'].update(full_name='other/fork'),
                       lambda c:c.run['repository'].update(private=True),lambda c:c.jobs.pop(),lambda c:c.artifacts.pop()]:
            c=FakeGithub();mutate(c)
            with self.assertRaises(ValueError):validate_run(c.run,c.jobs,c.artifacts)
            self.assertFalse(c.uploads)

    def test_corrupt_archive_and_unsafe_member_refused(self):
        c=FakeGithub();a=c.artifacts[0]
        with self.assertRaises(ValueError):inspect_archive(b'changed',a)
        raw=zipped('../escape');a.update(size_in_bytes=len(raw),digest='sha256:'+digest(raw))
        with self.assertRaises(ValueError):inspect_archive(raw,a)

    def test_changed_published_metadata_or_asset_refused_without_overwrite(self):
        c=FakeGithub()
        with tempfile.TemporaryDirectory() as td:
            retain(c,123,Path(td)/'first');before=list(c.uploads)
            c.assets['carddemo-proof-api.zip']=b'changed'
            with self.assertRaises(ValueError):retain(c,123,Path(td)/'second')
            self.assertEqual(before,c.uploads)

    def test_changed_draft_asset_refused_without_overwrite(self):
        c=FakeGithub();c.release_row=dict(id=42,tag_name='fixture',draft=True);c.assets['carddemo-proof-api.zip']=b'changed'
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):retain(c,123,Path(td))
        self.assertNotIn('carddemo-proof-api.zip',c.uploads)

    def test_xml_entity_and_unknown_status_refused(self):
        for raw in [b'<!DOCTYPE x><mutations/>',b'<mutations><mutation status="UNKNOWN"/></mutations>',b'<mutations/>']:
            with self.assertRaises(ValueError):mutation_counts(raw)
