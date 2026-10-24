"""Public index fixtures: synthetic run surfaces and mocked metadata only."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import copau_public_corpus_index as collector
from tools import copau_private_prerequisites as custody


class PublicCorpusIndexTests(unittest.TestCase):
    def test_producer_disabled_graph_inventory_uses_index_byte_contract(self):
        from tools.ci import copau_run_boundary as producer
        from lightyear_factory.copau_boundary import DISABLED_GRAPH
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve(); roots = {}
            for name in ('worker', 'graph', 'prompts', 'contexts'):
                root = base/name; root.mkdir(); roots[name] = root
                if name != 'graph':
                    for i in range(403 if name == 'worker' else 1):
                        (root/(str(i)+'.txt')).write_bytes(('synthetic '+str(i)).encode())
            (roots['graph']/'disabled.json').write_bytes(producer.encoded(DISABLED_GRAPH))
            rows = {n:collector.file_rows(root) for n,root in roots.items()}
            surfaces = {n:dict(records=1, inventory_sha256=producer.inventory_digest(rows[n]))
                        for n in ('graph','prompts','contexts')}
            surfaces['graph'].update(status='disabled', records=0,
                exception='copau-empty-graph-2026-10-24',
                declaration_sha256=producer.digest(producer.encoded(DISABLED_GRAPH)))
            self.assertIs(producer.inventory_digest, collector.inventory_digest)
            manifest = base/'manifest.json'
            manifest.write_bytes(collector.encoded({r['path']:r['sha256'] for r in rows['worker']}))
            boundary = base/'boundary.json'
            value = dict(schema='copau-run-visible-boundary/1', main_commit='a'*40, surfaces=surfaces)
            boundary.write_bytes(producer.encoded(value))
            with patch.object(collector,'WORKER_SHA',collector.sha(manifest.read_bytes())), \
                    patch.object(collector,'github',return_value={'object':{'sha':'a'*40}}), \
                    patch.object(collector,'git_bytes',return_value=b'synthetic-tree'), \
                    patch.object(collector,'historical_metadata',return_value={}):
                args = (roots['worker'],manifest,base,roots['graph'],roots['prompts'],roots['contexts'],boundary)
                index = collector.build_index(*args)
                self.assertEqual(index['closure_review']['status'],'unreviewed')
                self.assertEqual(index['corpora']['graph']['records'],0)
                self.assertEqual(index['corpora']['graph']['status'],'disabled')
                # The old no-newline inventory digest must still be refused.
                surfaces['graph']['inventory_sha256'] = producer.digest(producer.encoded(rows['graph']))
                self.assertNotEqual(surfaces['graph']['inventory_sha256'],producer.inventory_digest(rows['graph']))
                boundary.write_bytes(producer.encoded(value))
                with self.assertRaises(custody.Refused):collector.build_index(*args)

    def test_repository_endpoint_has_no_empty_path_separator(self):
        from subprocess import CompletedProcess
        with patch.object(collector.subprocess, 'run', return_value=CompletedProcess([], 0, b'{"private":false}')) as run:
            self.assertEqual(collector.github(''), {'private': False})
            self.assertEqual(run.call_args.args[0], ['gh', 'api', 'repos/'+collector.REPO])
            collector.github('git/ref/heads/main')
            self.assertEqual(run.call_args.args[0], ['gh', 'api', 'repos/'+collector.REPO+'/git/ref/heads/main'])
        with patch.object(collector.subprocess, 'run', return_value=CompletedProcess([], 1, b'{}')):
            with self.assertRaises(custody.Refused):collector.github('')

    def test_pagination_complete_and_changed_total_refused(self):
        first = dict(total_count=101, artifacts=[dict(id=i) for i in range(100)])
        second = dict(total_count=101, artifacts=[dict(id=100)])
        with patch.object(collector, 'github', side_effect=[first, second]) as api:
            self.assertEqual(len(collector.pages('actions/artifacts', 'artifacts')), 101)
            self.assertEqual(api.call_count, 2)
        with patch.object(collector, 'github', side_effect=[first, dict(second, total_count=102)]):
            with self.assertRaises(custody.Refused):collector.pages('actions/artifacts', 'artifacts')

    def test_historical_metadata_never_downloads_bytes(self):
        with patch.object(collector, 'pages', side_effect=[
                [dict(id=1, expired=False), dict(id=2, expired=True)],
                [dict(id=9, draft=True), dict(id=10, draft=False)], [dict(id=11)]]), \
                patch.object(collector, 'github') as download:
            report = collector.historical_metadata()
        download.assert_not_called()
        self.assertEqual(report['status'], collector.HISTORICAL)
        self.assertEqual(report['observed_count'], 3)
        self.assertIn(dict(kind='artifact', id=2), report['missing'])
        self.assertEqual(report['metadata_error_count'], 0)
        self.assertEqual(set(report), {'status', 'observed_count', 'catalog_sha256', 'catalog', 'missing', 'metadata_error_count'})
        self.assertEqual(report['catalog'], [dict(kind='artifact', id=1), dict(kind='artifact', id=2), dict(kind='release-asset', id=11)])
        self.assertEqual(report['catalog_sha256'], collector.sha(collector.encoded(report['catalog'])))

    def test_missing_historical_catalog_is_disclosure_only(self):
        with patch.object(collector, 'pages', side_effect=OSError('synthetic public failure')):
            report = collector.historical_metadata()
        self.assertEqual(report['metadata_error_count'], 2)
        self.assertEqual(len(report['missing']), 3)
        self.assertEqual(report['status'], collector.HISTORICAL)

    def test_run_index_requires_all_bound_surfaces_and_remains_unreviewed(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve(); roots = {}
            for name in ('worker', 'graph', 'prompts', 'contexts'):
                root = base / name; root.mkdir(); roots[name] = root
                for i in range(403 if name == 'worker' else 1):
                    (root / (str(i)+'.txt')).write_bytes(('synthetic '+str(i)).encode())
            bindings = {r['path']:r['sha256'] for r in collector.file_rows(roots['worker'])}
            manifest = base / 'manifest.json'; manifest.write_bytes(collector.encoded(bindings))
            boundary = base / 'boundary.json'
            boundary.write_bytes(collector.encoded(dict(schema='copau-run-visible-boundary/1', main_commit='a'*40, surfaces={
                n:dict(inventory_sha256=collector.sha(collector.encoded(collector.file_rows(roots[n]))), records=1)
                for n in ('graph', 'prompts', 'contexts')})))
            history = dict(status=collector.HISTORICAL, catalog_sha256='0'*64, observed_count=0,
                           missing=[], metadata_error_count=0)
            with patch.object(collector, 'WORKER_SHA', collector.sha(manifest.read_bytes())), \
                    patch.object(collector, 'github', return_value={'object':{'sha':'a'*40}}), \
                    patch.object(collector, 'git_bytes', return_value=b'synthetic-tree'), \
                    patch.object(collector, 'historical_metadata', return_value=history):
                index = collector.build_index(roots['worker'], manifest, base, roots['graph'],
                                              roots['prompts'], roots['contexts'], boundary)
                self.assertEqual(set(index['corpora']), {'worker','main','graph','prompts','contexts'})
                self.assertEqual(index['closure_review']['status'], 'unreviewed')
                self.assertEqual(index['corpora']['main']['commit'], 'a'*40)
                self.assertFalse(index['corpora']['prompts']['all_run_visible_content_included'])
                # The bound-main requirement must refuse stale surface inventories.
                with patch.object(collector, 'github', return_value={'object':{'sha':'b'*40}}):
                    with self.assertRaises(custody.Refused):
                        collector.build_index(roots['worker'], manifest, base, roots['graph'],
                                              roots['prompts'], roots['contexts'], boundary)
                (roots['contexts'] / 'extra.txt').write_bytes(b'new unbound template')
                with self.assertRaises(custody.Refused):
                    collector.build_index(roots['worker'], manifest, base, roots['graph'],
                                          roots['prompts'], roots['contexts'], boundary)


if __name__ == '__main__':
    unittest.main()
