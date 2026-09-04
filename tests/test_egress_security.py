import socket
import ssl
import threading
import time
import unittest
from unittest.mock import Mock, patch

from src.control_plane.connectors.egress import (
    EgressDenied,
    EgressBroker,
    EgressRequestFailed,
    EgressPolicy,
    ResolvedDestination,
    _secure_tls_context,
    validate_destination,
    validate_redirect,
)
from src.control_plane.connectors import egress as egress_module


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
        with patch("src.control_plane.connectors.egress.socket.socket", return_value=fake_socket):
            broker._connect(destination, deadline=time.monotonic() + 0.25)
        self.assertLessEqual(fake_socket.settimeout.call_args.args[0], 0.25)

    def test_dns_resolution_is_bounded_by_total_timeout(self):
        resolver_done = threading.Event()

        def slow_resolver(host, port):
            try:
                time.sleep(0.1)
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
            finally:
                resolver_done.set()

        policy = EgressPolicy(
            allowed_hosts=frozenset({"public.example"}),
            total_timeout_sec=0.01,
        )
        try:
            with patch("src.control_plane.connectors.egress._default_resolver", side_effect=slow_resolver):
                with self.assertRaises(EgressRequestFailed):
                    validate_destination("https://public.example/hook", policy)
        finally:
            self.assertTrue(resolver_done.wait(1))

    def test_broker_does_not_connect_after_dns_deadline(self):
        resolver_done = threading.Event()

        def slow_resolver(host, port):
            try:
                time.sleep(0.1)
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
            finally:
                resolver_done.set()

        policy = EgressPolicy(
            allowed_hosts=frozenset({"public.example"}),
            total_timeout_sec=0.01,
        )
        broker = EgressBroker(policy)
        try:
            with patch("src.control_plane.connectors.egress._default_resolver", side_effect=slow_resolver):
                with patch.object(broker, "_connect", side_effect=AssertionError("connect must not run")):
                    with self.assertRaises(EgressRequestFailed):
                        broker.post_json("https://public.example/hook", {}, "idem-1")
        finally:
            self.assertTrue(resolver_done.wait(1))

    def test_broker_passes_absolute_deadline_to_dns_validation(self):
        policy = EgressPolicy(
            allowed_hosts=frozenset({"public.example"}),
            total_timeout_sec=0.08,
        )
        broker = EgressBroker(policy)
        destination = ResolvedDestination(
            url="https://public.example/hook",
            scheme="https",
            hostname="public.example",
            port=443,
            request_target="/hook",
            addresses=((socket.AF_INET, ("93.184.216.34", 443)),),
        )
        with patch.object(egress_module, "validate_destination", return_value=destination) as validate:
            with patch.object(
                broker,
                "_connect",
                side_effect=EgressRequestFailed("stop after validation"),
            ):
                with self.assertRaises(EgressRequestFailed):
                    broker.post_json("https://public.example/hook", {}, "idem-1")

        self.assertIn("deadline", validate.call_args.kwargs)
        self.assertNotIn("timeout_sec", validate.call_args.kwargs)
        self.assertIsInstance(validate.call_args.kwargs["deadline"], float)

    def test_resolver_slot_contention_shares_one_absolute_deadline(self):
        class FakeClock:
            now = 100.0

            @classmethod
            def monotonic(cls):
                return cls.now

        acquire_timeouts = []
        result_timeouts = []

        class FakeSlots:
            def acquire(self, timeout):
                acquire_timeouts.append(timeout)
                FakeClock.now += 0.04
                return True

            def release(self):
                return None

        class FakeQueue:
            def __init__(self, maxsize):
                self.value = None

            def put(self, value):
                self.value = value

            def get(self, timeout):
                result_timeouts.append(timeout)
                return self.value

        class ImmediateThread:
            def __init__(self, target, name, daemon):
                self.target = target

            def start(self):
                self.target()

        def resolver(host, port):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

        policy = EgressPolicy(
            allowed_hosts=frozenset({"public.example"}),
            total_timeout_sec=0.08,
        )
        with patch.object(egress_module, "_resolver_slots", FakeSlots()):
            with patch.object(egress_module.time, "monotonic", FakeClock.monotonic):
                with patch.object(egress_module.queue, "Queue", return_value=FakeQueue(1)):
                    with patch.object(egress_module.threading, "Thread", ImmediateThread):
                        destination = validate_destination(
                            "https://public.example/hook",
                            policy,
                            resolver=resolver,
                        )

        self.assertEqual(destination.addresses[0][1][0], "93.184.216.34")
        self.assertEqual(len(acquire_timeouts), 1)
        self.assertAlmostEqual(acquire_timeouts[0], 0.08)
        self.assertEqual(len(result_timeouts), 1)
        self.assertAlmostEqual(result_timeouts[0], 0.04)


if __name__ == "__main__":
    unittest.main()
