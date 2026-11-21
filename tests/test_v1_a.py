"""Offline TLS tests. No network resolution or provider connection in CI."""
import os
import unittest
from unittest.mock import MagicMock, patch
from tools import v1_mac_tls as probe


class ProbeTests(unittest.TestCase):
    def simulate(self, *, verified=True, error=None):
        ctx=MagicMock(check_hostname=verified,verify_mode=probe.ssl.CERT_REQUIRED)
        channel=MagicMock()
        tls=ctx.wrap_socket.return_value.__enter__.return_value
        tls.do_handshake.side_effect=error
        tls.getpeercert.return_value={"subject":"synthetic"}
        tls.version.return_value="TLSv1.3"
        def resolve(host, port, *, type):
            self.assertEqual(dict(os.environ),{})
            self.assertEqual((host, port),(probe.HOST,443))
            return [(2,type,0,"",("127.0.0.1",443))]
        with patch.dict(os.environ,{"SSL_CERT_FILE":"unused"}), patch.object(probe.ssl,"create_default_context",return_value=ctx), patch.object(probe.socket,"getaddrinfo",side_effect=resolve), patch.object(probe.socket,"socket",return_value=channel):
            result=probe.handshake()
        self.assertEqual(ctx.wrap_socket.call_args.kwargs,dict(server_hostname=probe.HOST,do_handshake_on_connect=False))
        tls.do_handshake.assert_called_once_with()
        for method in (tls.write,tls.send,tls.sendall,channel.sendall):
            method.assert_not_called()
        return result

    def test_only_tls(self):
        row=self.simulate()
        self.assertEqual((row["http_requests"],row["application_bytes"],row["credentials"]),(0,0,0))
        self.assertTrue(row["environment_empty"])

    def test_no_insecure_context(self):
        with self.assertRaises(ValueError):
            self.simulate(verified=False)

    def test_bad_certificate_no_fallback(self):
        with self.assertRaises(probe.ssl.SSLError):
            self.simulate(error=probe.ssl.SSLError("public synthetic failure"))

    def test_no_operator_id_or_socket_override(self):
        self.assertIsNone(probe.ID.fullmatch("live-123"))
        self.assertEqual((probe.HOST,probe.PORT),("api.openai.com",443))
