"""Closed Tycho 4.0.8 properties and observed Equinox fork reader.

The legacy resolved_runtime reader is deliberately unchanged for /2 replay.
"""
import hashlib
import posixpath
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

BASE_KEYS = frozenset(('testpluginname testclassesdirectory reportsdirectory '
    'redirectTestOutputToFile runOrder trimStackTrace skipAfterFailureCount '
    'rerunFailingTestsCount printBundles printWires classLoaderOrder testprovider').split())
ORIGINAL_PROPERTIES = '/application/org.idempiere.test/target/surefire.properties'


def properties(raw):
    """Read Java Properties.store output without dropping unknown escapes/keys."""
    logical, pending = [], ''
    for line in raw.decode('iso-8859-1').splitlines():
        if not pending and (not line.strip() or line.lstrip().startswith(('#', '!'))):
            continue
        line = pending + (line.lstrip(' \t\f') if pending else line)
        trailing = len(line) - len(line.rstrip('\\'))
        if trailing % 2:
            pending = line[:-1]
            continue
        logical.append(line); pending = ''
    if pending:
        raise ValueError('incomplete-tycho-property-continuation')
    def decode(value):
        out, i = [], 0
        escapes = {'t':'\t', 'n':'\n', 'r':'\r', 'f':'\f', '\\':'\\', ':':':', '=':'=', ' ':' ', '#':'#', '!':'!'}
        while i < len(value):
            c = value[i]; i += 1
            if c != '\\': out.append(c); continue
            if i == len(value): raise ValueError('incomplete-tycho-property-escape')
            c = value[i]; i += 1
            if c == 'u':
                digits = value[i:i+4]
                if not re.fullmatch('[a-fA-F0-9]{4}', digits): raise ValueError('invalid-tycho-unicode-escape')
                out.append(chr(int(digits,16))); i += 4
            elif c in escapes: out.append(escapes[c])
            else: raise ValueError('unsupported-tycho-property-escape')
        return ''.join(out)
    result = {}
    for line in logical:
        line = line.lstrip(' \t\f'); escaped = False; split = None
        for i,c in enumerate(line):
            if not escaped and c in '=:\t\f ': split = i; break
            if c == '\\' and not escaped: escaped = True
            else: escaped = False
        if split is None: raise ValueError('tycho-property-separator-required')
        key = decode(line[:split]); tail = line[split:].lstrip(' \t\f')
        if tail.startswith(('=', ':')): tail = tail[1:]
        value = decode(tail.lstrip(' \t\f'))
        if not key or key in result: raise ValueError('duplicate-or-empty-tycho-property')
        result[key] = value
    return result


def path(value, install=None):
    value = value.removeprefix('initial@').removeprefix('reference:')
    u = urlsplit(value)
    if u.scheme != 'file' or u.netloc or u.query or u.fragment:
        raise ValueError('tycho-file-url-required')
    raw = unquote(u.path)
    if not raw or '\\' in raw or '\x00' in raw or '*' in raw:
        raise ValueError('tycho-runtime-path')
    if raw.startswith('/'):
        if '..' in raw.split('/'): raise ValueError('tycho-absolute-parent-path')
    else:
        if not install or not install.startswith('/') or unquote(u.path) != u.path:
            raise ValueError('tycho-relative-location-without-install')
        raw = posixpath.join(install, raw)
    return posixpath.normpath(raw)


def one_properties_file(runtime):
    files = list(Path(runtime).rglob('surefire.properties'))
    if len(files) != 1 or files[0].is_symlink() or not files[0].is_file():
        raise ValueError('exactly-one-tycho-surefire-properties-required')
    return files[0]


def capture_properties(target, runtime):
    source = Path(target)/'surefire.properties'; destination = Path(runtime)/'surefire.properties'
    if not source.is_file() or source.is_symlink():
        raise ValueError('tycho-surefire-properties-not-preserved')
    with destination.open('xb') as stream: stream.write(source.read_bytes())
    one_properties_file(runtime)
    return destination


def option(command, flag):
    if not isinstance(command,list) or not all(isinstance(a,str) and a for a in command) or command.count(flag) != 1:
        raise ValueError('tycho-fork-option-required:'+flag)
    i=command.index(flag)
    if i+1==len(command): raise ValueError('tycho-fork-option-value:'+flag)
    return command[i+1]


def layout(config_raw, observation, command):
    """Offline layout checks; does not substitute for properties/inventory proof."""
    config = properties(config_raw)
    install = path(config.get('osgi.install.area',''))
    if option(command,'-install').rstrip('/') != install:
        raise ValueError('tycho-install-command-mismatch')
    if 'install_area' in observation and path(observation['install_area']) != install:
        raise ValueError('tycho-observed-install-mismatch')
    config_dir=path(observation['configuration_url'])
    if option(command,'-configuration').rstrip('/') != config_dir:
        raise ValueError('tycho-configuration-command-mismatch')
    if option(command,'-testproperties') != ORIGINAL_PROPERTIES:
        raise ValueError('tycho-testproperties-command-mismatch')
    cp=observation.get('java_class_path','').split(':')
    if len(cp)!=1 or not cp[0].startswith('/') or '..' in PurePosixPath(cp[0]).parts or '*' in cp[0]:
        raise ValueError('exactly-one-tycho-boot-classpath-required')
    launcher=cp[0]
    if not re.fullmatch(r'org\.eclipse\.equinox\.launcher[-_][^/]+\.jar',PurePosixPath(launcher).name):
        raise ValueError('tycho-equinox-launcher-required')
    if option(command,'-jar')!=launcher:
        raise ValueError('tycho-launcher-command-mismatch')
    if command[0]!=str(PurePosixPath(observation['java_home'])/'bin/java'):
        raise ValueError('tycho-java-command-mismatch')
    values=config.get('osgi.bundles','').split(',')
    if not all(values): raise ValueError('effective-osgi-bundles-required')
    inputs=[path(re.sub(r'@\d+(?::start)?$|@start$','',v.strip()),install) for v in values]
    bundles=observation['bundles'];ids=[b['id'] for b in bundles]
    if len(set(ids))!=len(ids) or ids.count(0)!=1: raise ValueError('runtime-bundle-closure')
    if any(b['state'] not in (2,4,8,16,32) or b['id']==0 and b['state']!=32 for b in bundles):
        raise ValueError('unresolved-runtime-bundle')
    observed=[path(b['location'],install) for b in bundles if b['id']!=0]
    if len(observed)!=len(set(observed)) or set(inputs)!=set(observed):
        raise ValueError('tycho-config-observed-bundles-mismatch')
    for key in config:
        if key.startswith(('osgi.bundles','osgi.framework')) and key not in {'osgi.bundles','osgi.bundles.defaultStartLevel','osgi.framework','osgi.framework.extensions'}:
            raise ValueError('unknown-equinox-key:'+key)
    if config.get('osgi.framework.extensions'): raise ValueError('framework-extension-closure-required')
    if path(config.get('osgi.framework','')) != path(observation['framework_url']):
        raise ValueError('tycho-framework-config-mismatch')
    return dict(equinox_bundles=inputs,duplicate_config_bundle_paths=sorted({p for p in inputs if inputs.count(p)>1}),
                observed_bundle_paths=observed,boot_classpath=cp,
                install_area=install,surefire_original_path=ORIGINAL_PROPERTIES)


def read(config_raw, surefire_raw, observation, command):
    if not observation.get('install_area'): raise ValueError('tycho-observed-install-required')
    parsed=layout(config_raw,observation,command)
    props=properties(surefire_raw);suite={}
    for key,value in props.items():
        m=re.fullmatch(r'testSuiteXmlFiles(0|[1-9][0-9]*)',key)
        if m: suite[int(m[1])]=value
        elif key not in BASE_KEYS and not re.fullmatch(r'__provider\.[A-Za-z0-9_.-]+',key):
            raise ValueError('unknown-tycho-property:'+key)
    if not BASE_KEYS <= props.keys(): raise ValueError('incomplete-tycho-properties')
    if sorted(suite)!=list(range(len(suite))): raise ValueError('incomplete-tycho-suite-list')
    if props['testpluginname']!='org.idempiere.test': raise ValueError('tycho-testpluginname-mismatch')
    test=[b for b in observation['bundles'] if b.get('symbolic_name')==props['testpluginname']]
    if len(test)!=1 or test[0]['state'] not in (4,8,16,32): raise ValueError('resolved-tycho-test-bundle-required')
    if not props['testprovider']: raise ValueError('tycho-testprovider-required')
    return dict(**parsed,tycho_properties=props,testprovider=props['testprovider'],
                suite_xml_files=[suite[i] for i in sorted(suite)],
                source_sha256={'config.ini':hashlib.sha256(config_raw).hexdigest(),
                               'surefire.properties':hashlib.sha256(surefire_raw).hexdigest()})
