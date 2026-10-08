"""Read a closed subset of saved effective Equinox/Surefire configuration.

Unsupported escaping, indirect paths or absent effective properties refuse.
These files describe resolution; class-load observations must separately prove
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
    value = value.removeprefix('reference:')
    url = urlsplit(value)
    if url.scheme != 'file' or url.netloc or url.query or url.fragment:
        raise ValueError('resolved-file-url-required')
    path = unquote(url.path)
    if not path.startswith('/') or '..' in path.split('/') or '\\' in path:
        raise ValueError('resolved-runtime-path')
    return path


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
    entries = {}
    for key, value in booter.items():
        m = re.fullmatch(r'(?:test)?[Cc]lassPathUrl\.([0-9]+)', key)
        if m:
            index = int(m[1])
            if index in entries:
                raise ValueError('ambiguous-surefire-classpath')
            entries[index] = file_path(value)
    if not entries or sorted(entries) != list(range(len(entries))):
        raise ValueError('complete-surefire-classpath-required')
    return dict(equinox_bundles=paths,
                surefire_booter_classpath=[entries[i] for i in sorted(entries)],
                source_sha256={'config.ini': hashlib.sha256(config_ini).hexdigest(),
                               'surefire.properties': hashlib.sha256(surefire_properties).hexdigest()})
