import unittest
from lightyear_data.carddemo.volume import check_reconstruction, reconstruction_text
from lightyear_data.carddemo.volume import generated, generated_mapped, boundary_cases, check_browse


class VolumeTests(unittest.TestCase):
    def test_generator_is_unique_and_preserves_nonkey_bytes(self):
        rows=list(generated(b'HEAD0000TAIL',dict(key_offset=4,key_length=4),100))
        self.assertEqual(100,len(set(rows)))
        self.assertTrue(all(r[:4]==b'HEAD' and r[8:]==b'TAIL' for r in rows))
        self.assertEqual('0099'.encode('cp037'),rows[-1][4:8])
        with self.assertRaises(ValueError):list(generated(b'00',dict(key_offset=0,key_length=2),100))

    def test_browse_reference_detects_candidate_reversal(self):
        class BadStore:
            mapping={'keys':[dict(name='K',column='ebcdic_key',key_offset=0,key_length=2)]}
            def browse(self,*args,**kwargs):return [2,1]
        result=check_browse(BadStore(),[b'00',b'99'])
        self.assertLess(result['matched'],result['compared'])

    def test_public_volume_uses_distinct_duplicates_and_pic_x_boundaries(self):
        from pathlib import Path
        from lightyear_data.carddemo.plan import build
        root=Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-data'
        _,entries=build(root)
        for item,layout,m in entries:
            if item.get('synthetic'):continue
            template=(root/'upstream'/item['data']).read_bytes()[:layout.record_length]
            rows=list(generated_mapped(template,m,20001));k=m['keys'][0]
            keys=[r[k['key_offset']:k['key_offset']+k['key_length']] for r in rows]
            self.assertEqual(len(rows),len(set(keys)))
            if item['name'] in ('usrsec','carddata','cardxref'):
                self.assertEqual(b'\0'*k['key_length'],keys[0]);self.assertEqual(b'\xff'*k['key_length'],keys[1])
            for k in m['keys'][1:]:
                keys=[r[k['key_offset']:k['key_offset']+k['key_length']] for r in rows]
                self.assertEqual(20000,len(set(keys)));self.assertEqual(keys[0],keys[-1])

    def test_edges_and_prefixes_are_explicit(self):
        cases=boundary_cases([b'00',b'99'])
        self.assertIn((b'\0\0',None),cases)
        self.assertIn((b'\xff\xff',None),cases)
        self.assertIn((None,b''),cases)
        self.assertLess(len(cases),60)


class ReconstructionCountTests(unittest.TestCase):
    class Store:
        def bytes(self,row):return row['typed_bytes']

    def test_single_typed_comparison_changes_report_on_corruption(self):
        rows=[dict(source_ordinal=1,typed_bytes=b'first'),dict(source_ordinal=2,typed_bytes=b'second')]
        original=[b'first',b'second']
        good=check_reconstruction(self.Store(),rows,original)
        self.assertEqual(dict(compared=2,matched=2,expected=2,complete=True,equal=True),good)
        rows[1]['typed_bytes']=b'corrupt'
        bad=check_reconstruction(self.Store(),rows,original)
        self.assertFalse(bad['equal']);self.assertEqual(1,bad['matched'])
        self.assertNotEqual(reconstruction_text(good),reconstruction_text(bad))
        self.assertIn('One check; no separate raw replay.',reconstruction_text(good))

    def test_missing_duplicate_and_invalid_ordinals_never_pass(self):
        row=dict(source_ordinal=1,typed_bytes=b'first')
        for rows in ([row],[row,row],[dict(source_ordinal=0,typed_bytes=b'first')],
                     [dict(source_ordinal=True,typed_bytes=b'first')]):
            with self.subTest(rows=rows):
                result=check_reconstruction(self.Store(),rows,[b'first',b'second'])
                self.assertFalse(result['equal']);self.assertFalse(result['complete'])
