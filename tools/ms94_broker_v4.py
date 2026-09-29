"""Dedicated local builder MCP. Public contracts/API, bounded offline compilation only."""
from pathlib import Path
import hashlib,json,re,threading,uuid
from tools.ms94_v3_development import api,structural,compile_candidate,PUBLIC
from lightyear_calibration.contracts import require,read_json
from lightyear_calibration.journey_order import file_hash,save


class BuilderTools:
    def __init__(self, root, maximum=5, session_id=None):
        require(type(maximum) is int and 1<=maximum<=10,'Invalid development compilation limit')
        self.root=Path(root).resolve();self.maximum=maximum;self.used=0;self.lock=threading.Lock()
        session_id=session_id or uuid.uuid4().hex
        require(re.fullmatch(r'[a-z0-9-]{1,64}',session_id) is not None,'Invalid tool session identifier')
        self.session=self.root/'work/ms93/builder-workspaces'/('session-'+session_id)
        self.session.mkdir(parents=True,exist_ok=True)
        self.pins={p.name:file_hash(p) for p in (self.root/PUBLIC).iterdir() if p.is_file()}
        self.image=read_json(self.root/'work/ms87/local-runtime.json')['runner_image']
        declaration={'public_sha256':self.pins,'compiler_image':self.image,
             'max_compilations':maximum,'private_judge_access':False,'native_database_execution':False}
        path=self.session/'declaration.json'
        if path.exists():require(read_json(path)==declaration,'Tool session declaration changed')
        else:save(path,declaration)
        self.used=len(list(self.session.glob('*/invocation.json')))

    def guard(self):
        require(all(file_hash(self.root/PUBLIC/name)==sha for name,sha in self.pins.items()),'Public tool inputs changed')
        require(read_json(self.root/'work/ms87/local-runtime.json')['runner_image']==self.image,'Compiler image changed')

    def public_contract(self, scenario):
        self.guard();require(scenario in ('operations','procure-to-pay'),'Unknown scenario')
        return read_json(self.root/PUBLIC/(scenario+'.json'))

    def support(self):
        self.guard();return {'source':(self.root/PUBLIC/'JourneySupport.java').read_text(encoding='utf-8'),
                             'sha256':self.pins['JourneySupport.java']}

    def compile(self, source):
        with self.lock:
            self.used=len(list(self.session.glob('*/invocation.json')))
            self.guard();require(self.used<self.maximum,'Development compile budget exhausted')
            require(isinstance(source,str) and len(source.encode('utf-8'))<=60000,'Candidate exceeds bound')
            self.used+=1;folder=self.session/str(self.used);folder.mkdir();candidate=folder/'LightyearOperationsTest.java'
            candidate.write_text(source,encoding='utf-8',newline='\n')
            save(folder/'invocation.json',{'candidate_sha256':file_hash(candidate),'ordinal':self.used})
            try:result=compile_candidate(self.root,candidate)
            except Exception as exc:result={'status':'development-tool-error','error_type':type(exc).__name__}
            save(folder/'receipt.json',result);return result


def create_server(root, maximum=5, session_id=None):
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations
    broker=BuilderTools(root,maximum,session_id)
    server=MCPServer('Lightyear public journey development',version='1.0.0',instructions=
        'Read the public contract and pinned API signatures. Use the deterministic support class. '
        'Compile before proposing a candidate. No private gate, database or expected business outputs are available. '
        'Compilation success is not native execution or business correctness.')
    read=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)
    write=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)
    @server.tool(annotations=read)
    def public_contract(scenario: str) -> dict:
        """Read the declared public input, structural and trace contract."""
        return broker.public_contract(scenario)
    @server.tool(annotations=read)
    def public_api(class_name: str, method: str = '') -> dict:
        """Read signatures from a hash-verified, pinned allowlisted application class."""
        broker.guard();return api(broker.root,class_name,method)
    @server.tool(annotations=read)
    def deterministic_support() -> dict:
        """Read the reusable trace, typed-posting and transaction-cleanup component."""
        return broker.support()
    @server.tool(annotations=read)
    def check_structure(source: str) -> dict:
        """Validate candidate bounds and declared class before compilation."""
        broker.guard();return structural(source)
    @server.tool(annotations=write)
    def compile_candidate_source(source: str) -> dict:
        """Compile in an offline isolated container; consumes one bounded compile slot."""
        return broker.compile(source)
    return server


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--max-compilations',type=int,default=5)
    p.add_argument('--session-id')
    a=p.parse_args();create_server(a.root,a.max_compilations,a.session_id).run(transport='stdio')
