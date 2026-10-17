import os
from pathlib import Path
import unittest
import uuid
from lightyear_data.carddemo.access import VsamRepository,DliRepository
from lightyear_data.carddemo.schema import ddl
from lightyear_data.carddemo.plan import build
from lightyear_data.carddemo.proof import synthetic_segment
from lightyear_data.carddemo.store import Store
from test_carddemo_data_schema import fixture

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('CARDDEMO_DATA_TEST_DSN'),'PostgreSQL CI only')
class AccessTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.c=psycopg.connect(os.environ['CARDDEMO_DATA_TEST_DSN'])
        schema='access_'+uuid.uuid4().hex
        self.c.execute('CREATE SCHEMA '+schema);self.c.execute('SET LOCAL search_path TO '+schema)
        self.addCleanup(self.c.close);self.addCleanup(self.c.rollback)

    def test_vsam_typed_reconstruction_browse_and_mutation(self):
        layout,mapping=fixture(['05 K PIC X(2).','05 V PIC X(2).'],key=(2,0))
        self.c.execute(ddl(mapping));repo=VsamRepository(self.c,mapping,layout)
        enc=lambda s:s.encode('cp037')
        self.assertEqual(('INVREQ',None),repo.next())
        self.assertEqual('NORMAL',repo.write(enc('02bb'),1));self.assertEqual('NORMAL',repo.write(enc('01aa'),2))
        repo.start(prefix=enc('01'));self.assertEqual(('NORMAL',enc('01aa')),repo.next());self.assertEqual(('NORMAL',enc('02bb')),repo.next());self.assertEqual(('ENDFILE',None),repo.next())
        self.assertEqual('DUPREC',repo.write(enc('01zz'),3));self.assertEqual('NORMAL',repo.write(enc('03cc'),3))
        self.assertEqual('INVREQ',repo.rewrite(enc('03'),enc('04dd')));self.assertEqual('NORMAL',repo.rewrite(enc('03'),enc('03dd')))
        self.assertEqual(('NORMAL',enc('03dd')),repo.read(enc('03')))
        self.c.execute('UPDATE sample SET r_v=%s WHERE ebcdic_key=%s',(enc('ZZ'),enc('03')))
        self.assertEqual(('NORMAL',enc('03ZZ')),repo.read(enc('03')))
        self.assertEqual('NORMAL',repo.delete(enc('03')));self.assertEqual(('NOTFND',None),repo.read(enc('03')))
        self.assertEqual(0,self.c.execute('SELECT count(*) FROM quarantine_sample').fetchone()[0])
        self.assertNotIn('raw_record',[r[0] for r in self.c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='sample'")])
        repo.end();self.assertEqual(('INVREQ',None),repo.next())

    def test_real_usrsec_carddata_low_high_and_mixed_keys(self):
        root=ROOT/'spec/modernization/carddemo-data';_,entries=build(root)
        for item,layout,m in entries:
            if item['name'] not in ('usrsec','carddata'):continue
            self.c.execute(ddl(m));repo=VsamRepository(self.c,m,layout);k=m['keys'][0]
            template=(root/'upstream'/item['data']).read_bytes()[:layout.record_length]
            keys=[b'\0'*k['key_length'],b'\xff'*k['key_length'],(b'\x00\xff\xc1\xf0'*k['key_length'])[:k['key_length']]]
            originals=[]
            for i,key in enumerate(keys,1):
                raw=template[:k['key_offset']]+key+template[k['key_offset']+k['key_length']:];originals.append(raw)
                self.assertEqual('NORMAL',repo.write(raw,i));self.assertEqual(('NORMAL',raw),repo.read(key))
            repo.start();self.assertEqual([originals[i] for i in sorted(range(3),key=lambda i:keys[i])],[repo.next()[1] for _ in keys])
            self.assertEqual(0,self.c.execute('SELECT count(*) FROM quarantine_'+m['table']).fetchone()[0])

    def test_dli_migrated_hierarchy_hold_and_gn(self):
        _,entries=build(ROOT/'spec/modernization/carddemo-data')
        _,rl,rm=next(e for e in entries if e[2]['table']=='pautsum0');_,cl,cm=next(e for e in entries if e[2]['table']=='pautdtl1')
        self.c.execute(ddl(rm));self.c.execute(ddl(cm));repo=DliRepository(self.c,rm,rl,cm,cl,'AP')
        root=synthetic_segment(rl,rm,1);child=synthetic_segment(cl,cm,2)
        key=lambda raw,m:raw[m['keys'][0]['key_offset']:m['keys'][0]['key_offset']+m['keys'][0]['key_length']]
        rk=key(root,rm);ck=key(child,cm)
        self.assertEqual('DJ',repo.mutate(root));self.assertEqual('  ',repo.insert(rk,root));self.assertEqual('II',repo.insert(rk,root))
        self.assertEqual('GE',repo.insert(ck,child,b'absent'));self.assertEqual('  ',repo.insert(ck,child,rk))
        self.assertEqual(('GP',None),repo.gnp(ck));self.assertEqual(('  ',root),repo.gu(rk));self.assertEqual(('  ',child),repo.gnp(ck,hold=True))
        self.assertEqual('  ',repo.mutate(child));self.assertEqual('DJ',repo.mutate(child))
        repo.boundary();self.assertEqual(('  ',root),repo.gn());self.assertEqual(('  ',child),repo.gn());self.assertEqual(('GB',None),repo.gn())
        repo.gu(rk,hold=True);repo.gu(b'missing');self.assertEqual('DJ',repo.mutate(delete=True))
        repo.gu(rk,hold=True);self.assertEqual('  ',repo.mutate(delete=True))
        self.assertEqual(0,self.c.execute('SELECT count(*) FROM pautdtl1').fetchone()[0])
        self.assertEqual('AM',DliRepository(self.c,rm,rl,cm,cl,'G').insert(rk,root))

    def test_ims_corpus_actual_adapter(self):
        from lightyear_data.carddemo.ims_replay import replay
        result=replay(self.c,ROOT/'spec/modernization/carddemo-data',ROOT/'readiness/ims-expiry/conformance/cases.json')
        self.assertEqual(40,result['total'])
        self.assertFalse(result['unexpected_differences'])
        self.assertGreater(result['adapter_cases'],20)
        self.assertEqual(['07-gnp-without-parent','28-procopt-g-denies-update'],[r['id'] for r in result['cases'] if r.get('status_correction')])
        self.assertGreater(result['segment_comparisons'],0)
        self.assertFalse(result['release_authorized'])
