"""Small synthetic input fixtures; actual archived evidence is built only in CI."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from tools.build_intcalc_current_releasability import assess_data, render, ordered_state, EVIDENCE, CONSTANT_IDS
from lightyear_mainframe.equivalence_evidence import seal
from lightyear_factory.release_grade import NAMES


def signed_shape(value):
    value = {k:v for k,v in value.items() if k != 'content_sha256'}
    return dict(value,content_sha256=seal(value))


def fixture():
    head = 'a'*40
    fresh = [dict(id=name,status='killed-divergent') for name in sorted(CONSTANT_IDS)]
    constants = {name:dict(mutants=[dict(id=row['id'],status=row['status'],record_sha256=seal(row),
        valid_comparisons=1,evidence_complete=True,caught_comparison=True)]) for name,row in zip(('name','city','zip'),fresh)}
    threshold = signed_shape(dict(current_head=head,business=dict(covered=1,total=1,fraction='1/1'),
        io=dict(covered=1,total=2,fraction='1/2'),distinct_values_per_output_field={'name':1},below_two_values=['name']))
    projection = signed_shape(dict(head=head,raw_thresholds={s:dict(kill_rate='3/3') for s in ('twin','zos-facing')},
        projected_thresholds={s:dict(kill_rate='3/3') for s in ('twin','zos-facing')},
        independent_crosscheck={s:dict(passed=True) for s in ('twin','zos-facing')},overlays=[]))
    data = {'INTCALC/summary.json':signed_shape(dict(current_head=head,expected_sites=3)),
        'INTCALC/loader-domain-review-projection.json':projection,
        'INTCALC/request-06-rehearsal.json':signed_shape(dict(head=head,run_id=1,disposable_ci_signatures_only=True,
            releasable=False,reasons=['provisional-or-engineering-evidence'])),
        'INTCALC/constant-field-evidence.json':constants,
        'INTCALC/threshold-2-by-scope.json':{'twin':threshold},
        'POSTTRAN/threshold-2-by-scope.json':{'twin':threshold}}
    index=dict(head=head,run_id=1,sources=[dict(files={EVIDENCE+'/INTCALC/request-06-rehearsal.json':'b'*64})])
    return data,fresh,index


class CurrentReleasabilityTests(unittest.TestCase):
    def assess(self,data,fresh,index,**kwargs):
        return assess_data(data,fresh,index_ref=dict(path=EVIDENCE+'/index.json',sha256='c'*64),index=index,
            grade=kwargs.get('grade',{name:False for name in NAMES}),
            ordered=kwargs.get('ordered',dict(state='unknown',complete=False,reason='current-ordered-decision-proof-not-supplied')))

    def test_changed_constant_changes_measured_text_and_blocker(self):
        data,fresh,index=fixture()
        before=self.assess(data,fresh,index)
        fresh[0]['status']='survived'
        row=data['INTCALC/constant-field-evidence.json']['name']['mutants'][0]
        row.update(status='survived',caught_comparison=False,record_sha256=seal(fresh[0]))
        projection=data['INTCALC/loader-domain-review-projection.json']
        for value in projection['raw_thresholds'].values():value['kill_rate']='2/3'
        data['INTCALC/loader-domain-review-projection.json']=signed_shape(projection)
        after=self.assess(data,fresh,index)
        self.assertNotEqual(render(before),render(after))
        self.assertEqual('2/3',after['raw_kill_rate'])
        self.assertIn('survived',render(after))
        self.assertEqual([fresh[0]['id']],after['missing_caught_constant_fields'])
        self.assertIn('caught-constant-evidence-required',after['verdict'])
        self.assertFalse(after['release_authorized'])

    def test_rehearsal_hash_and_single_historical_reason_are_preserved(self):
        data,fresh,index=fixture();value=self.assess(data,fresh,index)
        self.assertEqual(data['INTCALC/request-06-rehearsal.json']['content_sha256'],value['rehearsal']['content_sha256'])
        self.assertEqual(['provisional-or-engineering-evidence'],value['rehearsal']['reasons'])
        self.assertIn('b'*64,render(value))
        data['INTCALC/request-06-rehearsal.json']['run_id']=2
        with self.assertRaisesRegex(ValueError,'seal'):self.assess(data,fresh,index)

    def test_checklist_and_ordered_inputs_change_blockers_not_fixed_sentences(self):
        data,fresh,index=fixture()
        missing=self.assess(data,fresh,index)
        complete=self.assess(data,fresh,index,grade={name:True for name in NAMES},
            ordered=dict(state='verified-current',complete=True,reason=None))
        self.assertNotEqual(render(missing),render(complete))
        self.assertEqual([],complete['blockers'])
        self.assertTrue(complete['effective'])
        self.assertFalse(complete['release_authorized'])
        self.assertNotIn('current-ordered-decision-proof-not-supplied',render(complete))
        self.assertNotIn('qualified-oracle-required',render(complete))

    def test_unknown_journal_and_untrusted_claimed_complete_refuse(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            missing=ordered_state(root)
            invalid=ordered_state(root,{'complete':True},b'fixture','d'*64)
            self.assertEqual('unknown',missing['state'])
            self.assertEqual('unverified',invalid['state'])
            self.assertFalse(missing['complete']);self.assertFalse(invalid['complete'])

    def test_mutant_record_and_run_or_head_substitution_refuse(self):
        for changed in ('record','head','run','inventory'):
            data,fresh,index=fixture()
            if changed=='record':data['INTCALC/constant-field-evidence.json']['name']['mutants'][0]['record_sha256']='0'*64
            if changed=='head':index['head']='e'*40
            if changed=='run':index['run_id']=99
            if changed=='inventory':fresh.append(deepcopy(fresh[0]))
            with self.subTest(changed=changed),self.assertRaises(ValueError):self.assess(data,fresh,index)
