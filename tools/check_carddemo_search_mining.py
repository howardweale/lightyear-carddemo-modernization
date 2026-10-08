"""Measure source-derived abbreviations on a local public CardDemo checkout.

No embeddings, model calls, labels or benchmark promotion. Source values remain
local; the report contains counts and mined name-contraction hypotheses only.
"""
import argparse,json,subprocess
from pathlib import Path
from lightyear_knowledge_graph.model import KnowledgeGraph
from lightyear_knowledge_graph.extractors import extract_legacy
from lightyear_knowledge_graph.hybrid import abbreviations,indexable
from lightyear_control_tower.decisions import digest


def measure(root):
    root=Path(root).resolve()
    graph=KnowledgeGraph('public-carddemo-mining',[],{});extract_legacy(graph,root)
    nodes=list(graph.nodes.values());files={}
    for n in nodes:
        n['source']=[]
        for e in n.get('evidence',[]):
            p=(root/e['path']).resolve()
            if not p.is_relative_to(root) or not p.is_file():raise ValueError('source evidence path')
            if p not in files:files[p]=p.read_text(encoding='utf-8',errors='strict').splitlines()
            n['source'].append(dict(text='\n'.join(files[p][e['line_start']-1:e['line_end']])))
    body=dict(schema='carddemo-search-mining/1',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        source_files=len(files),nodes=len(nodes),excluded_paragraph_headers=sum('paragraph' in n['kind'].lower() and not indexable(n) for n in nodes),
        abbreviations=abbreviations(nodes),model_calls=0,claim='Deterministic lexical hypotheses only; no semantic correctness or retrieval-quality claim')
    return dict(body,content_sha256=digest(body))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    result=measure(a.root);raw=json.dumps(result,sort_keys=True,indent=2)+'\n'
    if a.output:
        with a.output.open('x',encoding='utf-8') as f:f.write(raw)
    print(raw)
