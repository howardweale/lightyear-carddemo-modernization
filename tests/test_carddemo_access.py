import os
import unittest
import uuid
from lightyear_data.carddemo.access import VsamRepository,DliRepository
from lightyear_data.carddemo.volume import load_index


@unittest.skipUnless(os.environ.get('CARDDEMO_DATA_TEST_DSN'),'PostgreSQL CI only')
class AccessTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.c=psycopg.connect(os.environ['CARDDEMO_DATA_TEST_DSN'])
        schema='access_'+uuid.uuid4().hex
        self.c.execute('CREATE SCHEMA '+schema);self.c.execute('SET LOCAL search_path TO '+schema)
        self.addCleanup(self.c.close);self.addCleanup(self.c.rollback)

    def test_vsam_key_order_mutation_and_statuses(self):
        mapping=dict(table='vsam',record_length=4,keys=[dict(column='ebcdic_key',name='K',key_offset=0,key_length=2)])
        load_index(self.c,mapping,[b'02bb',b'01aa'])
        repo=VsamRepository(self.c,mapping)
        self.assertEqual(('46',None),repo.next())
        repo.start(key=b'01');self.assertEqual(('00',b'01aa'),repo.next());self.assertEqual(('00',b'02bb'),repo.next());self.assertEqual(('10',None),repo.next())
        self.assertEqual('22',repo.write(b'01zz',3));self.assertEqual('00',repo.write(b'03cc',3))
        self.assertEqual('21',repo.rewrite(b'03',b'04dd'));self.assertEqual('00',repo.rewrite(b'03',b'03dd'))
        self.assertEqual(('00',b'03dd'),repo.read(b'03'));self.assertEqual('00',repo.delete(b'03'));self.assertEqual(('23',None),repo.read(b'03'))
        repo.end();self.assertEqual(('46',None),repo.next())

    def test_dli_hierarchy_hold_and_failed_get_clear_position(self):
        DliRepository.create(self.c);repo=DliRepository(self.c,'AP')
        self.assertEqual('DJ',repo.mutate(b'bad'))
        self.assertEqual('  ',repo.insert(b'R1',b'root'))
        self.assertEqual('II',repo.insert(b'R1',b'duplicate'))
        self.assertEqual('GE',repo.insert(b'C1',b'orphan',b'R0'))
        self.assertEqual('  ',repo.insert(b'C1',b'child',b'R1'))
        self.assertEqual(('DJ',None),repo.gnp(b'C1'))
        self.assertEqual(('  ',b'root'),repo.gu(b'R1'))
        self.assertEqual(('  ',b'child'),repo.gnp(b'C1',hold=True))
        self.assertEqual('  ',repo.mutate(b'updated'));self.assertEqual('DJ',repo.mutate(b'again'))
        repo.gu(b'R1',hold=True);repo.gu(b'missing');self.assertEqual('DJ',repo.mutate(delete=True))
        repo.gu(b'R1',hold=True);self.assertEqual('  ',repo.mutate(delete=True))
        self.assertEqual(0,self.c.execute('SELECT count(*) FROM dli_child').fetchone()[0])
        self.assertEqual('DJ',DliRepository(self.c,'G').insert(b'R2',b'data'))
