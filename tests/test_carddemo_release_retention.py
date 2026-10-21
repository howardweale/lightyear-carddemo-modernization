"""Offline CI fixtures: no GitHub network, provider, signing or activation."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import zipfile
from tools.carddemo_release_retention import (ARCHIVES,JOBS,REPO,Github,digest,inspect_archive,
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
        return copy.deepcopy(self.release_row)
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
        c=FakeGithub();c.release_row=dict(id=42,tag_name='evidence-2026-10-19-carddemo-run123',draft=True);c.assets['carddemo-proof-api.zip']=b'changed'
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):retain(c,123,Path(td))
        self.assertNotIn('carddemo-proof-api.zip',c.uploads)

    def test_xml_entity_and_unknown_status_refused(self):
        for raw in [b'<!DOCTYPE x><mutations/>',b'<mutations><mutation status="UNKNOWN"/></mutations>',b'<mutations/>']:
            with self.assertRaises(ValueError):mutation_counts(raw)


class GithubDownloadTests(unittest.TestCase):
    def test_endpoint_media_types_and_original_binary_bytes(self):
        archive=b'PK\x03\x04\x00\xfforiginal ZIP bytes'
        metadata_bytes=b'{"public":"retained"}\n'
        def transport(command):
            route=command[2]
            if route.endswith('actions/artifacts/123/zip'):
                if command[-2:]!=['-H','Accept: application/json']:
                    raise subprocess.CalledProcessError(1,command,stderr=b'HTTP 415')
                return archive
            if route.endswith('releases/assets/456'):
                if command[-2:]!=['-H','Accept: application/octet-stream']:
                    raise subprocess.CalledProcessError(1,command,stderr=b'binary media type required')
                return metadata_bytes
            raise AssertionError(command)
        with patch('tools.carddemo_release_retention.subprocess.check_output',side_effect=transport) as call:
            client=Github()
            self.assertEqual(archive,client.download('actions/artifacts/123/zip'))
            self.assertEqual(metadata_bytes,client.download('releases/assets/456'))
            self.assertEqual(2,call.call_count)

    def test_unsupported_routes_refused_before_network(self):
        with patch('tools.carddemo_release_retention.subprocess.check_output') as call:
            for route in ('actions/artifacts/123','actions/artifacts/0/zip',
                          'actions/artifacts/123/zip?redirect=other','releases/assets/../123',
                          'releases/assets/123/extra','https://example.invalid/archive'):
                with self.subTest(route=route),self.assertRaises(ValueError):
                    Github().download(route)
            call.assert_not_called()

    def test_failed_download_propagates_without_retry_or_fallback(self):
        failure=subprocess.CalledProcessError(1,['gh','api'],stderr=b'HTTP 403')
        with patch('tools.carddemo_release_retention.subprocess.check_output',side_effect=failure) as call:
            with self.assertRaises(subprocess.CalledProcessError):
                Github().download('actions/artifacts/123/zip')
            self.assertEqual(1,call.call_count)


class ReleaseIdentityTests(unittest.TestCase):
    TAG='evidence-2026-10-19-carddemo-run123'

    def test_new_draft_not_visible_in_list_still_retained_once_by_create_identity(self):
        client=FakeGithub()
        # Reproduce the failed boundary: a list cannot see the new draft.
        with tempfile.TemporaryDirectory() as td, patch.object(client,'release',return_value=None) as lookup, \
                patch.object(client,'create',wraps=client.create) as create:
            retain(client,123,Path(td))
            self.assertEqual(1,lookup.call_count)
            self.assertEqual(1,create.call_count)
            self.assertEqual(7,client.zip_reads)
            self.assertEqual(10,len(client.uploads))
            self.assertFalse(client.release_row['draft'])

    def test_adapter_returns_verified_id_without_list_or_second_create(self):
        row=dict(id=42,tag_name=self.TAG,draft=True)
        for existing_tag in (False,True):
            with self.subTest(existing_tag=existing_tag), \
                    patch('tools.carddemo_release_retention.subprocess.run') as git_run, \
                    patch('tools.carddemo_release_retention.subprocess.check_output',return_value=('a'*40+' refs/tags/'+self.TAG+'\n') if existing_tag else ''):
                client=Github()
                with patch.object(client,'api',side_effect=[row,dict(row)]) as api, patch.object(client,'pages') as pages:
                    self.assertEqual(row,client.create(self.TAG,'a'*40))
                    self.assertEqual(2,api.call_count)
                    self.assertEqual(('releases',),api.call_args_list[0].args)
                    self.assertEqual('POST',api.call_args_list[0].kwargs['method'])
                    self.assertEqual(self.TAG,api.call_args_list[0].kwargs['tag_name'])
                    self.assertTrue(api.call_args_list[0].kwargs['draft'])
                    self.assertEqual(('releases/42',),api.call_args_list[1].args)
                    pages.assert_not_called()
                    commands=[c.args[0] for c in git_run.call_args_list]
                    self.assertTrue(all(c[0]=='git' for c in commands))
                    self.assertEqual(0 if existing_tag else 1,sum('push' in c for c in commands))

    def test_bad_creation_or_id_read_refused_without_fallback(self):
        good=dict(id=42,tag_name=self.TAG,draft=True)
        bad_rows=[None,{},dict(good,id=True),dict(good,id=0),dict(good,id='42'),
                  dict(good,tag_name='other'),dict(good,draft=False),dict(good,draft='true')]
        for bad in bad_rows:
            with self.subTest(bad=bad), patch('tools.carddemo_release_retention.subprocess.run'), \
                    patch('tools.carddemo_release_retention.subprocess.check_output',return_value=''):
                client=Github()
                with patch.object(client,'api',return_value=bad) as api:
                    with self.assertRaises(ValueError):client.create(self.TAG,'a'*40)
                    self.assertEqual(1,api.call_count)
        for fresh in [dict(good,id=43),dict(good,tag_name='other'),dict(good,draft=False)]:
            with self.subTest(fresh=fresh), patch('tools.carddemo_release_retention.subprocess.run'), \
                    patch('tools.carddemo_release_retention.subprocess.check_output',return_value=''):
                client=Github()
                with patch.object(client,'api',side_effect=[good,fresh]) as api:
                    with self.assertRaises(ValueError):client.create(self.TAG,'a'*40)
                    self.assertEqual(2,api.call_count)

    def test_create_or_read_transport_failure_never_recreates(self):
        good=dict(id=42,tag_name=self.TAG,draft=True)
        error=subprocess.CalledProcessError(1,['gh','api'],stderr=b'ambiguous response')
        for responses in ([error],[good,error]):
            with self.subTest(calls=len(responses)), patch('tools.carddemo_release_retention.subprocess.run'), \
                    patch('tools.carddemo_release_retention.subprocess.check_output',return_value=''):
                client=Github()
                with patch.object(client,'api',side_effect=responses) as api, patch.object(client,'release') as lookup:
                    with self.assertRaises(subprocess.CalledProcessError):client.create(self.TAG,'a'*40)
                    self.assertEqual(len(responses),api.call_count)
                    self.assertEqual(1,sum(c.kwargs.get('method')=='POST' for c in api.call_args_list))
                    lookup.assert_not_called()

    def test_changed_created_tag_refused_before_any_upload(self):
        client=FakeGithub();original=client.api
        def api(path,method='GET',**fields):
            if path.startswith('git/ref/tags/'):
                return dict(object=dict(sha='b'*40,type='commit'))
            return original(path,method,**fields)
        with tempfile.TemporaryDirectory() as td, patch.object(client,'api',side_effect=api):
            with self.assertRaisesRegex(ValueError,'tag identity changed'):retain(client,123,Path(td))
        self.assertEqual([],client.uploads)
        self.assertTrue(client.release_row['draft'])
