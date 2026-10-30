"""Pure conversion of exact fixture Git objects to proposed REST bodies.

No service, filesystem, credentials, intent, ref update, or approval entry.
Inputs are untrusted: digest/relationship equality is NOT provenance. A future
external caller must independently reconstruct and authenticate E/M, original
handoff, current native proof/trust and every fresh publication guard. It must
persist exclusive intent BEFORE any object creation, require each returned ID,
and stop on unknown outcomes without retry. This helper grants no authority.
"""
from base64 import b64encode
from datetime import datetime, timezone
import re
from tools.ci.operator_flow_metadata import LIMITS, MESSAGE, PREFIX, object_id, require

ANCESTORS=('', 'docs/', 'docs/factory/', PREFIX)
MODES={'100644':'blob','100755':'blob','40000':'tree','120000':'blob','160000':'commit'}

def tree_entries(raw):
    require(type(raw) is bytes and len(raw)<=2*1024*1024,'publication-bounded-tree')
    rows=[];offset=0;names=set()
    while offset<len(raw):
        space=raw.find(b' ',offset);end=raw.find(b'\0',space+1)
        require(space>offset and end>space+1 and end+21<=len(raw),'publication-tree-framing')
        mode=raw[offset:space].decode('ascii')
        name=raw[space+1:end];oid=raw[end+1:end+21].hex();offset=end+21
        require(mode in MODES and name not in names and name not in (b'.',b'..')
            and b'/' not in name,'publication-tree-entry')
        # REST paths are Unicode. Refuse unrepresentable original names instead
        # of replacing bytes, quoting them, or silently changing their spelling.
        try:text=name.decode('utf-8')
        except UnicodeDecodeError:raise ValueError('publication-tree-utf8') from None
        require(text.encode('utf-8')==name,'publication-tree-name-roundtrip')
        names.add(name);rows.append((name,mode,oid))
    require(rows==sorted(rows,key=lambda row:row[0]+(b'/' if row[1]=='40000' else b'')),
        'publication-tree-order')
    return rows

def tree_bytes(rows):
    return b''.join(mode.encode()+b' '+name+b'\0'+bytes.fromhex(oid) for name,mode,oid in rows)

def object_requests(candidate,metadata,base_trees,*,expected_executable,expected_candidate):
    """Return ordered (endpoint suffix, expected SHA1, body) tuples, never send.

    base_trees maps the four fixed ancestor paths to original (SHA1, raw bytes).
    They must eventually come from authenticated E; matching supplied values
    alone does not establish that. No output is an approval or guard receipt.
    """
    require(type(candidate) is dict and all(type(x) is str and re.fullmatch('[0-9a-f]{40}',x)
        for x in (expected_executable,expected_candidate)),'publication-exact-expectations')
    require(candidate.get('parent')==expected_executable and candidate.get('commit')==expected_candidate,
        'publication-expected-E-M')
    require(type(metadata) is dict and set(metadata)==set(LIMITS)
        and all(type(v) is bytes and 0<len(v)<=LIMITS[k] for k,v in metadata.items()),
        'publication-original-three-files')
    require(type(base_trees) is dict and set(base_trees)==set(ANCESTORS),'publication-base-ancestors')
    originals={}
    for path,value in base_trees.items():
        require(type(value) is tuple and len(value)==2,'publication-base-tree-shape')
        oid,raw=value
        require(type(oid) is str and object_id('tree',raw)==oid,'publication-base-tree-digest')
        originals[path]=(oid,tree_entries(raw))
    require(originals[''][0]==candidate.get('base_tree'),'publication-base-root')
    for parent,child in zip(ANCESTORS,ANCESTORS[1:]):
        name=child[len(parent):-1].encode()
        require((name,'40000',originals[child][0]) in originals[parent][1],'publication-base-ancestor-link')
    objects=candidate.get('objects')
    require(type(objects) is dict and 1<=len(objects)<=8,'publication-object-inventory')
    for oid,value in objects.items():
        require(type(value) is tuple and len(value)==2 and value[0] in ('blob','tree','commit')
            and type(value[1]) is bytes and len(value[1])<=2*1024*1024,'publication-object-shape')
        require(type(oid) is str and object_id(*value)==oid,'publication-object-digest')
    requests=[];used=set()
    def append(kind,body,payload):
        oid=object_id(kind,body)
        require(objects.get(oid)==(kind,body),'publication-missing-or-changed-object')
        if oid not in used:
            requests.append(({'blob':'blobs','tree':'trees','commit':'commits'}[kind],oid,payload))
            used.add(oid)
        return oid
    blobs={}
    for path in sorted(metadata):
        raw=metadata[path]
        blobs[path]=append('blob',raw,dict(content=b64encode(raw).decode('ascii'),encoding='base64'))
    child_oid=None
    for path in reversed(ANCESTORS):
        rows=list(originals[path][1])
        if path==PREFIX:
            for full,oid in blobs.items():
                name=full[len(path):].encode('ascii')
                require(not any(row[0]==name for row in rows),'publication-retained-metadata')
                rows.append((name,'100644',oid))
        else:
            child=ANCESTORS[ANCESTORS.index(path)+1]
            name=child[len(path):-1].encode('ascii')
            rows=[(n,m,child_oid if n==name else oid) for n,m,oid in rows]
        rows.sort(key=lambda row:row[0]+(b'/' if row[1]=='40000' else b''))
        raw=tree_bytes(rows)
        require(tree_entries(raw)==rows,'publication-tree-roundtrip')
        payload=dict(tree=[dict(path=n.decode('utf-8'),mode='040000' if m=='40000' else m,
            type=MODES[m],sha=oid) for n,m,oid in rows])
        # No base_tree: this is the COMPLETE immediate tree, not an overlay.
        child_oid=append('tree',raw,payload)
    require(child_oid==candidate.get('tree'),'publication-candidate-tree')
    epoch=candidate.get('commit_epoch')
    require(type(epoch) is int and 1<=epoch<10**11,'publication-prepared-epoch')
    identity='Codex <codex@openai.com> '+str(epoch)+' +0000'
    raw=('tree '+child_oid+'\nparent '+expected_executable+'\nauthor '+identity+
        '\ncommitter '+identity+'\n\n'+MESSAGE).encode()
    date=datetime.fromtimestamp(epoch,timezone.utc).isoformat(timespec='seconds')
    person=dict(name='Codex',email='codex@openai.com',date=date)
    oid=append('commit',raw,dict(tree=child_oid,parents=[expected_executable],
        message=MESSAGE,author=dict(person),committer=dict(person)))
    require(oid==expected_candidate and used==set(objects),'publication-exact-object-closure')
    # REST may normalize a commit even when fields are explicit. Exact returned
    # IDs and original object readback remain mandatory in the future caller.
    return tuple(requests)
