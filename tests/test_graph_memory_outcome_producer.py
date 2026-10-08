"""Synthetic trust/binding tests; mocked native replay is not qualification."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_mainframe.zos_evidence import initialize_key,Signer
from lightyear_factory.contracts import canonical_hash
from lightyear_factory.outcome_producer import produce


def hashed(body):return dict(body,content_sha256=canonical_hash(body))

class OutcomeProducerTests(unittest.TestCase):
    def test_separate_executor_and_judge_authorities_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('executor','judge'):initialize_key(root/(name+'.pem'))
            executor,judge=Signer(root/'executor.pem'),Signer(root/'judge.pem')
            (root/'receipts').mkdir()
            config=judge.sign(dict(evaluation_inventory_sha256='a'*64))
            receipt=judge.sign(dict(task_sha256=config['content_sha256'],artifact_sha256='b'*64,status='completed',verdict='equivalent'))
            (root/'task.json').write_text(json.dumps(config));(root/'receipts/attempt1.json').write_text(json.dumps(receipt))
            context=hashed(dict(annotation_ids=['hint'],customer_id='customer'))
            run=hashed(dict(run_id='run1',status='passed',annotation_context=dict(context_sha256=context['content_sha256'],annotation_ids=['hint'])))
            body=dict(schema='factory-verify-outcome-binding/1',evaluation_class='customer-factory',judge_family='lightyear-verify-intcalc',
                run_receipt=run,context=context,customer_id='customer',attempt_id='attempt1',verify_receipt_sha256=receipt['content_sha256'],
                candidate_sha256='b'*64,evaluation_inventory_sha256='a'*64,anchors=['field'])
            kwargs=dict(executor_key=executor.public,judge_key=judge.public,signer=judge,expected_head='c'*64)
            replay=dict(status='verified',native_verdicts_replayed=1,journal_head_sha256='c'*64,model_calls=0)
            with patch('lightyear_judge.service.replay',return_value=replay) as native:
                result=produce(root,binding=executor.sign(body),**kwargs)
                self.assertEqual(result['status'],'passed');native.assert_called_once_with(root,judge.public,'c'*64)
                self.assertEqual(result['resolved_categories'],[])
                for field,value in [('candidate_sha256','d'*64),('customer_id','wrong'),('evaluation_class','sealed-holdout'),('verify_receipt_sha256','e'*64)]:
                    with self.subTest(field=field),self.assertRaises(ValueError):produce(root,binding=executor.sign(dict(body,**{field:value})),**kwargs)
                with self.assertRaisesRegex(ValueError,'executor'):produce(root,binding=judge.sign(body),**kwargs)
            with patch('lightyear_judge.service.replay',side_effect=ValueError('native failed')):
                with self.assertRaisesRegex(ValueError,'native failed'):produce(root,binding=executor.sign(body),**kwargs)
