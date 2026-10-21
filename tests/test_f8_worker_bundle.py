import copy
import gzip
import io
import tarfile
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
from tools.ci.f8_worker_bundle import inspect_capsule, project, sha
from tools.ci.f8_worker_retention import validate_run, payload, retain
from tools.carddemo_release_retention import REPO

class F8WorkerBundleTests(unittest.TestCase):
    def archive(self, names):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as tar:
            for name, kind in names:
                entry = tarfile.TarInfo(name); entry.type = kind; entry.size = 1 if kind == tarfile.REGTYPE else 0
                tar.addfile(entry, io.BytesIO(b'x') if entry.size else None)
        return gzip.compress(stream.getvalue(), mtime=0)

    def test_exact_regular_hash_map_and_corruption(self):
        raw = self.archive([('m2/a.jar', tarfile.REGTYPE)])
        self.assertEqual({'m2/a.jar': sha(b'x')}, inspect_capsule(raw, {'m2/a.jar': sha(b'x')}))
        with self.assertRaisesRegex(ValueError, 'digest'): inspect_capsule(raw, {'m2/a.jar': '0' * 64})
        for entries in [[('../escape', tarfile.REGTYPE)], [('m2/link', tarfile.SYMTYPE)], [('m2/hard', tarfile.LNKTYPE)], [('m2/a', tarfile.REGTYPE)] * 2]:
            with self.assertRaisesRegex(ValueError, 'entry'): inspect_capsule(self.archive(entries), {'m2/a': sha(b'x')})

    def test_projection_is_exact_and_preserves_other_source(self):
        self.assertEqual('List trace=new ArrayList<>();', project('List<SourceEdits.Location> trace=new ArrayList<>();', 'ScreenFrame.java'))
        with self.assertRaisesRegex(ValueError, 'drift'): project('changed', 'ScreenFrame.java')
        text = 'before\n    public void load(SourceEdits x){\n        x.put();\n    }\nafter'
        self.assertEqual('before\nafter', project(text, 'AuthorizationRecords.java'))
        with self.assertRaisesRegex(ValueError, 'engine'): project('SourceEdits', 'Other.java')

    def test_retention_refuses_fork_failure_wrong_workflow_and_private_repo(self):
        good = dict(status='completed', conclusion='success', path='.github/workflows/f8-worker-bundle.yml', event='pull_request', repository=dict(full_name=REPO, private=False), head_repository=dict(full_name=REPO), head_sha='a' * 40)
        validate_run(good)
        for change in [dict(conclusion='failure'), dict(path='attacker.yml'), dict(event='workflow_dispatch'), dict(head_repository=dict(full_name='fork/repo')), dict(repository=dict(full_name=REPO, private=True))]:
            bad = copy.deepcopy(good); bad.update(change)
            with self.assertRaisesRegex(ValueError, 'untrusted'): validate_run(bad)

    def test_artifact_corruption_fails_before_parsing(self):
        with self.assertRaisesRegex(ValueError, 'artifact-digest'):
            payload(b'changed', {'size_in_bytes': 7, 'digest': 'sha256:' + '0' * 64}, {})

    def test_published_changed_asset_is_never_overwritten(self):
        run = dict(id=7, run_attempt=1, run_started_at='2026-10-20T01:00:00Z', status='completed', conclusion='success', path='.github/workflows/f8-worker-bundle.yml', event='push', repository=dict(full_name=REPO, private=False), head_repository=dict(full_name=REPO), head_sha='a' * 40)
        class Client:
            def api(self, path, **kwargs):
                if kwargs: raise AssertionError('No remote mutation permitted')
                return {'object': {'type': 'commit', 'sha': run['head_sha']}} if path.startswith('git/ref') else run
            def pages(self, path, key=None):
                if path.endswith('/jobs'): return [{'name': 'assemble-offline-worker', 'conclusion': 'success', 'status': 'completed'}]
                if path.endswith('/artifacts'): return [{'id': 9, 'name': 'f8-worker-offline-1', 'expired': False, 'size_in_bytes': 1, 'digest': 'sha256:' + sha(b'x')}]
                return [{'name': 'capsule.tar.gz', 'size': 999, 'digest': 'sha256:' + '0' * 64}]
            def release(self, tag): return {'id': 3, 'tag_name': tag, 'draft': False}
            def download(self, path): return b'x'
            def upload(self, *args): raise AssertionError('Published bytes must not be overwritten')
        with tempfile.TemporaryDirectory() as directory, patch('tools.ci.f8_worker_retention.payload', return_value={'capsule.tar.gz': b'original'}):
            with self.assertRaisesRegex(ValueError, 'immutable-release-mismatch'):
                retain(Client(), 7, Path(directory))
