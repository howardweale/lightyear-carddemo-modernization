import json
import tomllib
import unittest
from tools.ms94_b06_http_transport_draft import draft, TOKEN_ENV
from tools.ms94_b06_pinned_transport import PATH, SHA
from tools.ms94_b06_builder_boundary import ARGUMENTS


class HttpDraftTests(unittest.TestCase):
    def test_http_configuration_has_only_closed_tools_and_env_token(self):
        record = draft(49152, r'C:\ProgramData\Lightyear\builder-empty')
        argv = record['argv']
        config = tomllib.loads(next(x for x in argv if x.startswith('mcp_servers=')))
        servers = config['mcp_servers']
        self.assertEqual(set(servers), {'qualified_journey_public'})
        server = servers['qualified_journey_public']
        self.assertEqual(server['url'], 'http://127.0.0.1:49152/mcp')
        self.assertEqual(server['bearer_token_env_var'], TOKEN_ENV)
        self.assertEqual(set(server['enabled_tools']), set(ARGUMENTS))
        self.assertTrue(server['required'])
        self.assertFalse({'command', 'args', 'env', 'http_headers', 'bearer_token'} & set(server))
        self.assertEqual((record['executable'], record['executable_sha256']), (PATH, SHA))
        self.assertFalse(record['model_calls_authorized'])
        self.assertTrue(record['requires_new_transport_proof'])
        self.assertEqual(argv[-1], '-')
        self.assertIn('--ignore-user-config', argv)

    def test_arbitrary_endpoints_and_remote_workspaces_are_rejected(self):
        for port in (True, 0, 80, 65536, '49152', 'https://example.org/mcp'):
            with self.subTest(port=port), self.assertRaises(ValueError):
                draft(port, r'C:\empty')
        for path in ('relative', r'\\host\share', '//host/share', 'C:\bad\npath\n', None):
            with self.subTest(path=path), self.assertRaises(ValueError):
                draft(49152, path)

    def test_draft_is_deterministic_and_does_not_read_environment_token(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {TOKEN_ENV: 'test-secret-never-serialize'}):
            record = draft(49152, r'C:\empty')
        self.assertNotIn('test-secret-never-serialize', json.dumps(record))
        self.assertEqual(record, draft(49152, r'C:\empty'))


if __name__ == '__main__':
    unittest.main()
