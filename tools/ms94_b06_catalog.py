"""Select compiled identities from the pinned application, not a cache guess."""
from pathlib import Path
from lightyear_calibration.contracts import seal
from tools.ms94_b06_admission import bound_file, check
from tools.ms94_b06_classfile import inspect_class
from tools.ms94_b06_lock_sql import bind, METHOD, TEMPLATE

FRAMEWORK = {'org.compiere.model.PO', 'org.compiere.acct.Doc',
             'org.compiere.acct.DocManager', 'org.compiere.util.DB'}
TERMINAL = {'org.junit.platform.launcher.core.ExecutionListenerAdapter',
            'org.junit.platform.engine.support.hierarchical.NodeTestTask'}


def select_runtime(folder, extraction):
    """Hash/parse every selected class. Conflicting application versions block.

    Maven caches are inventoried by the worker but do not determine runtime
    admission. The actual JDI frames must later match these compiled identities.
    """
    folder = Path(folder); result = {}; origins = {}
    for row in extraction['classes']:
        if not row['origin'].startswith('/application/'): continue
        sha = row['sha256']
        cls = inspect_class(bound_file(folder, 'class-bytes/' + sha + '.class', sha).read_bytes())
        name = cls['class']
        check(name not in result or result[name] == sha, 'conflicting-application-class-versions')
        result[name] = sha; origins.setdefault(name, []).append(row['origin'])
    check(FRAMEWORK | TERMINAL <= set(result), 'incomplete-application-framework-catalog')
    return seal({'artifact_type': 'ms94-b06-application-class-catalog/1', 'classes_sha256': result,
                 'origins': origins, 'java_binary_sha256': extraction['java_sha256'],
                 'candidate_classes_required_per_source': True, 'native_qualified': False})


def lock_spec(folder, catalog):
    sha = catalog['classes_sha256']['org.compiere.acct.Doc']
    path = bound_file(folder, 'class-bytes/' + sha + '.class', sha)
    cls = inspect_class(path.read_bytes())
    fragments = [b'UPDATE ', b" SET Processing='Y' WHERE ", b'_ID=',
                 b" AND Processed='Y' AND IsActive='Y'", b" AND (Processing='N' OR Processing IS NULL)",
                 b" AND Posted IN ('N','d')"]
    indices = []
    for raw in fragments:
        matches = [int(i) for i, value in cls['utf8_constants_hex'].items() if value == raw.hex()]
        check(len(matches) == 1, 'pinned-lock-fragment-absent-or-ambiguous')
        indices.append(matches[0])
    a,b,c,d,e,f = indices
    spec = {'class_sha256': sha, 'constant_pool_sha256': cls['constant_pool_sha256'],
            'method_sha256': cls['methods'][METHOD], 'layout': 'literal-fragments',
            'fragments': [a, '{table}', b, '{table}', c, '{id}', d, e, f], 'template': TEMPLATE}
    binding = bind(path.read_bytes(), spec)
    return spec, binding


def source_classes(folder, record):
    check(record['exit_code'] == 0 and record['tests_run'] == record['model_calls'] == record['native_pairs'] == 0,
          'candidate-catalog-compilation-not-passed')
    classes = {}
    for row in record['classes']:
        sha = row['sha256']
        item = inspect_class(bound_file(folder, sha + '.class', sha).read_bytes())
        check(item['class'] not in classes, 'duplicate-source-class')
        classes[item['class']] = sha
    check({'org.idempiere.test.JourneySupport', 'org.idempiere.test.LightyearOperationsTest'} <= set(classes),
          'candidate-support-catalog-incomplete')
    return classes
