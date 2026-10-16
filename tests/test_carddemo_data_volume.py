import unittest
from lightyear_data.carddemo.volume import generated, boundary_cases, check_browse


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

    def test_edges_and_prefixes_are_explicit(self):
        cases=boundary_cases([b'00',b'99'])
        self.assertIn((b'\0\0',None),cases)
        self.assertIn((b'\xff\xff',None),cases)
        self.assertIn((None,b''),cases)
        self.assertLess(len(cases),60)
