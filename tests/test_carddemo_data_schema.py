"""Bounded definition and representation regressions; no database required."""
from decimal import Decimal
from pathlib import Path
import unittest

from lightyear_data.carddemo.codec import project, reconstruct
from lightyear_data.carddemo.plan import build
from lightyear_data.carddemo.schema import copybook, mapping, ddl, idcams, dbd

ROOT=Path(__file__).resolve().parents[1]


def fixture(body, kind='KSDS', key=(1,0)):
    text='       01 R.\n'+''.join('           '+line+'\n' for line in body)
    layout,_=copybook(text,'fixture.cpy')
    definition=dict(name='R',kind=kind,minimum=layout.minimum_length,maximum=layout.record_length,
        key_length=key[0] if key else None,key_offset=key[1] if key else None,unique=True,relate=None,source='fixture.jcl',line=1)
    return layout,mapping('sample',layout,'fixture.cpy',[definition])


class SchemaTests(unittest.TestCase):
    def test_public_source_pin_and_all_five_files_and_two_segments(self):
        plan,entries=build(ROOT/'spec/modernization/carddemo-data')
        self.assertEqual(7,len(entries))
        self.assertEqual(2,len(next(m for m in plan['mappings'] if m['table']=='cardxref')['keys']))
        self.assertEqual(2,len(next(m for m in plan['mappings'] if m['table']=='carddata')['keys']))
        for _,_,m in entries:
            self.assertTrue(all(f['line']>0 and f['source'] for f in m['fields']))
            self.assertIn('bytea',ddl(m))
        detail=next(m for m in plan['mappings'] if m['table']=='pautdtl1')
        self.assertIn('REFERENCES "pautsum0"(path_key)',ddl(detail))
        self.assertTrue(plan['unsupported'])

    def test_packed_c_d_f_and_negative_zero_reconstruct_from_values(self):
        layout,m=fixture(['05 K PIC X.','05 N PIC S9(3)V99 COMP-3.','05 FILLER PIC X(2).'])
        for packed in ('01234c','01234d','01234f','00000d'):
            raw=b'\xc1'+bytes.fromhex(packed)+b'\x00\xff'
            p=project(layout,m,raw)
            self.assertEqual(raw,reconstruct(m,p['values'],p['metadata']))
            p['values']['R.N']=Decimal('9.99')
            self.assertNotEqual(raw,reconstruct(m,p['values'],p['metadata']))
        self.assertNotIn('raw_hex',p['metadata'])

    def test_invalid_packed_and_date_and_unprintable_rejected(self):
        layout,m=fixture(['05 K PIC X.','05 N PIC S9(3) COMP-3.'])
        for value in ('12ac','1230'):
            with self.assertRaises(ValueError):project(layout,m,b'\xc1'+bytes.fromhex(value))
        layout,m=fixture(['05 K PIC X.','05 OPEN-DATE PIC X(10).'])
        for value in ('2026-02-30','0000-00-00'):
            with self.assertRaises(ValueError):project(layout,m,('A'+value).encode('cp037'))
        for k in (b'\x00',b'\xff'):
            with self.assertRaises(ValueError):project(layout,m,k+'2026-10-15'.encode('cp037'))

    def test_occurs_depending_on_and_sliding_tail(self):
        layout,m=fixture(['05 K PIC X.','05 N PIC 9.','05 ITEM OCCURS 0 TO 3 DEPENDING ON N.','10 V PIC 9(2).','05 TAIL PIC X.'])
        raw='A21234Z'.encode('cp037');p=project(layout,m,raw)
        self.assertEqual(raw,reconstruct(m,p['values'],p['metadata']))
        self.assertEqual(1,len(m['children']))
        self.assertIn('ordinal integer',ddl(m))

    def test_unreviewed_redefines_two_readers_refused(self):
        with self.assertRaisesRegex(ValueError,'discriminator'):
            fixture(['05 K PIC X.','05 A PIC X(2).','05 B REDEFINES A PIC 9(2).'])

    def test_esds_rrds_require_explicit_positions(self):
        for kind,col in [('ESDS','rba'),('RRDS','slot')]:
            _,m=fixture(['05 VALUE-FIELD PIC X(2).'],kind,None)
            self.assertIn('"'+col+'" bigint PRIMARY KEY',ddl(m))

    def test_definition_mismatch_and_unbound_alternate_refused(self):
        layout,m=fixture(['05 K PIC X.','05 V PIC 9.'])
        d=dict(m['definition']);d['maximum']=3
        with self.assertRaisesRegex(ValueError,'length'):mapping('x',layout,'x',[d])
        d=dict(m['definition']);d.update(kind='AIX',relate='WRONG')
        with self.assertRaisesRegex(ValueError,'another cluster'):mapping('x',layout,'x',[m['definition'],d])

    def test_numeric_overflow_and_scale_change_refused(self):
        layout,m=fixture(['05 K PIC X.','05 N PIC S9(3)V99 COMP-3.'])
        p=project(layout,m,bytes.fromhex('c101234c'))
        for value in ('1000','1.001','NaN'):
            p['values']['R.N']=Decimal(value)
            with self.assertRaises(ValueError):reconstruct(m,p['values'],p['metadata'])

    def test_comp5_preserves_values_outside_picture_but_inside_native_storage(self):
        layout,m=fixture(['05 K PIC X.','05 N PIC S9(4) COMP-5.'])
        raw=b'\xc1'+(32767).to_bytes(2,'big',signed=True)
        p=project(layout,m,raw)
        self.assertEqual(raw,reconstruct(m,p['values'],p['metadata']))
        self.assertEqual('numeric(5,0)',m['fields'][1]['sql_type'])

    def test_ambiguous_organization_refused(self):
        for kind in ('','INDEXED NONINDEXED'):
            text='//SYSIN DD *\n DEFINE CLUSTER (NAME(X) KEYS(1 0) RECORDSIZE(2 2) '+kind+')\n/*'
            with self.assertRaisesRegex(ValueError,'organization'):idcams(text,'x.jcl')


if __name__=='__main__':unittest.main()
