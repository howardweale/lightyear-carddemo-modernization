"""Readable public review and explicit operator signing; never self-approve."""
import argparse,json,re
from html import escape
from pathlib import Path
from lightyear_control_tower.decisions import digest,verify_envelope
from lightyear_control_tower.status_export import atomic_new
from .zos_bindings import ROOT

SHEET=ROOT/'docs/factory/posttran-human-review-sheet.json'
SOURCE=ROOT/'spec/mainframe/public-source/CBTRN02C.cbl'


def packet(sheet):
    return dict(schema='posttran-human-review/1',sheet_sha256=digest(sheet),
        source_sha256=digest(SOURCE.read_text().splitlines()),acceptance_sha256=sheet['acceptance_sha256'],
        reviewer=None,decisions=[dict(index=i,scenario=r['scenario'],id=r['id'],decision=None,reason=None)
                                for i,r in enumerate(sheet['records'])])


def body(sheet,decisions,reviewer):
    expected=packet(sheet)
    if not reviewer or decisions.get('reviewer')!=reviewer:raise ValueError('named-reviewer-required')
    for k in ('schema','sheet_sha256','source_sha256','acceptance_sha256'):
        if decisions.get(k)!=expected[k]:raise ValueError('review-evidence-binding')
    rows=decisions.get('decisions',[])
    if len(rows)!=len(expected['decisions']):raise ValueError('all-ten-decisions-required')
    for actual,want in zip(rows,expected['decisions']):
        if any(actual.get(k)!=want[k] for k in ('index','scenario','id')):raise ValueError('review-record-binding')
        if actual.get('decision') not in ('accept','reject','investigate'):raise ValueError('explicit-decision-required')
        if not isinstance(actual.get('reason'),str) or not actual['reason'].strip():raise ValueError('review-reason-required')
    return dict(**{k:decisions[k] for k in expected},claim='operator review, not independent attestation',
                promotion_authorized=False,model_calls=0)


def sign(sheet,decisions,reviewer,signer):
    return signer.sign(body(sheet,decisions,reviewer))


def verify(sheet,signed,public_key):
    if not verify_envelope(signed,public_key):raise ValueError('review-signature')
    expected=body(sheet,signed,signed.get('reviewer'))
    if {k:v for k,v in signed.items() if k not in ('signature','content_sha256')}!=expected:raise ValueError('review-body')
    return dict(authenticated=True,all_accepted=all(r['decision']=='accept' for r in signed['decisions']),promotion_authorized=False)


def render(sheet):
    rows=[];source=SOURCE.read_text().splitlines()
    for i,r in enumerate(sheet['records']):
        anchor=r['source']
        match=re.fullmatch(r'spec/mainframe/public-source/CBTRN02C.cbl:([0-9,\-]+)',anchor)
        if not match:raise ValueError('review-source-anchor')
        excerpts=[]
        for part in match[1].split(','):
            ends=list(map(int,part.split('-')));start=ends[0];end=ends[-1]
            if not 1<=start<=end<=len(source):raise ValueError('review-source-lines')
            excerpts.extend(f'{j}: {source[j-1]}' for j in range(start,end+1))
        fields=sorted(set(r['input'])|set(r['twin_output']))
        table='<table><tr><th>Field</th><th>Public input</th><th>Twin output</th></tr>'+''.join(
            '<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in (f,r['input'].get(f,'—'),r['twin_output'].get(f,'—')))+'</tr>' for f in fields)+'</table>'
        rows.append(f'<section><h2>{i+1}. {escape(r["scenario"])} / {escape(r["id"])}</h2><p><b>Expected:</b> {escape(r["expected_result"])}</p>'+table+
            '<details><summary>'+escape(anchor)+'</summary><pre>'+escape('\n'.join(excerpts))+'</pre></details>'+
            f'<p><label>Decision <select id="decision-{i}"><option value="">Choose</option><option>accept</option><option>reject</option><option>investigate</option></select></label></p><label>Reason <textarea id="reason-{i}" rows="2"></textarea></label></section>')
    data=json.dumps(packet(sheet)).replace('<','\\u003c')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>POSTTRAN operator review</title>
<style>body{font:16px system-ui;max-width:1150px;margin:2rem auto;padding:1rem;color:#183148;background:#f7f9fc}section{background:white;border:1px solid #ccd;padding:1rem;margin:1rem 0}table{border-collapse:collapse;width:100%;font:13px monospace}td,th{border:1px solid #ccd;padding:.4rem;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere}pre{overflow:auto;font-size:12px}textarea{width:98%}button,select,input{font:inherit;padding:.5rem}</style>
<h1>POSTTRAN: ten public records for operator review</h1><p>The twin remains provisional. Review each input, output and source-based expected result. This page creates an unsigned decision file; it neither signs nor promotes evidence.</p>
<label>Your name <input id="reviewer" autocomplete="name"></label>'''+''.join(rows)+'''
<button id="download">Download my unsigned decisions</button><p id="message" role="status"></p>
<h2>Sign through the existing operator flow</h2><p>After reviewing the downloaded JSON, run the documented <code>python -m lightyear_mainframe.posttran_review sign</code> command on your authority host. Keep your operator key local. No key is entered into this page.</p>
<script>const packet='''+data+''';document.getElementById('download').onclick=()=>{packet.reviewer=document.getElementById('reviewer').value.trim();for(const row of packet.decisions){row.decision=document.getElementById('decision-'+row.index).value;row.reason=document.getElementById('reason-'+row.index).value.trim();}if(!packet.reviewer||packet.decisions.some(r=>!r.decision||!r.reason)){document.getElementById('message').textContent='Enter your name and a decision and reason for every record.';return;}const url=URL.createObjectURL(new Blob([JSON.stringify(packet,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='posttran-decisions-unsigned.json';a.click();URL.revokeObjectURL(url);document.getElementById('message').textContent='Unsigned decisions downloaded. Review before signing.';};</script></html>'''


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['render','sign','verify']);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--decisions',type=Path);p.add_argument('--reviewer');p.add_argument('--operator-key',type=Path);p.add_argument('--public-key',type=Path)
    a=p.parse_args();sheet=json.loads(SHEET.read_bytes())
    if a.action=='render':a.output.write_text(render(sheet),encoding='utf-8');return
    decisions=json.loads(a.decisions.read_bytes())
    if a.action=='sign':
        from .zos_evidence import Signer
        body(sheet,decisions,a.reviewer) # Reject incomplete decisions before accessing the operator's key.
        atomic_new(a.output,sign(sheet,decisions,a.reviewer,Signer(a.operator_key)))
    else:atomic_new(a.output,verify(sheet,decisions,a.public_key.read_bytes()))

if __name__=='__main__':main()
