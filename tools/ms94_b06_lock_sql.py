"""Lock predicate identity from the exact pinned Doc.class, not source prose."""
from lightyear_calibration.contracts import seal, verify
from tools.ms94_b06_admission import check
from tools.ms94_b06_classfile import inspect_class

TEMPLATE = ("UPDATE {table} SET Processing='Y' WHERE {table}_ID={id}"
            " AND Processed='Y' AND IsActive='Y' AND (Processing='N' OR Processing IS NULL)"
            " AND Posted IN ('N','d')")
METHOD = 'post(ZZZ)Ljava/lang/String;'


def bind(data, spec):
    cls = inspect_class(data)
    check(cls['class'] == 'org.compiere.acct.Doc' and cls['class_sha256'] == spec['class_sha256'] and
          cls['constant_pool_sha256'] == spec['constant_pool_sha256'] and
          cls['methods'].get(METHOD) == spec['method_sha256'] != 'unavailable', 'lock-sql-class-binding')
    def constant(index):
        check(type(index) is int and str(index) in cls['utf8_constants_hex'], 'lock-sql-constant-missing')
        return bytes.fromhex(cls['utf8_constants_hex'][str(index)]).decode('ascii')
    if spec['layout'] == 'concat-recipe':
        recipe = constant(spec['recipe_index'])
        check(recipe.count('\x01') == 3 and '\x02' not in recipe, 'lock-sql-recipe-shape')
        parts = recipe.split('\x01')
        text = parts[0] + '{table}' + parts[1] + '{table}' + parts[2] + '{id}' + parts[3]
    else:
        check(spec['layout'] == 'literal-fragments', 'lock-sql-layout-unknown')
        # Full literal constants only, no character picking or unbound text.
        text = ''.join(constant(x) if type(x) is int else x for x in spec['fragments']
                       if type(x) is int or x in ('{table}', '{id}'))
        check(all(type(x) is int or x in ('{table}', '{id}') for x in spec['fragments']), 'lock-sql-fragment-invalid')
    check(text == TEMPLATE and spec['template'] == TEMPLATE, 'lock-sql-template-not-in-class-bytes')
    return seal({'artifact_type': 'ms94-b06-lock-sql-binding/1', 'class_sha256': cls['class_sha256'],
                 'constant_pool_sha256': cls['constant_pool_sha256'], 'method_sha256': cls['methods'][METHOD],
                 'template': text})


def render(binding, table, record_id):
    verify(binding)
    check(binding['artifact_type'] == 'ms94-b06-lock-sql-binding/1' and binding['template'] == TEMPLATE,
          'lock-sql-projection-binding')
    return binding['template'].format(table=table, id=record_id)
