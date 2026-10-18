"""CI cross-checks use a second reader, never shared model output as expectations."""
from copy import deepcopy
from pathlib import Path
import unittest

from independent_carddemo_layout import bms_fields, display_layout, decode_display
from lightyear_data.carddemo import screens
from lightyear_data.carddemo.plan import build
from lightyear_data.carddemo.codec import project

ROOT=Path(__file__).resolve().parents[1]


def compare_screen(raw,model):
    independent=bms_fields(raw);shared=[]
    for m in model['maps']:
        fields=[]
        for f in m['fields']:
            row,column=divmod(f['attribute_offset'],m['columns'])
            fields.append(dict(name=f['name'],row=row+1,column=column+1,length=f['length'],
                attributes=sorted(f['attributes']),color=f['color'],highlight=f['highlight']))
        shared.append(dict(name=m['name'],rows=m['rows'],columns=m['columns'],fields=fields))
    if independent!=shared:raise ValueError('independent-bms-mismatch')


class IndependentLayoutTests(unittest.TestCase):
    def test_two_screen_models_and_seeded_shared_length_fault(self):
        source=ROOT/'spec/modernization/carddemo-screens/upstream/app/bms'
        for name in ('COSGN00','COACTUP'):
            with self.subTest(name=name):
                raw=(source/(name+'.bms')).read_bytes();model=screens.parse(raw,name)
                compare_screen(raw,model)
                altered=deepcopy(model);altered['maps'][0]['fields'][0]['length']+=1
                with self.assertRaisesRegex(ValueError,'independent-bms-mismatch'):compare_screen(raw,altered)
                altered=deepcopy(model);altered['maps'][0]['fields'][0]['attribute_offset']+=1
                with self.assertRaisesRegex(ValueError,'independent-bms-mismatch'):compare_screen(raw,altered)
                altered=deepcopy(model);altered['maps'][0]['fields'][0]['attributes']=['UNPROT']
                with self.assertRaisesRegex(ValueError,'independent-bms-mismatch'):compare_screen(raw,altered)

    def test_thousand_public_records_per_layout_against_independent_decoder(self):
        source=ROOT/'spec/modernization/carddemo-data';_,entries=build(source)
        for name in ('acctdata','custdata'):
            item,layout,mapping=next(e for e in entries if e[0]['name']==name)
            fields,length=display_layout((source/'upstream'/item['copybook']).read_bytes())
            self.assertEqual(layout.record_length,length)
            shared_fields=[('FILLER' if f['filler'] else f['path'],f['offset'],f['length']) for f in mapping['fields']]
            self.assertEqual([('FILLER' if f['name']=='FILLER' else f['path'],f['offset'],f['length']) for f in fields],shared_fields)
            data=(source/'upstream'/item['data']).read_bytes()
            self.assertGreaterEqual(len(data),1000*length)
            for ordinal in range(1000):
                raw=data[ordinal*length:(ordinal+1)*length]
                expected=decode_display(raw,fields,length);actual=project(layout,mapping,raw)['values']
                self.assertEqual(set(expected),set(actual),(name,ordinal))
                for field,value in expected.items():
                    self.assertTrue(value==actual[field],(name,ordinal,field))
                    if hasattr(value,'is_signed') and value==0:
                        self.assertEqual(value.is_signed(),actual[field].is_signed(),(name,ordinal,field))

    def test_independent_display_bounds_and_signs(self):
        raw=b'       01 R.\n           05 VALUE PIC S9(2)V9.\n'
        fields,length=display_layout(raw)
        self.assertEqual('-12.3',str(decode_display(bytes.fromhex('f1f2d3'),fields,length)['R.VALUE']))
        for bad in ('f1f213','f1f2da'):
            with self.assertRaises(ValueError):decode_display(bytes.fromhex(bad),fields,length)
        with self.assertRaises(ValueError):display_layout(b'       01 R.\n           05 VALUE PIC 9 COMP.\n')
