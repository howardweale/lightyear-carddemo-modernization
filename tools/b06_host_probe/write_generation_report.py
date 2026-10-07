"""Record bounded host findings and approval without modifying frozen campaigns."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from lightyear_calibration.contracts import canonical, seal
from tools.ms94_b06_executable import verify_snapshot
from tools.b06_host_probe.generation_replay import lambda_linkage, lambda_body, adjacent_target
from tools.b06_host_probe.lambda_form_replay import replay_body


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root=Path.cwd();area=root/'work/b06-observer-v2-host'
    public=root/'docs/calibration/idempiere-ms94/stage-b-06/preparation/observer-v2-generated-proof'
    public.mkdir(exist_ok=False)
    proposal=root/'docs/calibration/idempiere-ms94/stage-b-06/preparation/observer-v2-host-diagnosis/pool-comparison-proposal.md'
    assert sha(proposal)=='31a0f4ff21208456d81ef47bfdef619c68c97bb3615348678c8d2fa7e9a0e3a7'
    approval=seal({'artifact_type':'ms94-b06-pool-operator-approval-transcription/1',
        'proposal_file_sha256':sha(proposal),'policy':'hierarchical-overpass-pool-v1',
        'approved_by':'Howard Weale','approval_source':'explicit user message in this conversation',
        'approval_text':'approving pool comparison proposal. complete generated-class proof, publish five-path snapshot and I will approve through tower.',
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
        'operator_cryptographic_signature':False,'native_runs_authorized':False,'model_calls_authorized':False,
        'review':'operator review; not independent attestation','r10_status':'failed-preserved'})
    (public/'pool-approval.json').write_bytes(canonical(approval))
    local=area/'generation-proof-report';local.mkdir(exist_ok=False)
    tests=subprocess.run([sys.executable,'-B','-m','unittest','tests.test_b06_host_pool_proposal','tests.test_b06_generated_linkage','tests.test_b06_lambda_form_experiment','-v'],capture_output=True)
    (local/'tests.stdout').write_bytes(tests.stdout);(local/'tests.stderr').write_bytes(tests.stderr)
    assert tests.returncode==0
    path=area/'generation-proof-attempt8/observations.json';data=json.loads(path.read_text(encoding='utf-8'));assert data['complete']
    definitions=data['definitions'];gens=[r for r in data['records'] if r['kind']=='generation']
    final=next(r for r in reversed(data['records']) if r['kind']=='checkpoint')
    ids={r['returned_class']['class_object_id'] for r in gens};hidden=set(final['hidden_class_ids'])
    framework=0;roles=[];proofs=[]
    interface=(area/'pool-probe-inputs/surefire59/org/junit/platform/engine/TestEngine.class').read_bytes()
    for r in gens:
        if not r['entry_method'].endswith('spinInnerClass()Ljava/lang/Class;'):continue
        host=r['lambda_factory']['targetClass']['class']
        if host.startswith('org.junit.'):
            source=area/'pool-probe-inputs/surefire59'/(host.replace('.','/')+'.class');framework+=1
        elif host.startswith('HostGenerationTarget$'):
            source=area/'generation-proof-build4'/(host+'.class')
        else:continue
        proof=lambda_body(r,definitions,lambda_linkage(r,definitions,source.read_bytes(),test_engine=interface))
        if host.startswith('HostGenerationTarget$'):
            frames=next(v['stack'] for v in data['records'] if v['kind']=='target-checkpoint' and any(f['class_object_id']==proof['generated_class_object_id'] for f in v['stack']))
            proof=adjacent_target(proof,frames);roles.append(host)
        proofs.append(proof)
    (local/'lambda-proofs.json').write_bytes(canonical({'proofs':proofs}))
    forms=[r for r in gens if 'lambda_form_graph' in r]
    emissions={r['returned_bytes_object_id']:r for r in data['records'] if r['kind']=='generator-bytecode'}
    matched=0;pending=[];links=0
    for r in forms:
        emitted=emissions.get(r['definition_input_object_id'])
        assert emitted and emitted['returned_bytes_hex']==r['definition_input_hex'] and emitted['thread_id']==r['thread_id'];links+=1
        d=definitions[str(r['returned_class']['class_object_id'])]
        m=next(m for m in d['methods'] if m['name']!='<clinit>')
        try: replay_body(d,r['lambda_form_graph'],m['name']);matched+=1
        except ValueError as error:pending.append({'class':d['class'],'reason':str(error)})
    attempts=[]
    for i in range(1,9):
        p=area/(f'generation-proof-attempt{i}/observations/observations.json' if i==1 else f'generation-proof-attempt{i}/observations.json')
        if p.exists():
            v=json.loads(p.read_text(encoding='utf-8'));attempts.append({'attempt':i,'observation_file_sha256':sha(p),'complete':v['complete'],'error':v.get('error'),'elapsed_seconds':v['elapsed_seconds']})
    preserved={}
    for name,h in [('j1-smoke-r10','e5790d832a18ea0272b24a1bfd611ad60aa3f45c340fc68997e3c6ed30409c06'),('j1-smoke-r11',None)]:
        folder=root/'work/b06-execution-snapshots'/name
        if h is None:
            manifests=[p for p in folder.glob('*.json') if 'snapshot' in p.name]
            assert len(manifests)==1
            h=json.loads(manifests[0].read_text())['content_sha256']
        v=verify_snapshot(folder,h);preserved[name]={'snapshot_sha256':h,'unchanged_file_count':len(v['files_sha256'])}
    report=seal({'artifact_type':'ms94-b06-generated-host-progress/1','status':'incomplete-not-native-admission',
        'pool_approval_sha256':approval['content_sha256'],'observer_v2_amendment_sha256':'a6ae76dee979c59badeec20630b54e83dbcaddc85d8467ff3d4e1adb9d4b8898',
        'host':'Windows x64 Corretto 21.0.10+7; pinned native image uses Temurin 21.0.10+7-LTS',
        'observation_file_sha256':sha(path),'source_files_sha256':{p.relative_to(root).as_posix():sha(p) for p in (root/'tools/b06_host_probe').glob('*') if p.is_file()},
        'hidden_classes_at_final_checkpoint':len(hidden),'hidden_classes_with_generator_return':len(hidden&ids),
        'framework_lambda_host_site_and_body_checks':framework,'public_fixture_role_adjacent_target_checks':roles,
        'lambda_form_exact_emission_definition_links':links,'lambda_form_expression_matches':matched,
        'lambda_form_remaining_decoder_rejections':pending,'complete_LambdaForm_proof':False,
        'remaining_work':['Close typed LambdaForm adapter and dynamic-target replay, including all negative controls',
                          'Bind native pinned-JDK/module and actual loader/artifact origins; host Corretto evidence is not a native attestation',
                          'Integrate completed verifier and generation records into production collector and independent replay',
                          'Assemble five-path executable snapshot, verify public commit and request exact Tower decision'],
        'tests':{'exit_code':tests.returncode,'stderr_sha256':sha(local/'tests.stderr')},
        'attempts_preserved':attempts,'preparation_compile_failure_preserved':'build5 syntax error in host observer; tool transcript only, no raw local compiler log retained',
        'frozen_preservation':preserved,'r10_status':'failed-preserved','model_calls':0,'docker_commands':0,'native_pairs':0,
        'target_method_invocations':0,'five_path_snapshot_published':False,'Tower_request_issued':False,
        'timebox_cutoff_exclusive_utc':'2026-10-10T07:00:00Z','review':'operator review; not independent attestation'})
    (public/'report.json').write_bytes(canonical(report))
    print(json.dumps({'approval_sha256':approval['content_sha256'],'report_sha256':report['content_sha256'],'hidden_classes':len(hidden),'linked_hidden_classes':len(hidden&ids),'framework_lambdas':framework,'lambda_form_links':links,'expression_matches':matched,'preserved':preserved},indent=2))


if __name__=='__main__':main()
