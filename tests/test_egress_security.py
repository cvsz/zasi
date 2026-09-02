import socket
import ssl
import time
import unittest
from unittest.mock import Mock, patch

from src.control_plane.egress import (
    EgressDenied,
    EgressBroker,
    EgressRequestFailed,
    EgressPolicy,
    ResolvedDestination,
    _secure_tls_context,
    validate_destination,
    validate_redirect,
)


class EgressSecurityTests(unittest.TestCase):
    def test_tls_context_requires_tls_12_or_newer(self):
        context = _secure_tls_context()
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_loopback_ipv4_is_rejected_even_when_hostname_is_allowlisted(self):
        def resolver(host, port):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

        with self.assertRaises(EgressDenied):
            validate_destination(
                "https://public.example/hook",
                EgressPolicy(allowed_hosts=frozenset({"public.example"})),
                resolver=resolver,
            )

    def test_loopback_ipv6_is_rejected(self):
        def resolver(host, port):
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", port, 0, 0))]

        with self.assertRaises(EgressDenied):
            validate_destination(
                "https://public.example/hook",
                EgressPolicy(allowed_hosts=frozenset({"public.example"})),
                resolver=resolver,
            )

    def test_private_resolution_is_rejected_when_one_dns_answer_is_private(self):
        def resolver(host, port):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", port)),
            ]

        with self.assertRaises(EgressDenied):
            validate_destination(
                "https://public.example/hook",
                EgressPolicy(allowed_hosts=frozenset({"public.example"})),
                resolver=resolver,
            )

    def test_redirects_and_userinfo_are_rejected_before_connection(self):
        def resolver(host, port):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        policy = EgressPolicy(allowed_hosts=frozenset({"public.example"}))
        with self.assertRaises(EgressDenied):
            validate_redirect(
                "https://public.example/hook",
                "https://other.example/hook",
                policy,
                resolver=resolver,
            )
        with self.assertRaises(EgressDenied):
            validate_redirect(
                "https://public.example/hook",
                "https://public.example/hook?next=https://other.example",
                policy,
                resolver=resolver,
            )
        with self.assertRaises(EgressDenied):
            validate_destination(
                "https://user:password@public.example/hook",
                policy,
                resolver=resolver,
            )

    def test_connect_timeout_is_capped_by_total_deadline(self):
        fake_socket = Mock()
        fake_socket.getpeername.return_value = ("93.184.216.34", 443)
        destination = ResolvedDestination(
            url="http://public.example/hook",
            scheme="http",
            hostname="public.example",
            port=80,
            request_target="/hook",
            addresses=((socket.AF_INET, ("93.184.216.34", 80)),),
        )
        broker = EgressBroker(
            EgressPolicy(
                allowed_hosts=frozenset({"public.example"}),
                connect_timeout_sec=5.0,
                total_timeout_sec=0.25,
            )
        )
        with patch("src.control_plane.egress.socket.socket", return_value=fake_socket):
            broker._connect(destination, deadline=time.monotonic() + 0.25)
        self.assertLessEqual(fake_socket.settimeout.call_args.args[0], 0.25)

    def test_dns_resolution_is_bounded_by_total_timeout(self):
        def slow_resolver(host, port):
            time.sleep(0.1)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        policy = EgressPolicy(
            allowed_hosts=frozenset({"public.example"}),
            total_timeout_sec=0.01,
        )
        with patch("src.control_plane.egress._default_resolver", side_effect=slow_resolver):
            with self.assertRaises(EgressRequestFailed):
                validate_destination("https://public.example/hook", policy)

    def test_broker_does_not_connect_after_dns_deadline(self):
        def slow_resolver(host, port):
            time.sleep(0.1)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        policy = EgressPolicy(
            allowed_hosts=frozenset({"public.example"}),
            total_timeout_sec=0.01,
        )
        broker = EgressBroker(policy)
        with patch("src.control_plane.egress._default_resolver", side_effect=slow_resolver):
            with patch.object(broker, "_connect", side_effect=AssertionError("connect must not run")):
                with self.assertRaises(EgressRequestFailed):
                    broker.post_json("https://public.example/hook", {}, "idem-1")


if __name__ == "__main__":
    unittest.main()
