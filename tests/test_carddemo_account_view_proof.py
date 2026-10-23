"""CI-only account-view scope and strict mutation refusal cases."""
import copy,json,tempfile,unittest
from pathlib import Path
from tools.carddemo_account_view_proof import SCOPE,CLASSES,check_scope,evaluate
ROOT=Path(__file__).resolve().parents[1]
class AccountViewProofTests(unittest.TestCase):
    def test_inventory_claims_and_source_bindings_cannot_be_reduced(self):
        self.assertEqual(35,check_scope(ROOT)['paragraph_occurrences'])
        original=json.loads((ROOT/SCOPE).read_bytes())
        for defect in ('inventory','hash','class','claim','independent','move','oracle','service'):
            scope=copy.deepcopy(original)
            if defect=='inventory':scope['source']['inventory'].pop(6)
            elif defect=='hash':scope['source']['sha256']='0'*64
            elif defect=='class':scope['required_mutation_classes']=[]
            elif defect=='claim':scope['whole_screen_idiomatic']=True
            elif defect=='independent':scope['independent_full_slice_required']=False
            elif defect=='move':scope['source_moves'].pop()
            elif defect=='oracle':scope['oracle_sha256']='0'*64
            else:scope['service_original_sha256']='0'*64
            with self.subTest(defect=defect),self.assertRaises(ValueError):check_scope(ROOT,scope)
    def test_empty_missing_and_non_killed_mutants_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'mutations.xml'
            self.assertFalse(evaluate(path)['passed'])
            for status in ('SURVIVED','TIMED_OUT','NO_COVERAGE','RUN_ERROR','MEMORY_ERROR'):
                rows=[]
                for name in CLASSES:
                    for i in range(10):
                        state='KILLED' if i<8 else status
                        rows.append(f'<mutation status="{state}"><mutatedClass>ai.lightyear.carddemo.{name}$Nested</mutatedClass></mutation>')
                path.write_text('<mutations>'+''.join(rows)+'</mutations>')
                self.assertFalse(evaluate(path)['passed'],status)
            path.write_text('<mutations><mutation status="KILLED"><mutatedClass>ai.lightyear.carddemo.Unrelated</mutatedClass></mutation></mutations>')
            self.assertFalse(evaluate(path)['passed'])
            path.write_text('<mutations>'+''.join(f'<mutation status="KILLED"><mutatedClass>ai.lightyear.carddemo.{name}</mutatedClass></mutation>' for name in CLASSES)+'</mutations>')
            self.assertTrue(evaluate(path)['passed'])

    def test_service_oracle_requires_exact_original_executable_bytes(self):
        from tools.carddemo_account_view_proof import SERVICE_ORACLE,check_service_oracle
        original=(ROOT/SERVICE_ORACLE).read_text();scope=json.loads((ROOT/SCOPE).read_text())
        check_service_oracle(original,scope['service_original_sha256'])
        check_service_oracle(original.replace('\n','\r\n'),scope['service_original_sha256'])
        for bad in (original.replace('AccountViewProjectionOracle','AccountViewService'),original+'// changed\n',
                    original.replace('if(acct==null)missing','if(acct!=null)missing')):
            self.assertNotEqual(original,bad)
            with self.assertRaises(ValueError):check_service_oracle(bad,scope['service_original_sha256'])

    def test_changed_service_route_and_removed_source_annotation_are_refused(self):
        from tools.carddemo_account_view_proof import JAVA
        scope=json.loads((ROOT/SCOPE).read_bytes())
        paths=[SCOPE,scope['source']['path'],'factory/carddemo-web/service/pom.xml',
               'factory/carddemo-web/service/account-view-proof.pom.xml',
               'factory/carddemo-web/service/supplemental-tests/account-view/java/ai/lightyear/carddemo/AccountViewProjectionOracle.java',
               JAVA+'AccountViewRendering.java',JAVA+'AccountViewService.java',JAVA+'ScreenProjection.java']
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in paths:
                target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/path).read_bytes())
            self.assertEqual(35,check_scope(root)['paragraph_occurrences'])
            path=JAVA+'AccountViewService.java';original=(root/path).read_text()
            route='projection.apply(frame,rows.get("acctdata"),rows.get("custdata"))'
            annotation='    @CobolSource(program="COACTVWC", paragraph="0000-MAIN", lines="262-393")'
            for bad in (original.replace(annotation+'\n',''),original.replace(annotation,annotation+'\n'+annotation),
                        original.replace(route,route.replace('rows.get("custdata")','rows.get("acctdata")')),
                        original.replace(route,'projection.apply(frame,null,null)'),
                        original.replace('if(acct==null)missing','if(acct!=null)missing')):
                self.assertNotEqual(original,bad);(root/path).write_text(bad)
                with self.assertRaises(ValueError):check_scope(root)
            (root/path).write_text(original)
            path=JAVA+'AccountViewRendering.java';original=(root/path).read_text()
            for bad in (original.replace('lines="460-535"','lines="460-534"'),original.replace('ssn.substring(0,3)','ssn.substring(0,2)')):
                self.assertNotEqual(original,bad);(root/path).write_text(bad)
                with self.assertRaises(ValueError):check_scope(root)

    def test_metadata_labels_and_partial_projection_cannot_be_counted_as_retirements(self):
        original=json.loads((ROOT/SCOPE).read_bytes())
        self.assertEqual(38,check_scope(ROOT)['source_label_occurrences'])
        self.assertEqual(35,check_scope(ROOT)['paragraph_occurrences'])
        for defect in ('missing','duplicate','metadata','retirement','count'):
            scope=copy.deepcopy(original)
            if defect=='missing':scope['procedure_inventory'].pop()
            elif defect=='duplicate':scope['procedure_inventory'].append(scope['procedure_inventory'][0])
            elif defect=='metadata':scope['procedure_inventory'].insert(0,scope['source']['inventory'][0])
            elif defect=='retirement':scope['retirement_accounting']['complete_paragraph_retirements']=1
            else:scope['retirement_accounting']['procedure_occurrences']=38
            with self.subTest(defect=defect),self.assertRaises(ValueError):check_scope(ROOT,scope)
