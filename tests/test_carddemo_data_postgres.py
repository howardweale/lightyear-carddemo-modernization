"""Real PostgreSQL adversarial checks. Run only in the dedicated Linux CI job."""
import os
from pathlib import Path
import unittest
import uuid

from lightyear_data.carddemo.codec import project
from lightyear_data.carddemo.plan import build
from lightyear_data.carddemo.proof import reconcile, browse_gate, run
from lightyear_data.carddemo.schema import ddl,quote
from lightyear_data.carddemo.store import Store
from test_carddemo_data_schema import fixture

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('CARDDEMO_DATA_TEST_DSN'),'dedicated PostgreSQL CI only')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.connection=psycopg.connect(os.environ['CARDDEMO_DATA_TEST_DSN'])
        self.schema='proof_'+uuid.uuid4().hex
        self.connection.execute('CREATE SCHEMA '+quote(self.schema))
        self.connection.execute('SET LOCAL search_path TO '+quote(self.schema))

    def tearDown(self):
        # Tests own a transaction-scoped schema; rollback removes it without DROP.
        self.connection.rollback();self.connection.close()

    def make(self,body,kind='KSDS',key=(1,0)):
        layout,m=fixture(body,kind,key);self.connection.execute(ddl(m))
        return Store(self.connection,m,layout)

    def test_actual_database_roundtrip_tamper_and_control_totals(self):
        store=self.make(['05 K PIC X.','05 AMOUNT PIC S9(3)V99 COMP-3.','05 FILLER PIC X(2).'])
        records=[bytes.fromhex('c101234c00ff'),bytes.fromhex('f101234f4040'),bytes.fromhex('c200000d40ff')]
        for i,r in enumerate(records,1):self.assertEqual('loaded',store.load_one(r,i)['status'])
        result=reconcile(store,records)
        self.assertEqual('equivalent',result['round_trip']['verdict'])
        self.assertEqual('equivalent',result['reconciliation']['verdict'])
        self.assertEqual('equivalent',result['browse_order']['verdict'])
        self.connection.execute('UPDATE sample SET r_amount=99.99 WHERE source_ordinal=1')
        changed=reconcile(store,records)
        self.assertEqual('divergent',changed['round_trip']['verdict'])
        self.assertEqual('divergent',changed['reconciliation']['verdict'])

    def test_duplicate_invalid_and_truncated_records_quarantine_atomically(self):
        store=self.make(['05 K PIC X.','05 AMOUNT PIC S9(3) COMP-3.'])
        records=[bytes.fromhex(v) for v in ('c1123c','c1123d','c212ac','c31230','c4','00123c','ff123c')]
        statuses=[store.load_one(r,i)['status'] for i,r in enumerate(records,1)]
        self.assertEqual(['loaded']+['quarantined']*4+['loaded']*2,statuses)
        result=reconcile(store,records)
        self.assertEqual(4,result['quarantined'])
        self.assertEqual('equivalent',result['reconciliation']['verdict'])

    def test_empty_input_never_claims_equivalence(self):
        store=self.make(['05 K PIC X.'])
        self.assertEqual('indeterminate',reconcile(store,[])['round_trip']['verdict'])

    def test_saved_metadata_cannot_replace_typed_business_fields(self):
        store=self.make(['05 K PIC X.','05 VALUE-FIELD PIC X(2).'])
        original='ABC'.encode('cp037');store.load_one(original,1)
        from psycopg.types.json import Jsonb
        metadata=store.rows()[0]['encoding_meta']
        metadata['active']=[];metadata['filler']=[{'offset':0,'hex':original.hex()}]
        self.connection.execute('UPDATE sample SET encoding_meta=%s, r_value_field=%s',(Jsonb(metadata),'ZZ'.encode('cp037')))
        self.assertEqual('divergent',reconcile(store,[original])['round_trip']['verdict'])

    def test_nonunique_alternate_browse_uses_primary_tie_breaker(self):
        from lightyear_data.carddemo.schema import mapping
        layout,m=fixture(['05 K PIC X.','05 GROUP-ID PIC X.'])
        alternate={**m['definition'],'name':'ALT','kind':'AIX','key_offset':1,'unique':False,'relate':'R'}
        m=mapping('sample',layout,'fixture.cpy',[m['definition'],alternate])
        self.connection.execute(ddl(m));store=Store(self.connection,m,layout)
        records=[s.encode('cp037') for s in ('1A','BA','AA','Z0')]
        for i,r in enumerate(records,1):store.load_one(r,i)
        self.assertEqual([3,2,1,4],store.browse('ebcdic_key_aix_1',prefix='A'.encode('cp037')))
        self.assertEqual([1,2,3],store.browse('ebcdic_key_aix_1',prefix='A'.encode('cp037'),reverse=True))
        self.assertEqual('equivalent',reconcile(store,records)['browse_order']['verdict'])

    def test_date_raw_text_and_invalid_date_quarantine(self):
        store=self.make(['05 K PIC X.','05 OPEN-DATE PIC X(10).'])
        records=[s.encode('cp037') for s in ('A2026-10-15','B2026-02-30')]
        self.assertEqual('loaded',store.load_one(records[0],1)['status'])
        self.assertEqual('quarantined',store.load_one(records[1],2)['status'])
        self.assertEqual(records[0],store.bytes(store.rows()[0]))
        self.connection.execute("UPDATE sample SET r_open_date='2026-10-16'")
        self.assertEqual('divergent',reconcile(store,records)['round_trip']['verdict'])

    def test_odo_child_rows_preserve_count_order_and_sliding_tail(self):
        store=self.make(['05 K PIC X.','05 N PIC 9.','05 ITEM OCCURS 0 TO 3 DEPENDING ON N.','10 V PIC 9(2).','05 TAIL PIC X.'])
        records=[s.encode('cp037') for s in ('A21234Z','B0Y')]
        for i,r in enumerate(records,1):self.assertEqual('loaded',store.load_one(r,i)['status'])
        self.assertEqual('equivalent',reconcile(store,records)['round_trip']['verdict'])
        child=next(iter(store.mapping['children']))
        self.connection.execute('DELETE FROM '+quote(child)+' WHERE ordinal=2')
        self.assertEqual('divergent',reconcile(store,records)['round_trip']['verdict'])

    def test_esds_positions_are_explicit_and_duplicates_quarantined(self):
        store=self.make(['05 V PIC X(2).'],'ESDS',None)
        self.assertEqual('quarantined',store.load_one(b'\xc1\xc2',1)['status'])
        self.assertEqual('loaded',store.load_one(b'\xc1\xc2',2,position=128)['status'])
        self.assertEqual('quarantined',store.load_one(b'\xc1\xc3',3,position=128)['status'])

    def test_public_pipeline_and_generated_ims_remain_honestly_scoped(self):
        root=ROOT/'spec/modernization/carddemo-data';plan,entries=build(root)
        receipt=run(self.connection,root,plan,entries)
        self.assertEqual([],receipt['failures'])
        self.assertEqual(5,len(receipt['vsam']))
        self.assertEqual('equivalent',receipt['ims']['traversal']['verdict'])
        self.assertEqual('indeterminate',receipt['ims']['public_unload']['verdict'])
        self.assertFalse(receipt['signed'])
        # Parent foreign keys must reject an orphan without losing the raw segment.
        _,layout,m=next(e for e in entries if e[2]['table']=='pautdtl1')
        store=Store(self.connection,m,layout)
        raw=store.bytes(store.rows()[0])
        self.assertEqual('quarantined',store.load_one(raw,99,parent_path=b'absent',twin_seq=99)['status'])


if __name__=='__main__':unittest.main()
