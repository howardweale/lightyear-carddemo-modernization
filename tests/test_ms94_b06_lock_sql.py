"""Synthetic compiled-class layout tests; not evidence from the pinned image."""
import unittest
from tests.test_ms94_b06_classfile import u2, u4, utf8
from tools.ms94_b06_classfile import inspect_class
from tools.ms94_b06_lock_sql import bind, render, TEMPLATE, METHOD


def fixture(recipe):
    pool = utf8('org/compiere/acct/Doc') + b'\x07' + u2(1) + utf8('post')
    pool += utf8('(ZZZ)Ljava/lang/String;') + utf8('Code') + utf8(recipe)
    code = u2(1) + u2(4) + u4(2) + b'\x01\xb0' + u2(0) + u2(0)
    method = u2(1) + u2(3) + u2(4) + u2(1) + u2(5) + u4(len(code)) + code
    return u4(0xCAFEBABE) + u2(0) + u2(65) + u2(7) + pool + u2(0x21) + u2(2) + u2(0) + u2(0) + u2(0) + u2(1) + method + u2(0)


class LockSQLTests(unittest.TestCase):
    def spec(self, data):
        c = inspect_class(data)
        return {'class_sha256': c['class_sha256'], 'constant_pool_sha256': c['constant_pool_sha256'],
                'method_sha256': c['methods'][METHOD], 'layout': 'concat-recipe', 'recipe_index': 6, 'template': TEMPLATE}

    def test_actual_class_bytes_are_required_not_matching_source_text(self):
        data = fixture(TEMPLATE.replace('{table}', '\x01').replace('{id}', '\x01'))
        spec = self.spec(data); binding = bind(data, spec)
        self.assertEqual(render(binding, 'c_invoice', 123), TEMPLATE.format(table='c_invoice', id=123))
        for key, value in [('class_sha256', 'a'*64), ('constant_pool_sha256', 'a'*64),
                           ('method_sha256', 'a'*64), ('recipe_index', 1), ('template', 'invented')]:
            with self.subTest(key=key), self.assertRaises(ValueError): bind(data, {**spec, key: value})
        changed = fixture(TEMPLATE.replace('{table}', '\x01').replace('{id}', '\x01').replace("Posted IN ('N','d')", "Posted='N'"))
        with self.assertRaisesRegex(ValueError, 'not-in-class-bytes'): bind(changed, self.spec(changed))

    def test_unknown_recipe_and_unbound_fragment_refused(self):
        data = fixture('UPDATE wrong WHERE id=\x01')
        with self.assertRaises(ValueError): bind(data, self.spec(data))
        with self.assertRaises(ValueError): bind(data, {**self.spec(data), 'layout': 'literal-fragments', 'fragments': [TEMPLATE]})


if __name__ == '__main__': unittest.main()
