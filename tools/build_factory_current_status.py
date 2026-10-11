"""Generate the current operator view from explicit decision/register/receipt inputs."""
import argparse,json
from hashlib import sha256
from pathlib import Path
from lightyear_control_tower.decisions import digest
from lightyear_mainframe.zos_bindings import ROOT

INPUTS=(
 'docs/factory/howard-decisions-2026-10-11b.json',
 'docs/factory/keep-or-fix-register.json',
 'docs/factory/posttran-decisions-unsigned-2026-10-11.json',
 'docs/factory/posttran-second-opinion/dedicated-transport-plan-2026-10-11.json',
 'docs/factory/b07-prefreeze-power-2026-10-11.json',
 'docs/factory/ci-times-316-320-2026-10-11.json',
 'docs/factory/posttran-second-opinion/attempt-1-public-summary-2026-10-11.json',
)

def generate(root=ROOT):
    root=Path(root);data={p:json.loads((root/p).read_bytes()) for p in INPUTS}
    d=data[INPUTS[0]];r=data[INPUTS[1]];review=data[INPUTS[2]];plan=data[INPUTS[3]];power=data[INPUTS[4]];ci=data[INPUTS[5]]
    attempt=data[INPUTS[6]]
    for sealed in (d,plan,power,attempt):
        if digest({k:v for k,v in sealed.items() if k!='content_sha256'})!=sealed['content_sha256']:raise ValueError('status-input-seal')
    if attempt['plan_sha256']!=plan['content_sha256']:raise ValueError('status-attempt-plan-binding')
    rows=[{'path':p,'lf_sha256':sha256((root/p).read_text(encoding='utf-8').encode()).hexdigest()} for p in INPUTS]
    view={'schema':'factory-current-status/1','decision_time':d['decided_at'],'inputs':rows,'conditional_threshold':d['scenario_threshold_2'],
      'unsigned_review_accepted':sum(x['decision']=='accept' for x in review['decisions']),
      'signature_verified':False,'posttran_plan_sha256':plan['content_sha256'],'model_execution_authorized':False,
      'posttran_attempt_1':attempt,'posttran_phase2_authorized':False,
      'b06_execution_authorized':False,'b06_window':d['execution']['b06_window'],'b06_request_due':d['execution']['b06_request_due'],
      'register_dispositions':[{k:x[k] for k in ('id','disposition')} for x in r['defects']],
      'b07_freeze_ready':power['freeze_ready'],'latest_ci_collection':ci['checked_at']}
    view['content_sha256']=digest(view)
    lines=['# Current factory status','','Generated from named decision files, the keep-or-fix register and the latest bound receipts below. This view is documentation, not an execution approval. Historical milestones remain historical.','',
      f"Decision time: {d['decided_at']}.",'',
      '- B06: October 13, 9 AM-noon PDT request; delivery due Monday October 12, 5 PM PDT. Exact executable commit and request seal need Howard\'s one-line go. Engineering execution remains held.',
      f"- POSTTRAN: {view['unsigned_review_accepted']}/10 unsigned operator acceptances received and bound to the historical sheet; Howard's signature remains outstanding.",
      f"- POSTTRAN Phase 1 plan: `{plan['content_sha256']}`. Operator attempt 1 completed at {attempt['finished_at']}: {attempt['usage']['input_tokens']} input and {attempt['usage']['output_tokens']} output tokens. Receipt and artifact hashes verified locally; compilation and Phase 1 validation remain pending. Phase 2 is unapproved; no further model call is authorized by this status view.",
      '- scenario-threshold/2: conditionally approved as amended, not effective until B1 completes, remaining equivalence arguments are accepted and the current-head compiled campaign satisfies the gate.',
      '- Equivalence sample: AI-assisted operator review accepted by Howard; not independent human attestation. The TWO-BYTES mutant remains unresolved for z/OS-facing claims.',
      '- B07: 72 analysis slots per arm, graph versus search, two runners, at most 14 calendar days. The power limitation requires review before freezing. Spending remains unapproved; B06 Part 6 and graph coverage precede trials.','',
      '## Recorded legacy dispositions','']
    lines += [f"- {x['id']}: {x['disposition']}" for x in view['register_dispositions']]
    lines += ['', '## Evidence inputs','']
    lines += [f"- [{x['path'].split('/')[-1]}]({Path(x['path']).relative_to('docs/factory').as_posix()}): LF-normalized SHA-256 `{x['lf_sha256']}`" for x in rows]
    lines += ['',f"Generated view seal: `{view['content_sha256']}`.",'','Regenerate with `python -B tools/build_factory_current_status.py`; CI uses `--check` to refuse stale output. Missing or changed source records require regeneration and review. No approval is inferred from a filename, unsigned acceptance or a green CI badge.','']
    return view,'\n'.join(lines)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    view,text=generate();base=ROOT/'docs/factory'
    outputs={base/'current-status.md':text,base/'current-status.json':json.dumps(view,indent=2)+'\n'}
    for path,content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8')!=content:raise SystemExit('stale current status: '+str(path))
        else:path.write_text(content,encoding='utf-8',newline='\n')
