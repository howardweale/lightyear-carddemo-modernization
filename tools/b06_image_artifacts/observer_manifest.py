"""Compile exact, prospective observer inputs from saved OSGi bundle bytes.

No execution or authority. Bundle-ClassPath order is retained; shadowed entries
are reported, not silently treated as a runtime observation. JDI must still prove
the actual defining bytes, code source and defining loader for every frame.
"""
import hashlib
import io
import re
import zipfile
from pathlib import PurePosixPath


def check(ok, reason):
    if not ok: raise ValueError(reason)


def headers(raw):
    lines=raw.decode('utf-8').replace('\r\n','\n').split('\n')
    logical=[]
    for line in lines:
        if not line: break
        if line.startswith(' '):
            check(bool(logical),'manifest-continuation');logical[-1]+=line[1:]
        else: logical.append(line)
    result={}
    for line in logical:
        key,sep,value=line.partition(': ')
        check(sep and key.lower() not in result,'manifest-duplicate-header')
        result[key.lower()]=value
    return result


def archive(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist()
        check(len(names)==len(set(names)), 'observer-assembly-duplicate-entry')
        check(all(not n.startswith('/') and '..' not in PurePosixPath(n).parts and '\\' not in n
                  for n in names),'observer-assembly-member-path')
        return {n:z.read(n) for n in names if not n.endswith('/')}


def class_entries(entries, *, java_feature, multi_release=False):
    selected={}
    for n,raw in entries.items():
        if not n.endswith('.class'): continue
        version=0; relative=n
        if n.startswith('META-INF/versions/'):
            match=re.fullmatch(r'META-INF/versions/([0-9]+)/(.+\.class)',n)
            if not multi_release or not match: continue
            version=int(match[1]);relative=match[2]
            if not 9<=version<=java_feature: continue
        if relative=='module-info.class' or relative.startswith('META-INF/'): continue
        old=selected.get(relative)
        if old is None or version>old[0]: selected[relative]=(version,n,raw)
    return [(name,n,raw) for name,(_,n,raw) in sorted(selected.items())]


def bundle_classes(raw, *, origin, folder, bundle_id, config_path, dev=(), java_feature=21):
    """Return private bytes with exact archive/loose origins and code sources.

    Nested JAR code sources use Equinox's bundle-id/generation-0 extraction path;
    folder bundles' nested directory entries retain the root's code source.
    Explicit external dev directories use their own directory code source.
    The caller binds the framework/configuration that establish these paths.
    """
    entries=archive(raw);h=headers(entries['META-INF/MANIFEST.MF'])
    bcp=h.get('bundle-classpath','.').split(',')
    check(all(x and x==x.strip() and ';' not in x and '"' not in x and
              not x.startswith('/') and '..' not in PurePosixPath(x).parts for x in bcp),
          'observer-assembly-complex-classpath')
    roots=[]
    for path in dev:
        check(folder and path.startswith(origin+'/'),'observer-assembly-external-dev')
        roots.append((path[len(origin)+1:]+'/',path.rstrip('/')+'/',True))
    roots += [(x, origin.rstrip('/')+('/' if folder else ''), False) for x in bcp]
    rows=[];shadowed=[];seen=set()
    for entry,source,isdev in roots:
        if entry.endswith('.jar'):
            check(entry in entries,'observer-assembly-nested-jar-missing')
            jar=entries[entry];nested=archive(jar)
            mh=headers(nested.get('META-INF/MANIFEST.MF',b''))
            local=class_entries(nested,java_feature=java_feature,multi_release=mh.get('multi-release')=='true')
            code_source=(origin+'/'+entry if folder else config_path.rstrip('/')+
                         '/org.eclipse.osgi/'+str(bundle_id)+'/0/.cp/'+entry)
            provider=origin+'/'+entry if folder else origin
            members_prefix=[] if folder else [entry]
            artifact=jar if folder else raw
            for name,member,body in local:
                from .native_catalogue import class_name
                if class_name(body).replace('.','/')+'.class' != name: continue
                row=dict(name=name,bytes=body,origin=provider,members=members_prefix+[member],
                         artifact=artifact,code_source=code_source)
                if name in seen: shadowed.append((name,entry,hashlib.sha256(body).hexdigest()))
                else: seen.add(name);rows.append(row)
        else:
            prefix='' if entry=='.' else entry.rstrip('/')+'/'
            local={n[len(prefix):]:b for n,b in entries.items() if n.startswith(prefix)}
            local=class_entries(local,java_feature=java_feature,multi_release=not folder and h.get('multi-release')=='true')
            for name,member,body in local:
                full=prefix+member
                # A class's internal name must match the path relative to its
                # declared classpath root. Reject accidental target/work copies.
                from .native_catalogue import class_name
                if class_name(body).replace('.','/')+'.class' != name: continue
                row=dict(name=name,bytes=body,origin=origin+'/'+full if folder else origin,
                         members=[] if folder else [full],artifact=None if folder else raw,
                         code_source=source)
                if name in seen: shadowed.append((name,entry,hashlib.sha256(body).hexdigest()))
                else: seen.add(name);rows.append(row)
    return rows,shadowed
