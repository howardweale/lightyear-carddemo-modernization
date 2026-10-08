"""Host judge producer for customer-factory annotation outcomes.

The executor signs the exact run/context/Verify binding. The separately trusted
judge recomputes all Verify native evidence before countersigning the outcome.
This adapter only supports completed Lightyear Verify INTCALC runs. Other judge
families remain unsupported, never replaced by a caller-supplied replay boolean.
"""
import json
from pathlib import Path
from lightyear_control_tower.decisions import verify_envelope,digest
from .contracts import canonical_hash


def produce(root, *, binding, executor_key, judge_key, signer, expected_head):
    from lightyear_judge.service import replay
    if not verify_envelope(binding,executor_key) or binding.get('schema')!='factory-verify-outcome-binding/1':
        raise ValueError('trusted executor outcome binding required')
    if signer.public!=judge_key:raise ValueError('outcome judge authority differs')
    run,context=binding['run_receipt'],binding['context']
    for record in (run,context):
        if canonical_hash(record,{'content_sha256'})!=record['content_sha256']:raise ValueError('factory outcome hash')
    if (binding['evaluation_class']!='customer-factory' or binding['judge_family']!='lightyear-verify-intcalc'
        or run['annotation_context']['context_sha256']!=context['content_sha256']
        or run['annotation_context']['annotation_ids']!=context['annotation_ids']
        or context['customer_id']!=binding['customer_id']):raise ValueError('factory context binding')
    attempt=binding['attempt_id']
    if not isinstance(attempt,str) or not attempt or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in attempt):
        raise ValueError('attempt identifier')
    root=Path(root)
    result=replay(root,judge_key,expected_head)
    if result['status']!='verified' or result['native_verdicts_replayed']<1:raise ValueError('native judge replay required')
    receipt=json.loads((root/'receipts'/(attempt+'.json')).read_bytes())
    config=json.loads((root/'task.json').read_bytes())
    if (not verify_envelope(receipt,judge_key) or not verify_envelope(config,judge_key)
        or receipt['content_sha256']!=binding['verify_receipt_sha256']
        or receipt['artifact_sha256']!=binding['candidate_sha256']
        or receipt['task_sha256']!=config['content_sha256']
        or config['evaluation_inventory_sha256']!=binding['evaluation_inventory_sha256']
        or receipt['status']!='completed' or receipt['verdict'] not in ('equivalent','divergent')):
        raise ValueError('completed native receipt binding')
    status='passed' if receipt['verdict']=='equivalent' else 'failed'
    if run['status']!=status:raise ValueError('factory/judge verdict disagreement')
    bound_context=dict(annotation_ids=context['annotation_ids'],full_context_sha256=context['content_sha256'])
    return signer.sign(dict(schema='annotation-outcome/1',run_id=run['run_id'],
        run_receipt_sha256=run['content_sha256'],customer_id=binding['customer_id'],
        evaluation_class='customer-factory',context=bound_context,context_sha256=digest(bound_context),
        anchors=binding['anchors'],status=status,independently_replayed=True,
        resolved_categories=[],judge_replay=result,executor_binding_sha256=binding['content_sha256'],
        verify_receipt_sha256=receipt['content_sha256'],model_calls=0,
        claim='Separate judge offline recomputation; operator review, not independent human attestation'))


def main():
    """Explicit host operator command; never invoked by a candidate MCP tool."""
    import argparse
    from lightyear_mainframe.zos_evidence import Signer
    from lightyear_control_tower.status_export import atomic_new
    p=argparse.ArgumentParser()
    for name in ('root','binding','executor-public-key','judge-public-key','judge-private-key','expected-head','output'):
        p.add_argument('--'+name,required=True)
    args=p.parse_args()
    result=produce(args.root,binding=json.loads(Path(args.binding).read_bytes()),
        executor_key=Path(args.executor_public_key).read_bytes(),judge_key=Path(args.judge_public_key).read_bytes(),
        signer=Signer(Path(args.judge_private_key)),expected_head=args.expected_head)
    atomic_new(Path(args.output),result)
    print(json.dumps(dict(content_sha256=result['content_sha256'],model_calls=0)))

if __name__=='__main__':main()
