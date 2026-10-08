"""Read a closed subset of saved effective Equinox/Surefire configuration.

Unsupported escaping, indirect paths or absent effective properties refuse.
These files describe installation inputs, NOT resolution; class-load observations must separately prove
which artifact defined a class before it is admitted by the posting observer.
"""
import hashlib
import re
from urllib.parse import unquote, urlsplit


def properties(raw):
    text = raw.decode('utf-8')
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', '!')):
            continue
        if '\\' in line or '=' not in line:
            raise ValueError('unsupported-runtime-property-encoding')
        key, value = line.split('=', 1)
        if key.strip() in result:
            raise ValueError('duplicate-runtime-property')
        result[key.strip()] = value.strip()
    return result


def file_path(value):
    value = value.removeprefix('initial@').removeprefix('reference:')
    url = urlsplit(value)
    if url.scheme != 'file' or url.netloc or url.query or url.fragment:
        raise ValueError('resolved-file-url-required')
    path = unquote(url.path)
    if not path.startswith('/') or '..' in path.split('/') or '\\' in path:
        raise ValueError('resolved-runtime-path')
    return path.rstrip('/') or '/'


def read(config_ini, surefire_properties):
    config, booter = properties(config_ini), properties(surefire_properties)
    bundles = config.get('osgi.bundles', '').split(',')
    if not all(bundles):
        raise ValueError('effective-osgi-bundles-required')
    paths = []
    for bundle in bundles:
        # Strip only Equinox's documented start-level/start suffix.
        bundle = re.sub(r'@\d+(?::start)?$|@start$', '', bundle.strip())
        paths.append(file_path(bundle))
    groups={}
    for key,value in booter.items():
        m=re.fullmatch(r'(classPathUrl|testClassPathUrl|surefireClassPathUrl)\.([0-9]+)',key)
        if m:
            group,index=m[1],int(m[2]);groups.setdefault(group,{})[index]=file_path(value)
        elif any(word in key.lower() for word in ('classpath','bundle','framework')):
            raise ValueError('unknown-runtime-path-key:'+key)
    for key in config:
        if key.startswith(('osgi.bundles','osgi.framework')) and key not in {'osgi.bundles','osgi.bundles.defaultStartLevel','osgi.framework','osgi.framework.extensions'}:
            raise ValueError('unknown-equinox-key:'+key)
    if config.get('osgi.framework.extensions'):raise ValueError('framework-extension-closure-required')
    if not groups:raise ValueError('complete-surefire-classpath-required')
    paths_by_group=[]
    for group in ('classPathUrl','testClassPathUrl','surefireClassPathUrl'):
        entries=groups.get(group,{})
        if sorted(entries)!=list(range(len(entries))):raise ValueError('complete-surefire-classpath-required')
        paths_by_group.extend(entries[i] for i in sorted(entries))
    return dict(equinox_bundles=paths,
                surefire_booter_classpath=list(dict.fromkeys(paths_by_group)),
                source_sha256={'config.ini': hashlib.sha256(config_ini).hexdigest(),
                               'surefire.properties': hashlib.sha256(surefire_properties).hexdigest()})
