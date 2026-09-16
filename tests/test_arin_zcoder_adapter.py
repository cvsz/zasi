import unittest

from backend.arin.tools import (
    OperationClass,
    ToolCapabilityDescriptor,
    ToolRiskClass,
)
from backend.arin.zcoder_adapter import (
    ToolAdapterError,
    ToolAdapterRequest,
    ToolAdapterResponse,
)


def read_descriptor():
    return ToolCapabilityDescriptor(
        capability_id="arin.read-evidence",
        version="1",
        operation=OperationClass.READ,
        risk_class=ToolRiskClass.LOW,
    )


class ZCoderAdapterContractTests(unittest.TestCase):
    def test_low_risk_read_request_is_tenant_and_session_bound(self):
        request = ToolAdapterRequest(
            capability_id="arin.read-evidence",
            capability_version="1",
            tenant_id="tenant-a",
            session_id="session-a",
            request_id="req-1",
            operation=OperationClass.READ,
            payload={"query": "status"},
            timeout_seconds=5.0,
        )
        request.validate_capability(read_descriptor())
        self.assertEqual(request.tenant_id, "tenant-a")
        self.assertEqual(request.session_id, "session-a")

    def test_request_rejects_missing_identity_binding(self):
        for field in ("tenant_id", "session_id", "request_id"):
            values = {
                "capability_id": "arin.read-evidence",
                "capability_version": "1",
                "tenant_id": "tenant-a",
                "session_id": "session-a",
                "request_id": "req-1",
                "operation": OperationClass.READ,
                "payload": {},
                "timeout_seconds": 5.0,
            }
            values[field] = ""
            with self.subTest(field=field), self.assertRaises(ToolAdapterError):
                ToolAdapterRequest(**values)

    def test_request_rejects_unbounded_timeout(self):
        with self.assertRaises(ToolAdapterError):
            ToolAdapterRequest(
                capability_id="arin.read-evidence",
                capability_version="1",
                tenant_id="tenant-a",
                session_id="session-a",
                request_id="req-1",
                operation=OperationClass.READ,
                payload={},
                timeout_seconds=31.0,
            )

    def test_request_rejects_unknown_operation(self):
        with self.assertRaises(ToolAdapterError):
            ToolAdapterRequest(
                capability_id="arin.read-evidence",
                capability_version="1",
                tenant_id="tenant-a",
                session_id="session-a",
                request_id="req-1",
                operation="admin",
                payload={},
            )

    def test_request_rejects_capability_identity_mismatch(self):
        request = ToolAdapterRequest(
            capability_id="arin.other",
            capability_version="1",
            tenant_id="tenant-a",
            session_id="session-a",
            request_id="req-1",
            operation=OperationClass.READ,
            payload={},
        )
        with self.assertRaises(ToolAdapterError):
            request.validate_capability(read_descriptor())

    def test_request_rejects_capability_version_mismatch(self):
        request = ToolAdapterRequest(
            capability_id="arin.read-evidence",
            capability_version="2",
            tenant_id="tenant-a",
            session_id="session-a",
            request_id="req-1",
            operation=OperationClass.READ,
            payload={},
        )
        with self.assertRaises(ToolAdapterError):
            request.validate_capability(read_descriptor())

    def test_request_rejects_operation_authority_escalation(self):
        request = ToolAdapterRequest(
            capability_id="arin.read-evidence",
            capability_version="1",
            tenant_id="tenant-a",
            session_id="session-a",
            request_id="req-1",
            operation=OperationClass.WRITE,
            payload={"path": "/workspace/file"},
        )
        with self.assertRaises(ToolAdapterError):
            request.validate_capability(read_descriptor())

    def test_response_must_match_request_identity(self):
        request = ToolAdapterRequest(
            capability_id="arin.read-evidence",
            capability_version="1",
            tenant_id="tenant-a",
            session_id="session-a",
            request_id="req-1",
            operation=OperationClass.READ,
            payload={},
        )
        response = ToolAdapterResponse(
            tenant_id="tenant-b",
            session_id="session-a",
            request_id="req-1",
            result={"ok": True},
        )
        with self.assertRaises(ToolAdapterError):
            response.validate_for(request)

    def test_secret_is_redacted_from_request_repr(self):
        request = ToolAdapterRequest(
            capability_id="arin.read-evidence",
            capability_version="1",
            tenant_id="tenant-a",
            session_id="session-a",
            request_id="req-1",
            operation=OperationClass.READ,
            payload={},
            service_token="super-secret-token",
        )
        self.assertNotIn("super-secret-token", repr(request))


if __name__ == "__main__":
    unittest.main()
