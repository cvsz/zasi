import asyncio
import unittest

from backend.arin.tools import (
    OperationClass,
    ToolCapabilityDescriptor,
    ToolRiskClass,
)
from backend.arin.zcoder_adapter import (
    LocalToolTransport,
    ToolAdapterError,
    ToolAdapterRequest,
    ToolAdapterResponse,
    ToolTransportError,
)


def read_descriptor():
    return ToolCapabilityDescriptor(
        capability_id="arin.read-evidence",
        version="1",
        operation=OperationClass.READ,
        risk_class=ToolRiskClass.LOW,
    )


def read_request(**overrides):
    values = {
        "capability_id": "arin.read-evidence",
        "capability_version": "1",
        "tenant_id": "tenant-a",
        "session_id": "session-a",
        "request_id": "req-1",
        "operation": OperationClass.READ,
        "payload": {"query": "status"},
        "timeout_seconds": 0.05,
    }
    values.update(overrides)
    return ToolAdapterRequest(**values)


class ZCoderAdapterContractTests(unittest.TestCase):
    def test_low_risk_read_request_is_tenant_and_session_bound(self):
        request = read_request(timeout_seconds=5.0)
        request.validate_capability(read_descriptor())
        self.assertEqual(request.tenant_id, "tenant-a")
        self.assertEqual(request.session_id, "session-a")

    def test_request_rejects_missing_identity_binding(self):
        for field in ("tenant_id", "session_id", "request_id"):
            with self.subTest(field=field), self.assertRaises(ToolAdapterError):
                read_request(**{field: ""})

    def test_request_rejects_unbounded_timeout(self):
        with self.assertRaises(ToolAdapterError):
            read_request(timeout_seconds=31.0)

    def test_request_rejects_unknown_operation(self):
        with self.assertRaises(ToolAdapterError):
            read_request(operation="admin")

    def test_request_rejects_capability_identity_mismatch(self):
        with self.assertRaises(ToolAdapterError):
            read_request(capability_id="arin.other").validate_capability(read_descriptor())

    def test_request_rejects_capability_version_mismatch(self):
        with self.assertRaises(ToolAdapterError):
            read_request(capability_version="2").validate_capability(read_descriptor())

    def test_request_rejects_operation_authority_escalation(self):
        with self.assertRaises(ToolAdapterError):
            read_request(operation=OperationClass.WRITE).validate_capability(read_descriptor())

    def test_response_must_match_request_identity(self):
        request = read_request()
        response = ToolAdapterResponse(
            tenant_id="tenant-b",
            session_id="session-a",
            request_id="req-1",
            result={"ok": True},
        )
        with self.assertRaises(ToolAdapterError):
            response.validate_for(request)

    def test_secret_is_redacted_from_request_repr(self):
        request = read_request(service_token="super-secret-token")
        self.assertNotIn("super-secret-token", repr(request))


class LocalToolTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_transport_returns_identity_bound_response(self):
        async def handler(request):
            return {
                "tenant_id": request.tenant_id,
                "session_id": request.session_id,
                "request_id": request.request_id,
                "result": {"status": "ok"},
            }

        response = await LocalToolTransport(handler).send(read_request(), read_descriptor())
        self.assertEqual(response.result, {"status": "ok"})

    async def test_local_transport_times_out_fail_closed(self):
        async def handler(_request):
            await asyncio.sleep(0.2)
            return {}

        with self.assertRaises(ToolTransportError):
            await LocalToolTransport(handler).send(read_request(), read_descriptor())

    async def test_local_transport_normalizes_handler_failure(self):
        async def handler(_request):
            raise OSError("secret internal path")

        with self.assertRaisesRegex(ToolTransportError, "transport unavailable") as raised:
            await LocalToolTransport(handler).send(read_request(), read_descriptor())
        self.assertNotIn("secret internal path", str(raised.exception))

    async def test_local_transport_rejects_malformed_response(self):
        async def handler(_request):
            return {"result": {"status": "ok"}}

        with self.assertRaises(ToolTransportError):
            await LocalToolTransport(handler).send(read_request(), read_descriptor())

    async def test_local_transport_rejects_cross_tenant_response(self):
        async def handler(request):
            return {
                "tenant_id": "tenant-b",
                "session_id": request.session_id,
                "request_id": request.request_id,
                "result": {},
            }

        with self.assertRaises(ToolTransportError):
            await LocalToolTransport(handler).send(read_request(), read_descriptor())

    async def test_local_transport_rejects_oversized_result(self):
        async def handler(request):
            return {
                "tenant_id": request.tenant_id,
                "session_id": request.session_id,
                "request_id": request.request_id,
                "result": {"data": "x" * 5000},
            }

        with self.assertRaises(ToolTransportError):
            await LocalToolTransport(handler, max_result_bytes=1024).send(
                read_request(), read_descriptor()
            )

    async def test_local_transport_does_not_forward_service_token_to_handler(self):
        seen = []

        async def handler(request):
            seen.append(request)
            return {
                "tenant_id": request.tenant_id,
                "session_id": request.session_id,
                "request_id": request.request_id,
                "result": {},
            }

        await LocalToolTransport(handler).send(
            read_request(service_token="super-secret-token"), read_descriptor()
        )
        self.assertIsNone(seen[0].service_token)


if __name__ == "__main__":
    unittest.main()
