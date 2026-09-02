import socket
import unittest

from src.control_plane.egress import (
    EgressDenied,
    EgressPolicy,
    validate_destination,
    validate_redirect,
)


class EgressSecurityTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
