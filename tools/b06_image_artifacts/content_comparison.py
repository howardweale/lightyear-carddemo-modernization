"""Offline comparison through the same capture/producer/replay content view."""
import io,json,zipfile,hashlib
from pathlib import Path
from .bundle_content import bundle_content_view
from .application_identity import manifest,base_version

def identity(source,kind):
 view=bundle_content_view(source,kind=kind)
 if kind=='folder':raw=(Path(source)/'META-INF/MANIFEST.MF').read_bytes()
 else:
  data=source if isinstance(source,bytes) else Path(source).read_bytes()
  with zipfile.ZipFile(io.BytesIO(data)) as z:raw=z.read('META-INF/MANIFEST.MF')
 normal,headers,normalized=manifest(raw);entries=dict(view['entries']);entries['META-INF/MANIFEST.MF']=dict(kind='file',bytes=len(normal),sha256=hashlib.sha256(normal).hexdigest())
 return dict(symbolic_name=headers['bundle-symbolicname'].split(';')[0],base_version=base_version(headers['bundle-version'])[0],entries=entries,normalized_headers=normalized,exclusions=view['exclusions'])

def compare(a,b):
 left,right=a['entries'],b['entries'];common=left.keys()&right.keys()
 added=sorted(right.keys()-left.keys());removed=sorted(left.keys()-right.keys());changed=sorted(n for n in common if left[n]!=right[n])
 return dict(passed=a['symbolic_name']==b['symbolic_name'] and a['base_version']==b['base_version'] and not added+removed+changed,
  previous_entries=len(left),current_entries=len(right),added=added,removed=removed,changed=changed)
