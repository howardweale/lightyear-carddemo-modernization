from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from tools.check_record_commit_claims import check,validate_claim,CLAIMS,resolve,references


class RecordCommitTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.git('init','-q');self.git('config','user.email','fixture@example.invalid');self.git('config','user.name','CI fixture')
        (self.root/'source.txt').write_bytes(b'original\n');self.commit('baseline')
        self.base=self.git('rev-parse','HEAD').strip()
        self.claim=dict(reference=self.base,commit=self.base,role='source',source_path='source.txt',
                        source_sha256=sha256(b'original\n').hexdigest())

    def git(self,*args):
        return subprocess.check_output(['git','-c','commit.gpgsign=false',*args],cwd=self.root,text=True)

    def commit(self,message):
        self.git('add','.');self.git('commit','-qm',message)

    def test_resolves_and_verifies_source_bytes(self):
        self.assertEqual(self.base,validate_claim(self.root,self.claim))
        with self.assertRaisesRegex(ValueError,'source-mismatch'):
            validate_claim(self.root,dict(self.claim,source_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'unresolved'):resolve(self.root,'f'*40)
        with self.assertRaisesRegex(ValueError,'merge-parents'):
            validate_claim(self.root,dict(self.claim,role='merge',parents=[],head_commit=self.base,pr=1))

    def test_new_record_requires_specific_claim_and_historical_record_is_untouched(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        (directory/'preserved-2026-10-16.md').write_text('Historical unresolved `ffffffff`.\n')
        self.commit('preserved historical record')
        baseline=self.git('rev-parse','HEAD').strip()
        name='docs/factory/receipt-2026-10-17.md'
        (self.root/name).write_text('Source revision `'+self.base+'`.\n')
        self.commit('new records')
        with self.assertRaisesRegex(ValueError,'claim-required'):check(self.root,baseline)
        (self.root/CLAIMS).write_text(json.dumps(dict(claims=[dict(self.claim,record=name)])))
        self.commit('bound source claim')
        self.assertEqual(1,len(check(self.root,baseline)))

    def test_resolving_wrong_commit_does_not_validate_claim(self):
        (self.root/'source.txt').write_bytes(b'different\n');self.commit('changed source')
        head=self.git('rev-parse','HEAD').strip()
        with self.assertRaisesRegex(ValueError,'source-mismatch'):
            validate_claim(self.root,dict(self.claim,reference=head,commit=head))

    def test_full_content_hash_and_its_short_prefix_are_not_commit_claims(self):
        content='abcdef12'+'3'*56
        self.assertEqual(set(),references([content]))
        self.assertEqual(set(),references(['Evidence digest `abcdef12`.']))
        self.assertEqual(set(),references(['Archive `abcdef12`.'],record='SHA-256: '+content))
        self.assertEqual({'abcdef12'},references(['Commit `abcdef12`.'],record='SHA-256: '+content))
        self.assertEqual({'deadbeef'},references(['SHA-256: '+content+'; head `deadbeef`.']))
        self.assertEqual({'abcdef12'},references(['Unlabelled revision `abcdef12`.']))

    def test_new_past_dated_record_still_requires_a_claim(self):
        name='docs/factory/new-record-2020-01-01.md'
        (self.root/name).parent.mkdir(parents=True)
        (self.root/name).write_text('Source commit `'+self.base+'`.\n')
        self.commit('new record with old date')
        with self.assertRaisesRegex(ValueError,'claim-required'):
            check(self.root,self.base)
        (self.root/CLAIMS).write_text(json.dumps(dict(claims=[dict(self.claim,record=name)])))
        self.commit('bind source')
        self.assertEqual(1,len(check(self.root,self.base)))

    def test_hash_prefix_record_does_not_need_git_resolution(self):
        name='docs/factory/hash-record-2020-01-01.json'
        (self.root/name).parent.mkdir(parents=True)
        (self.root/name).write_text(json.dumps({'sha256':'abcdef12'+'3'*56,'display':'abcdef12'}))
        self.commit('content hash record')
        self.assertEqual([],check(self.root,self.base))


    def test_publication_role_binds_snapshot_bytes_without_source_claim(self):
        claim=dict(reference=self.base,commit=self.base,role='publication',publication_path='source.txt',
                   publication_sha256=sha256(b'original\n').hexdigest())
        self.assertEqual(self.base,validate_claim(self.root,claim))
        with self.assertRaisesRegex(ValueError,'source-mismatch'):
            validate_claim(self.root,dict(claim,publication_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'source-path'):
            validate_claim(self.root,dict(claim,publication_path='../outside'))

    def test_dated_role_correction_preserves_registry_and_cannot_change_evidence(self):
        from tools.check_record_commit_claims import ROLE_CORRECTIONS,current_claims
        old=dict(self.claim,record='docs/factory/old.json')
        registry=self.root/CLAIMS;registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({'claims':[old]}));before=registry.read_bytes()
        new={k:v for k,v in old.items() if k not in ('role','source_path','source_sha256')}
        new.update(role='publication',publication_path=old['source_path'],publication_sha256=old['source_sha256'])
        correction=dict(record=old['record'],reference=old['reference'],
                        previous_claim_sha256=sha256(json.dumps(old,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                        replacement=new)
        data=dict(schema='record-commit-role-corrections/1',prepared_on='2026-10-18',corrections=[correction])
        path=self.root/ROLE_CORRECTIONS;path.write_text(json.dumps(data))
        self.assertEqual([new],current_claims(self.root));self.assertEqual(before,registry.read_bytes())
        new['publication_sha256']='0'*64;path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'changes-evidence'):current_claims(self.root)
        new['publication_sha256']=old['source_sha256'];correction['previous_claim_sha256']='0'*64
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'correction-binding'):current_claims(self.root)

    def test_new_dated_manifest_preserves_old_and_checks_changed_inputs(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        name='docs/factory/authored-status-claim.json'
        (self.root/name).write_text(json.dumps({'source':self.base}))
        original=json.dumps({'claims':[]}).encode()
        (self.root/CLAIMS).write_bytes(original)
        newer=directory/'commit-claims-2026-10-19.json'
        newer.write_text(json.dumps({'claims':[dict(self.claim,record=name)]}))
        self.commit('new dated claims')
        self.assertEqual(1,len(check(self.root,self.base)))
        self.assertEqual(original,(self.root/CLAIMS).read_bytes())
        newer.write_text(json.dumps({'claims':[dict(self.claim,record=name,source_sha256='0'*64)]}))
        self.commit('wrong new claim')
        with self.assertRaisesRegex(ValueError,'source-mismatch'):check(self.root,self.base)


    def test_duplicate_claim_across_dated_manifests_is_refused(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        name='docs/factory/authored-status-claim.json'
        (self.root/name).write_text(json.dumps({'source':self.base}))
        content=json.dumps({'claims':[dict(self.claim,record=name)]})
        (self.root/CLAIMS).write_text(content)
        (directory/'commit-claims-2026-10-19.json').write_text(content)
        self.commit('ambiguous claim')
        with self.assertRaisesRegex(ValueError,'claim-required'):check(self.root,self.base)


    def test_non_dated_registry_is_read_and_checked_without_prose_change(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        registry=directory/'commit-claims-additional.json'
        registry.write_text(json.dumps({'claims':[dict(self.claim,record='docs/factory/old.md')]}))
        self.commit('additional registry')
        self.assertEqual([],check(self.root,self.base))
        baseline=self.git('rev-parse','HEAD').strip()
        registry.write_text(json.dumps({'claims':[dict(self.claim,record='docs/factory/old.md',source_sha256='0'*64)]}))
        self.commit('bad assertion without prose edit')
        with self.assertRaisesRegex(ValueError,'source-mismatch'):check(self.root,baseline)

    def test_later_correction_uses_filename_date_and_later_registry(self):
        from tools.check_record_commit_claims import current_claims
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        old=dict(self.claim,record='docs/factory/prior.md')
        registry=directory/'commit-claims-2026-11-03.json'
        registry.write_text(json.dumps({'claims':[old]}));before=registry.read_bytes()
        new={k:v for k,v in old.items() if k not in ('role','source_path','source_sha256')}
        new.update(role='publication',publication_path=old['source_path'],publication_sha256=old['source_sha256'])
        row=dict(record=old['record'],reference=old['reference'],
                 previous_claim_sha256=sha256(json.dumps(old,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                 replacement=new)
        data=dict(schema='record-commit-role-corrections/1',prepared_on='2026-11-04',corrections=[row])
        correction=directory/'commit-claim-role-corrections-2026-11-04.json'
        correction.write_text(json.dumps(data))
        self.assertEqual([new],current_claims(self.root));self.assertEqual(before,registry.read_bytes())
        self.commit('later correction and registry')
        self.assertEqual([],check(self.root,self.base))
        data['prepared_on']='2026-10-18';correction.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'correction-schema'):current_claims(self.root)
        data['prepared_on']='2026-11-04';correction.write_text(json.dumps(data))
        data['prepared_on']='2026-11-05'
        (directory/'commit-claim-role-corrections-2026-11-05.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'correction-duplicate'):current_claims(self.root)

    def test_malformed_registry_and_correction_metadata_fail_closed(self):
        from tools.check_record_commit_claims import current_claims
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        registry=directory/'commit-claims-future.json'
        for data in ([],{}, {'claims':{}}, {'claims':[1]}):
            with self.subTest(registry=data):
                registry.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'claims-schema'):current_claims(self.root)
        registry.write_text(json.dumps({'claims':[]}))
        for filename,prepared in (('bad','2026-11-04'),('2026-02-30','2026-02-30')):
            correction=directory/('commit-claim-role-corrections-'+filename+'.json')
            correction.write_text(json.dumps(dict(schema='record-commit-role-corrections/1',prepared_on=prepared,corrections=[])))
            with self.assertRaisesRegex(ValueError,'correction-date'):current_claims(self.root)
            correction.unlink()
        correction=directory/'commit-claim-role-corrections-2026-11-04.json'
        for data in ([],{},dict(schema='record-commit-role-corrections/1',prepared_on='2026-11-04',corrections={}),
                     dict(schema='record-commit-role-corrections/1',prepared_on='2026-11-04',corrections=[1])):
            with self.subTest(correction=data):
                correction.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'correction-schema'):current_claims(self.root)

    def test_named_dated_manifest_preserves_both_existing_dated_files(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        name='docs/factory/retention-summary-2026-10-19.md'
        (self.root/name).write_text('Source revision `'+self.base+'`.\n')
        frozen={self.root/CLAIMS:b'{"claims": []}\n',
                directory/'commit-claims-2026-10-19.json':b'{"claims":[]}\n'}
        for path,raw in frozen.items():path.write_bytes(raw)
        newer=directory/'commit-claims-intcalc-retention-2026-10-19.json'
        newer.write_text(json.dumps({'claims':[dict(self.claim,record=name)]}))
        self.commit('named dated claims')
        self.assertEqual(1,len(check(self.root,self.base)))
        for path,raw in frozen.items():self.assertEqual(raw,path.read_bytes())
        newer.write_text(json.dumps({'claims':[dict(self.claim,record=name,source_sha256='0'*64)]}))
        self.commit('invalid named claim')
        with self.assertRaisesRegex(ValueError,'source-mismatch'):check(self.root,self.base)
        for path,raw in frozen.items():self.assertEqual(raw,path.read_bytes())

    def test_named_and_bare_dated_duplicate_claims_remain_ambiguous(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        name='docs/factory/authored-status-claim.json'
        (self.root/name).write_text(json.dumps({'source':self.base}))
        content=json.dumps({'claims':[dict(self.claim,record=name)]})
        for filename in ('commit-claims-2026-10-19.json','commit-claims-intcalc-retention-2026-10-19.json'):
            (directory/filename).write_text(content)
        self.commit('duplicate across named and bare dated manifests')
        with self.assertRaisesRegex(ValueError,'claim-required'):check(self.root,self.base)


    def test_named_dated_registry_preserves_existing_and_rejects_bad_or_duplicate_claim(self):
        directory=self.root/'docs/factory';directory.mkdir(parents=True)
        name='docs/factory/l10-note.md'
        (self.root/name).write_text('Source `'+self.base+'`.\n')
        original=json.dumps({'claims':[]}).encode()
        (self.root/CLAIMS).write_bytes(original)
        named=directory/'commit-claims-l10-2026-10-20.json'
        content=json.dumps({'claims':[dict(self.claim,record=name)]})
        named.write_text(content);self.commit('named dated registry')
        self.assertEqual(1,len(check(self.root,self.base)))
        self.assertEqual(original,(self.root/CLAIMS).read_bytes())
        named.write_text(json.dumps({'claims':[dict(self.claim,record=name,source_sha256='0'*64)]}))
        self.commit('invalid named claim')
        with self.assertRaisesRegex(ValueError,'source-mismatch'):check(self.root,self.base)
        named.write_text(content)
        (directory/'commit-claims-2026-10-20.json').write_text(content)
        self.commit('duplicate across named and ordinary registry')
        with self.assertRaisesRegex(ValueError,'claim-required'):check(self.root,self.base)


    def test_bound_record_path_is_not_a_commit_but_same_line_head_is(self):
        identifier='abcdef1234567890abcdef1234567890'
        name='docs/calibration/attempts/journey-'+identifier+'/plan.json'
        target=self.root/name;target.parent.mkdir(parents=True);target.write_bytes(b'{}\n')
        self.commit('bound path fixture')
        digest=sha256(target.read_bytes()).hexdigest()
        for path_key, hash_key in (('record','record_sha256'),('path','sha256')):
            row={path_key:name,hash_key:digest}
            line=json.dumps(row)
            self.assertEqual(set(),references([line],root=self.root))
            self.assertEqual({identifier},references([line]))
            row['head']=identifier
            self.assertEqual({identifier},references([json.dumps(row)],root=self.root))
            row['head']=self.base
            self.assertEqual({self.base},references([json.dumps(row)],root=self.root))
        record='docs/factory/bound-path.json'
        (self.root/record).parent.mkdir(parents=True,exist_ok=True)
        (self.root/record).write_text(json.dumps({'record':name,'record_sha256':digest}))
        self.commit('authored inventory row')
        self.assertEqual([],check(self.root,self.base))
        (self.root/record).write_text(json.dumps({'record':name,'record_sha256':digest,'head':self.base}))
        self.commit('commit next to valid path')
        with self.assertRaisesRegex(ValueError,'claim-required'):
            check(self.root,self.base)

    def test_unverified_path_bindings_never_hide_identifiers(self):
        identifier='abcdef1234567890abcdef1234567890'
        name='docs/calibration/journey-'+identifier+'/plan.json'
        target=self.root/name;target.parent.mkdir(parents=True);target.write_bytes(b'{}\n')
        digest=sha256(target.read_bytes()).hexdigest()
        row={'record':name,'record_sha256':digest}
        self.assertEqual({identifier},references([json.dumps(row)],root=self.root))
        self.commit('committed fixture')
        for bad in ('0'*64,'bad',None):
            self.assertEqual({identifier},references([json.dumps(dict(row,record_sha256=bad))],root=self.root))
        duplicate=json.dumps(row)[:-1]+', "record": '+json.dumps(name)+'}'
        self.assertEqual({identifier},references([duplicate],root=self.root))
        for bad_path in ('../'+name,'/'+name,'./'+name,name.replace('/','//')):
            self.assertEqual({identifier},references([json.dumps(dict(row,record=bad_path))],root=self.root))
        self.git('update-index','--chmod=+x',name);self.git('commit','-qm','executable path')
        self.assertEqual({identifier},references([json.dumps(row)],root=self.root))



class GeneratedStatusClaimTests(unittest.TestCase):
    """Real Git output guard fixtures; renderer boundary mocked explicitly."""
    setUp = RecordCommitTests.setUp
    git = RecordCommitTests.git
    commit = RecordCommitTests.commit
    def generated(self):
        from tools.check_record_commit_claims import GENERATED_STATUS
        # A historical commit and a tree identifier are not authored claims.
        view = {'tested_commit': 'f'*40, 'tested_tree': 'e'*40}
        outputs = {GENERATED_STATUS[0]: (json.dumps(view, indent=2)+'\n').encode(),
                   GENERATED_STATUS[1]: b'Captured source '+b'd'*40+b'\n'}
        for name, raw in outputs.items():
            target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        self.commit('generated status fixture')
        return outputs

    def test_exact_generated_identifiers_need_no_authored_claim(self):
        outputs=self.generated()
        with patch('tools.check_record_commit_claims.render_generated_status',return_value=outputs) as render:
            self.assertEqual([],check(self.root,self.base))
            render.assert_called_once_with(self.root)

    def test_both_outputs_are_verified_even_when_only_one_changed(self):
        outputs=self.generated();baseline=self.git('rev-parse','HEAD').strip()
        json_name,md_name=outputs
        changed=dict(outputs);changed[json_name]+=b' '
        (self.root/json_name).write_bytes(changed[json_name]);self.commit('one output changed')
        changed[md_name]+=b'forged sibling'
        with patch('tools.check_record_commit_claims.render_generated_status',return_value=changed):
            with self.assertRaisesRegex(ValueError,'output-mismatch'):check(self.root,baseline)

    def test_forged_generated_output_and_authored_prose_fail(self):
        outputs=self.generated();name=next(iter(outputs))
        (self.root/name).write_bytes(outputs[name]+b' ');self.commit('forged output')
        with patch('tools.check_record_commit_claims.render_generated_status',return_value=outputs):
            with self.assertRaisesRegex(ValueError,'output-mismatch'):check(self.root,self.base)
        (self.root/name).write_bytes(outputs[name])
        (self.root/'docs/factory/authored.md').write_text('Commit '+self.base+'\n')
        self.commit('valid output does not exempt prose')
        with patch('tools.check_record_commit_claims.render_generated_status',return_value=outputs):
            with self.assertRaisesRegex(ValueError,'claim-required'):check(self.root,self.base)

    def test_deleted_renamed_or_executable_output_is_refused(self):
        outputs=self.generated();baseline=self.git('rev-parse','HEAD').strip();name=next(iter(outputs))
        self.git('mv',name,name+'.renamed');self.commit('rename output')
        with patch('tools.check_record_commit_claims.render_generated_status',return_value=outputs):
            with self.assertRaisesRegex(ValueError,'output-mode'):check(self.root,baseline)
        self.git('mv',name+'.renamed',name);self.commit('restore output')
        (self.root/name).unlink();self.commit('delete output')
        with patch('tools.check_record_commit_claims.render_generated_status',return_value=outputs):
            with self.assertRaisesRegex(ValueError,'output-mode'):check(self.root,baseline)
        (self.root/name).write_bytes(outputs[name]);self.commit('restore output')
        self.git('update-index','--chmod=+x',name);self.git('commit','-qm','executable output')
        with patch('tools.check_record_commit_claims.render_generated_status',return_value=outputs):
            with self.assertRaisesRegex(ValueError,'output-mode|dirty-inputs'):check(self.root,baseline)

    def test_renderer_failure_and_dirty_or_changed_sources_are_refused(self):
        outputs=self.generated()
        with patch('tools.check_record_commit_claims.render_generated_status',side_effect=ValueError('source-evidence-invalid')):
            with self.assertRaisesRegex(ValueError,'source-evidence-invalid'):check(self.root,self.base)
        (self.root/'source.txt').write_bytes(b'changed')
        with patch('tools.check_record_commit_claims.render_generated_status') as render:
            with self.assertRaisesRegex(ValueError,'dirty-inputs'):check(self.root,self.base)
            render.assert_not_called()
        (self.root/'source.txt').write_bytes(b'original\n')
        def changing(root):
            (root/'source.txt').write_bytes(b'changed during render')
            return outputs
        with patch('tools.check_record_commit_claims.render_generated_status',side_effect=changing):
            with self.assertRaisesRegex(ValueError,'input-changed'):check(self.root,self.base)

    def test_declared_inputs_must_be_committed_exact_bytes(self):
        from tools.check_record_commit_claims import generated_input_blobs
        self.assertEqual({'source.txt':sha256(b'original\n').hexdigest()},generated_input_blobs(self.root,['source.txt']))
        (self.root/'source.txt').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'input-uncommitted'):generated_input_blobs(self.root,['source.txt'])
        (self.root/'new.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'input-uncommitted'):generated_input_blobs(self.root,['new.json'])
        with self.assertRaisesRegex(ValueError,'input-path'):generated_input_blobs(self.root,['../outside'])

    def test_renderer_wrapper_uses_validated_inputs_and_exact_encoding(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock
        from tools.check_record_commit_claims import render_generated_status, GENERATED_STATUS
        model=object();view={'tested_tree':'e'*40};text='Verified projection\n'
        records=SimpleNamespace(inputs=Mock(return_value=('source.txt',)),
            load=Mock(return_value=model),render=Mock(return_value=(view,text)))
        with patch.dict(sys.modules,{'tools.release_status_records':records}):
            actual=render_generated_status(self.root)
        self.assertEqual({GENERATED_STATUS[0]:(json.dumps(view,indent=2)+'\n').encode(),
                          GENERATED_STATUS[1]:text.encode()},actual)
        records.load.assert_called_once_with(self.root);records.render.assert_called_once_with(model)
        self.assertEqual(2,records.inputs.call_count)
        records.inputs.side_effect=[('source.txt',),('source.txt','untracked.json')]
        with patch.dict(sys.modules,{'tools.release_status_records':records}):
            with self.assertRaisesRegex(ValueError,'input-changed'):render_generated_status(self.root)
        records.inputs.side_effect=None
        def mutate(model):
            (self.root/'source.txt').write_bytes(b'mutated during rendering')
            return view,text
        records.render.side_effect=mutate
        with patch.dict(sys.modules,{'tools.release_status_records':records}):
            with self.assertRaisesRegex(ValueError,'input-uncommitted'):render_generated_status(self.root)

    def test_renderer_cannot_omit_sibling_output(self):
        outputs=self.generated();outputs.pop('docs/factory/current-status.md')
        with patch('tools.check_record_commit_claims.render_generated_status',return_value=outputs):
            with self.assertRaisesRegex(ValueError,'output-set'):check(self.root,self.base)
