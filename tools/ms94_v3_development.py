"""Local builder tools: public API signatures, structural checks, offline compiler.

The compiler has no host project mount, DB network, credentials or private judge.
Never returns Maven output verbatim: only closed compiler diagnostics leave it.
"""
import hashlib,json,re,subprocess,uuid
from pathlib import Path
from lightyear_calibration.contracts import require,read_json,seal
from lightyear_calibration.journey_order import file_hash
from lightyear_calibration.qualified_diagnostics import compiler

PUBLIC=Path('factory/idempiere/qualification-ms94-v3/public')
SOURCE_COMMIT='731515dcdd5278b843db33b9d3109d155b881951'
API_FILES={'Doc':'acct/Doc.java','DocManager':'acct/DocManager.java','PO':'model/PO.java','MAcctSchema':'model/MAcctSchema.java',
           'Trx':'util/Trx.java','Query':'model/Query.java','MInvoice':'model/MInvoice.java',
           'MInvoiceLine':'model/MInvoiceLine.java','MOrder':'model/MOrder.java',
           'MInOut':'model/MInOut.java','MPayment':'model/MPayment.java',
           'MOrderLine':'model/MOrderLine.java','MInOutLine':'model/MInOutLine.java',
           'MBPartner':'model/MBPartner.java','MBPartnerLocation':'model/MBPartnerLocation.java',
           'MProduct':'model/MProduct.java','MProductPrice':'model/MProductPrice.java',
           'MAllocationHdr':'model/MAllocationHdr.java','MInventory':'model/MInventory.java',
           'MInventoryLine':'model/MInventoryLine.java','MTax':'model/MTax.java',
           'DB':'util/DB.java','Env':'util/Env.java','MWorkflow':'wf/MWorkflow.java',
           'DocAction':'process/DocAction.java'}


def api(root, name, method=''):
    require(name in API_FILES,'Class is outside the public API allowlist')
    require(not method or re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*',method),'Invalid public method selector')
    repo=root/'work/idempiere-upstream';relative='org.adempiere.base/src/org/compiere/'+API_FILES[name]
    raw=subprocess.run(['git','show',SOURCE_COMMIT+':'+relative],cwd=repo,capture_output=True,check=True).stdout
    working=(repo/relative).read_bytes()
    require(raw.replace(b'\r\n',b'\n')==working.replace(b'\r\n',b'\n'),'Working API source differs from pinned commit')
    # Public signatures only. No private helper bodies or unrelated application data.
    pattern=r'\bpublic\s+(?:(?:static|final|synchronized|abstract)\s+)*(?:[\w.<>\[\]?]+\s+)?\w+\s*\([^)]*\)(?:\s+throws\s+[\w., ]+)?'
    def signatures(data):
        values=[' '.join(m.split()) for m in re.findall(pattern,data.decode('utf-8'))]
        return [v for v in values if not method or re.search(r'\b'+re.escape(method)+r'\s*\(',v)]
    inherited=[]
    parent=re.search(r'\bclass\s+'+re.escape(name)+r'\s+extends\s+(X_[A-Za-z0-9_]+)\b',raw.decode('utf-8'))
    if parent:
        path='org.adempiere.base/src/org/compiere/model/'+parent[1]+'.java'
        data=subprocess.run(['git','show',SOURCE_COMMIT+':'+path],cwd=repo,capture_output=True,check=True).stdout
        require(data.replace(b'\r\n',b'\n')==(repo/path).read_bytes().replace(b'\r\n',b'\n'),'Generated API source differs from pinned commit')
        inherited.append({'class':parent[1],'source_sha256':hashlib.sha256(data).hexdigest(),'signatures':signatures(data)})
    return seal({'tool':'public-api','class':name,'source_commit':SOURCE_COMMIT,
                 'source_sha256':hashlib.sha256(raw).hexdigest(),
                 'workspace_sha256':hashlib.sha256(working).hexdigest(),
                 'source_comparison':'exact-after-CRLF-to-LF-only',
                 'signatures':signatures(raw),'inherited_generated_api':inherited})


def structural(source):
    issues=[]
    if len(source.encode('utf-8'))>60000:issues.append('candidate-too-large')
    if not re.search(r'class\s+LightyearOperationsTest\s+extends\s+AbstractTestCase',source):issues.append('unexpected-test-class')
    forbidden=('ProcessBuilder','Runtime.getRuntime','java.net.','System.getenv','/output/','/verifier/')
    if any(x in source for x in forbidden):issues.append('out-of-scope-capability')
    return {'passed':not issues,'codes':issues}


def compile_candidate(root, candidate):
    candidate=candidate.resolve();area=(root/'work/ms93/builder-workspaces').resolve()
    require(candidate.is_relative_to(area) and candidate.name=='LightyearOperationsTest.java',
            'Compiler input must be in the separate builder workspace')
    require(not any(p.is_symlink() for p in (candidate,*candidate.parents)),'Symbolic compiler input')
    source=candidate.read_text(encoding='utf-8');check=structural(source)
    if not check['passed']:return {'tool':'compile','status':'structural-failure','structural':check,'diagnostics':[]}
    image=read_json(root/'work/ms87/local-runtime.json')['runner_image']
    require(re.fullmatch(r'sha256:[0-9a-f]{64}',image) is not None,'Unpinned compiler image')
    name='ly-ms93-compile-'+uuid.uuid4().hex
    support=root/PUBLIC/'JourneySupport.java'
    script='cp /candidate/LightyearOperationsTest.java /application/org.idempiere.test/src/org/idempiere/test/LightyearOperationsTest.java && cp /support/JourneySupport.java /application/org.idempiere.test/src/org/idempiere/test/JourneySupport.java && cd /application && mvn -o -B test-compile -DskipTests -DmaterializeProduct=none -DassembleRepository=none'
    args=['docker','run','--name',name,'--network','none','--memory','4g','--cpus','2',
          '--cap-drop','ALL','--security-opt','no-new-privileges','--label','lightyear.development=ms93',
          '--mount','type=bind,src='+str(candidate)+',dst=/candidate/LightyearOperationsTest.java,readonly',
          '--mount','type=bind,src='+str(support)+',dst=/support/JourneySupport.java,readonly',
          '--entrypoint','sh',image,'-c',script]
    try:
        process=subprocess.run(args,capture_output=True,timeout=600)
        diagnostics=compiler((process.stdout+process.stderr).decode('utf-8',errors='replace'),
                             root=root,api=read_json(root/'factory/idempiere/analyst-repair/api-provenance.json'))
        return seal({'tool':'compile','candidate_sha256':file_hash(candidate),'image':image,
                     'status':'compiled' if process.returncode==0 else 'compile-failed',
                     'support_sha256':file_hash(support),'exit_code':process.returncode,'diagnostics':diagnostics,'private_judge_access':False,
                     'database_access':False,'network':'none','raw_output_exposed':False})
    except subprocess.TimeoutExpired:
        return {'tool':'compile','status':'timeout','diagnostics':[]}
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,check=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('command',choices=('api','check','compile'))
    p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--class-name');p.add_argument('--candidate',type=Path)
    a=p.parse_args();root=a.root.resolve()
    value=api(root,a.class_name) if a.command=='api' else compile_candidate(root,a.candidate) if a.command=='compile' else structural(a.candidate.read_text(encoding='utf-8'))
    print(json.dumps(value,indent=2))
