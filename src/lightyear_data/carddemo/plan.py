"""Build an inspectable plan without opening a database or executing a workload."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from .schema import pinned, copybook, mapping, idcams, dbd, ddl


def build(root):
    root = Path(root); provenance = pinned(root)
    spec = json.loads((root/'slice.json').read_bytes()); source = root/'upstream'
    def text(path):
        if path not in provenance['files']: raise ValueError('unbound source: '+path)
        return (source/path).read_bytes().decode('utf-8')
    entries = []
    for item in spec['datasets']:
        layout, shift = copybook(text(item['copybook']), item['copybook'])
        m = mapping(item['name'],layout,item['copybook'],idcams(text(item['idcams']),item['idcams']),shift)
        if item['data'] not in provenance['files']: raise ValueError('unbound data')
        entries.append((item, layout, m))
    ims = spec['ims']; hierarchy = dbd(text(ims['dbd']),ims['dbd'])
    for segment in hierarchy['segments']:
        path = ims['segments'][segment['name']]
        layout, shift = copybook(text(path),path,segment=segment['name'])
        seq = segment['sequence']
        definition = dict(name=segment['name'],kind='KSDS' if seq and seq['unique'] else 'RRDS',
            minimum=segment['length'],maximum=segment['length'],key_length=seq['length'] if seq and seq['unique'] else None,
            key_offset=seq['offset'] if seq and seq['unique'] else None,unique=True,relate=None,
            source=ims['dbd'],line=segment['statement']['line'])
        m = mapping(segment['name'],layout,path,[definition],shift);m['segment']=segment
        entries.append(({'name':segment['name'].lower(),'copybook':path,'synthetic':True},layout,m))
    plan = dict(schema='carddemo-data-plan/1',claim_scope='public-source-twin',upstream=provenance,
        configuration_sha256=sha256((root/'slice.json').read_bytes()).hexdigest(),
        mappings=[m for _,_,m in entries],
        unsupported=hierarchy['unsupported'] + [dict(reason='public IMS utility unload framing is not verified',source=ims['public_unload'])],
        read_only_plan=True,execution_authorized=False)
    plan['content_sha256']=sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return plan,entries


def export(plan, out):
    out=Path(out);(out/'mapping').mkdir(parents=True,exist_ok=True)
    for m in plan['mappings']:
        (out/'mapping'/f"{m['table']}.json").write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
        (out/'mapping'/f"{m['table']}.sql").write_text(ddl(m),encoding='utf-8')
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
    (out/'schema.sql').write_text('\n'.join(ddl(m) for m in plan['mappings']),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('spec/modernization/carddemo-data'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();plan,_=build(args.source);export(plan,args.out)


if __name__=='__main__':main()
