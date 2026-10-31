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


def verify_object_readback(candidate, expected_oid, response):
    """Check untrusted original Git REST readback against original object bytes.

    This is a relationship check only. Caller owns authenticated GET, original
    candidate provenance, current proof, operation approval and host guards.
    No write, retry, repair, callback or authority result is provided.
    """
    require(type(candidate) is dict and type(candidate.get('objects')) is dict
        and type(expected_oid) is str and re.fullmatch('[0-9a-f]{40}', expected_oid),
        'readback-exact-expectation')
    value = candidate['objects'].get(expected_oid)
    require(type(value) is tuple and len(value) == 2 and value[0] in ('blob','tree','commit')
        and type(value[1]) is bytes and len(value[1]) <= 2*1024*1024
        and object_id(*value) == expected_oid, 'readback-original-object')
    kind, original = value
    require(type(response) is dict and response.get('sha') == expected_oid,
        'readback-returned-id')
    if kind == 'blob':
        from base64 import b64decode
        content = response.get('content')
        require(response.get('encoding') == 'base64' and type(content) is str
            and len(content) <= 3*1024*1024 and type(response.get('size')) is int
            and response['size'] == len(original), 'readback-blob-shape')
        # GitHub wraps base64 with newlines. No other normalization is allowed.
        try:
            raw = b64decode(content.replace('\n',''), validate=True)
        except (ValueError, UnicodeError):
            raise ValueError('readback-blob-encoding') from None
    elif kind == 'tree':
        rows = response.get('tree')
        require(response.get('truncated') is False and type(rows) is list
            and len(rows) <= len(original)//23, 'readback-complete-tree')
        parsed = []; total_bytes = 0
        for row in rows:
            require(type(row) is dict and type(row.get('path')) is str
                and type(row.get('mode')) is str and type(row.get('sha')) is str
                and re.fullmatch('[0-9a-f]{40}', row['sha']), 'readback-tree-row')
            mode = row['mode']
            require(mode in ('040000','100644','100755','120000','160000')
                and row.get('type') == MODES[mode.lstrip('0')], 'readback-tree-mode-type')
            name = row['path'].encode('utf-8')
            total_bytes += len(mode.lstrip('0')) + 1 + len(name) + 1 + 20
            require(total_bytes <= 2*1024*1024, 'readback-tree-byte-budget')
            parsed.append((name, mode.lstrip('0'), row['sha']))
        raw = tree_bytes(parsed)
        tree_entries(raw)  # Refuse duplicate/noncanonical/order/path encodings.
    else:
        require(type(response.get('tree')) is dict
            and response['tree'].get('sha') == candidate.get('tree')
            and type(response.get('parents')) is list
            and len(response['parents']) == 1
            and type(response['parents'][0]) is dict
            and response['parents'][0].get('sha') == candidate.get('parent')
            and response.get('message') == MESSAGE, 'readback-commit-links-message')
        identities = []
        for name in ('author','committer'):
            who = response.get(name)
            require(type(who) is dict and who.get('name') == 'Codex'
                and who.get('email') == 'codex@openai.com'
                and type(who.get('date')) is str, 'readback-commit-identity')
            try:
                moment = datetime.fromisoformat(who['date'].replace('Z','+00:00'))
            except ValueError:
                raise ValueError('readback-commit-date') from None
            require(moment.tzinfo is not None and moment.utcoffset().total_seconds() == 0
                and moment.microsecond == 0 and type(candidate.get('commit_epoch')) is int
                and moment.timestamp() == candidate['commit_epoch'], 'readback-commit-time')
            identities.append('Codex <codex@openai.com> '+str(candidate['commit_epoch'])+' +0000')
        raw = ('tree '+candidate['tree']+'\nparent '+candidate['parent']+
            '\nauthor '+identities[0]+'\ncommitter '+identities[1]+'\n\n'+MESSAGE).encode()
    require(raw == original and object_id(kind,raw) == expected_oid, 'readback-original-bytes')
    return expected_oid


def verify_ref_readback(response, *, branch_ref, metadata_head):
    """Exact branch/commit relationship only; never permission to update a ref."""
    require(type(branch_ref) is str and re.fullmatch(r'refs/heads/codex/[A-Za-z0-9_-]+',branch_ref)
        and type(metadata_head) is str and re.fullmatch('[0-9a-f]{40}',metadata_head),
        'readback-ref-expectation')
    require(type(response) is dict and response.get('ref') == branch_ref
        and type(response.get('object')) is dict
        and response['object'].get('type') == 'commit'
        and response['object'].get('sha') == metadata_head, 'readback-exact-ref')
    return metadata_head
