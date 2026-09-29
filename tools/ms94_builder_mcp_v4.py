"""Controller-v2 public broker: all five tools have hash-chained closed transcripts."""
import json,threading
from pathlib import Path
from tools.ms94_broker_v4 import BuilderTools
from tools.ms94_v3_development import structural
from tools.ms94_public_api_v4 import api
from lightyear_calibration.contracts import require,read_json,seal,verify
from lightyear_calibration.journey_order import save,file_hash

TOOLS=('public_contract','public_api','deterministic_support','check_structure','compile')
SERVER='qualified_journey_public'


def shape_file(scenario):
    return 'operations-shapes.json' if scenario=='operations' else 'procure-to-pay-shapes.json'


class RecordedTools:
    def __init__(self,root,maximum,session_id):
        self.broker=BuilderTools(root,maximum,session_id);self.lock=threading.Lock()
        self.transcript=self.broker.session/'tool-transcript';self.transcript.mkdir(exist_ok=True)
        self.shapes={s:file_hash(self.broker.root/'factory/idempiere/qualification-ms94-v3/public'/shape_file(s))
                     for s in ('operations','procure-to-pay')}
        config={'shapes':self.shapes,'tools':list(TOOLS),'version':'ms94-public-tools-v4'}
        p=self.transcript/'configuration.json'
        if p.exists():require(read_json(p)==config,'Tool contract changed')
        else:save(p,config)

    def call(self,name,arguments):
        with self.lock:
            require(name in TOOLS,'Unknown public tool')
            previous=sorted(self.transcript.glob('[0-9]*'))
            prev=read_json(previous[-1]/'result.json')['content_sha256'] if previous else None
            folder=self.transcript/f'{len(previous)+1:05d}';folder.mkdir()
            invocation=seal({'tool':name,'arguments':arguments,'ordinal':len(previous)+1,'previous_sha256':prev})
            save(folder/'invocation.json',invocation)
            try:
                self.broker.guard()
                require(all(file_hash(self.broker.root/'factory/idempiere/qualification-ms94-v3/public'/shape_file(s))==h
                            for s,h in self.shapes.items()),'Public shape contract changed')
                if name=='public_contract':
                    s=arguments['scenario'];value=self.broker.public_contract(s)
                    output={'base_contract':value,'shapes':read_json(self.broker.root/'factory/idempiere/qualification-ms94-v3/public'/shape_file(s))}
                elif name=='public_api':output=api(self.broker.root,arguments['class_name'],arguments.get('method',''))
                elif name=='deterministic_support':output=self.broker.support()
                elif name=='check_structure':output=structural(arguments['source'])
                else:output=self.broker.compile(arguments['source'])
            except Exception as exc:
                # Never serialize arbitrary exception prose, source excerpts or DB data.
                output={'status':'tool-rejected','error_code':type(exc).__name__}
            value=seal({'invocation_sha256':invocation['content_sha256'],'output':output})
            save(folder/'result.json',value)
            return output


def transcript(root,session_id):
    p=Path(root)/'work/ms93/builder-workspaces'/('session-'+session_id)/'tool-transcript'
    result=[];previous=None
    for ordinal,folder in enumerate(sorted(p.glob('[0-9]*')),1):
        i=read_json(folder/'invocation.json');v=read_json(folder/'result.json');verify(i);verify(v)
        require(i['ordinal']==ordinal and i['previous_sha256']==previous and v['invocation_sha256']==i['content_sha256'],'Tool transcript chain changed')
        require(i['tool'] in TOOLS,'Undeclared recorded tool')
        result.append({'invocation':i,'result':v});previous=v['content_sha256']
    return result


def create_server(root,maximum,session_id):
    from mcp.server import MCPServer
    broker=RecordedTools(root,maximum,session_id)
    server=MCPServer('Lightyear public journey development',version='2.0.0')
    @server.tool()
    def public_contract(scenario:str)->dict:return broker.call('public_contract',{'scenario':scenario})
    @server.tool()
    def public_api(class_name:str,method:str='')->dict:return broker.call('public_api',{'class_name':class_name,'method':method})
    @server.tool()
    def deterministic_support()->dict:return broker.call('deterministic_support',{})
    @server.tool()
    def check_structure(source:str)->dict:return broker.call('check_structure',{'source':source})
    @server.tool()
    def compile(source:str)->dict:return broker.call('compile',{'source':source})
    return server


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--maximum',type=int,required=True);p.add_argument('--session-id',required=True)
    a=p.parse_args();create_server(a.root,a.maximum,a.session_id).run(transport='stdio')
