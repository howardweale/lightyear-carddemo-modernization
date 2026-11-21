"""Native SSL construction only; public roots, no network or private keys."""
import hashlib
import os
import ssl
import time
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError
from tools.ci import supervised_flex_exchange as exchange


class SupervisedFixedTLSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Read public runner roots solely to produce an inert construction fixture.
        # No root is designated as approved run trust by this test.
        roots = ssl.create_default_context().get_ca_certs(binary_form=True)
        if not roots:
            raise AssertionError('native CI public trust roots missing')
        cls.der = roots[0]
        cls.pem = ssl.DER_cert_to_PEM_cert(cls.der).encode('ascii')
        cls.digest = hashlib.sha256(cls.pem).hexdigest()

    def build(self):
        connection = exchange._fixed_provider_connection(
            self.pem,self.digest,time.monotonic()+60.0)
        self.addCleanup(connection.close)
        return connection

    def test_only_fixed_host_port_without_connection(self):
        connection = self.build()
        self.assertEqual((connection.host,connection.port),('api.openai.com',443))
        self.assertIsNone(connection.sock)
        self.assertIsNone(connection._tunnel_host)

    def test_certificate_and_hostname_verification_required(self):
        context = self.build()._context
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertGreaterEqual(context.minimum_version,ssl.TLSVersion.TLSv1_2)

    def test_only_supplied_public_root_is_loaded(self):
        context = self.build()._context
        self.assertEqual(context.get_ca_certs(binary_form=True),[self.der])
        self.assertEqual(context.cert_store_stats()['x509_ca'],1)

    def test_changed_trust_bytes_refuse_before_construction(self):
        with self.assertRaisesRegex(ContractError,'public-trust-pin'):
            exchange._fixed_provider_connection(self.pem+b'\n',self.digest,
                                                 time.monotonic()+60.0)

    def test_empty_wrong_type_or_oversized_bundle_refuses(self):
        for raw in (b'',self.pem.decode(),b'x'*2097153):
            with self.subTest(kind=type(raw).__name__), self.assertRaises(ContractError):
                exchange._fixed_provider_connection(raw,self.digest,
                                                     time.monotonic()+60.0)

    def test_invalid_certificate_or_key_container_refuses(self):
        for raw in (b'-----BEGIN CERTIFICATE-----\ninvalid\n-----END CERTIFICATE-----',
                    b'PRIVATE KEY marker only; not key material',
                    b'\xff'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ContractError,'public-trust-invalid'):
                exchange._fixed_provider_connection(raw,hashlib.sha256(raw).hexdigest(),
                                                     time.monotonic()+60.0)

    def test_expired_deadline_refuses_without_connection(self):
        with self.assertRaisesRegex(ContractError,'deadline'):
            exchange._fixed_provider_connection(self.pem,self.digest,
                                                 time.monotonic()-1.0)

    def test_proxy_and_trust_environment_cannot_redirect_or_replace_roots(self):
        with patch.dict(os.environ,{'HTTPS_PROXY':'http://127.0.0.1:1',
                'HTTP_PROXY':'http://127.0.0.1:1','ALL_PROXY':'http://127.0.0.1:1',
                'SSL_CERT_FILE':'/nonexistent/engineering-fixture',
                'SSL_CERT_DIR':'/nonexistent/engineering-fixture',
                'REQUESTS_CA_BUNDLE':'/nonexistent/engineering-fixture'}):
            connection = self.build()
            self.assertEqual(connection.host,'api.openai.com')
            self.assertIsNone(connection._tunnel_host)
            self.assertEqual(connection._context.get_ca_certs(binary_form=True),[self.der])

    def test_context_is_fresh_for_each_construction(self):
        first, second = self.build(),self.build()
        self.assertIsNot(first._context,second._context)
        first._context.check_hostname = False
        self.assertTrue(second._context.check_hostname)
