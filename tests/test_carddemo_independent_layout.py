"""CI cross-checks use a second reader, never shared model output as expectations."""
from copy import deepcopy
from pathlib import Path
import unittest
import json
import os
from tempfile import TemporaryDirectory
from unittest.mock import patch
from hashlib import sha256

from independent_carddemo_layout import bms_fields, display_layout, decode_display, synthetic_records
from lightyear_data.carddemo import screens
from lightyear_data.carddemo.plan import build
from lightyear_data.carddemo.codec import project

ROOT=Path(__file__).resolve().parents[1]


def save_report(kind,rows):
    directory=os.environ.get('CARDDEMO_INDEPENDENT_REPORT')
    if not directory:return
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    value=dict(schema='carddemo-independent-layout-check/1',kind=kind,results=rows,
        scope='Two BMS layouts; 50 public plus 950 synthetic DISPLAY records per layout. Not 1000 public records or native equivalence.',
        shared_components='Python standard-library cp037 codec and Decimal only; no shared BMS/layout/record parser.',
        tested_commit=os.environ.get('GITHUB_SHA'),
        signed=False,release_authorized=False)
    (out/(kind+'.json')).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


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
        report=[]
        source=ROOT/'spec/modernization/carddemo-screens/upstream/app/bms'
        for name in ('COSGN00','COACTUP'):
            with self.subTest(name=name):
                raw=(source/(name+'.bms')).read_bytes();model=screens.parse(raw,name)
                compare_screen(raw,model)
                report.append(dict(screen=name,source_sha256=sha256(raw).hexdigest(),fields=sum(len(m['fields']) for m in model['maps']),matched=True))
                altered=deepcopy(model);altered['maps'][0]['fields'][0]['length']+=1
                with self.assertRaisesRegex(ValueError,'independent-bms-mismatch'):compare_screen(raw,altered)
                altered=deepcopy(model);altered['maps'][0]['fields'][0]['attribute_offset']+=1
                with self.assertRaisesRegex(ValueError,'independent-bms-mismatch'):compare_screen(raw,altered)
                altered=deepcopy(model);altered['maps'][0]['fields'][0]['attributes']=['UNPROT']
                with self.assertRaisesRegex(ValueError,'independent-bms-mismatch'):compare_screen(raw,altered)

        save_report('screens',report)

    def test_approved_fifty_public_plus_950_synthetic_per_layout(self):
        report=[]
        source=ROOT/'spec/modernization/carddemo-data';_,entries=build(source)
        for name in ('acctdata','custdata'):
            item,layout,mapping=next(e for e in entries if e[0]['name']==name)
            fields,length=display_layout((source/'upstream'/item['copybook']).read_bytes())
            self.assertEqual(layout.record_length,length)
            shared_fields=[('FILLER' if f['filler'] else f['path'],f['offset'],f['length']) for f in mapping['fields']]
            self.assertEqual([('FILLER' if f['name']=='FILLER' else f['path'],f['offset'],f['length']) for f in fields],shared_fields)
            data=(source/'upstream'/item['data']).read_bytes()
            self.assertEqual(50*length,len(data))
            originals=[data[i:i+length] for i in range(0,len(data),length)]
            synthetic=list(synthetic_records(originals,fields,length))
            rows=originals+synthetic
            self.assertEqual(1000,len(rows));self.assertEqual(1000,len(set(rows)))
            first=fields[0]
            self.assertEqual(1000,len({r[first['offset']:first['offset']+first['length']] for r in rows}))
            for ordinal,raw in enumerate(rows):
                expected=decode_display(raw,fields,length);actual=project(layout,mapping,raw)['values']
                self.assertEqual(set(expected),set(actual),(name,ordinal))
                for field,value in expected.items():
                    self.assertTrue(value==actual[field],(name,ordinal,field))
                    if hasattr(value,'is_signed') and value==0:
                        self.assertEqual(value.is_signed(),actual[field].is_signed(),(name,ordinal,field))

            report.append(dict(layout=name,public_records=len(originals),synthetic_records=len(synthetic),
                compared=len(rows),matched=len(rows),public_data_sha256=sha256(data).hexdigest(),
                copybook_sha256=sha256((source/'upstream'/item['copybook']).read_bytes()).hexdigest(),
                synthetic_sha256=sha256(b''.join(synthetic)).hexdigest()))
        save_report('records',report)

    def test_report_changes_when_measured_input_changes(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {'CARDDEMO_INDEPENDENT_REPORT': directory}):
            path=Path(directory)/'records.json'
            save_report('records',[dict(public_records=50,synthetic_records=950,matched=1000)])
            before=path.read_text(encoding='utf-8')
            save_report('records',[dict(public_records=50,synthetic_records=949,matched=999)])
            after=path.read_text(encoding='utf-8')
            self.assertNotEqual(before,after)
            self.assertEqual(999,json.loads(after)['results'][0]['matched'])

    def test_independent_display_bounds_and_signs(self):
        raw=b'       01 R.\n           05 VALUE PIC S9(2)V9.\n'
        fields,length=display_layout(raw)
        self.assertEqual('-12.3',str(decode_display(bytes.fromhex('f1f2d3'),fields,length)['R.VALUE']))
        for bad in ('f1f213','f1f2da'):
            with self.assertRaises(ValueError):decode_display(bytes.fromhex(bad),fields,length)
        with self.assertRaises(ValueError):display_layout(b'       01 R.\n           05 VALUE PIC 9 COMP.\n')
