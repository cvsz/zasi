import unittest

from backend.arin.tools import (
    OperationClass,
    ToolCapabilityDescriptor,
    ToolCapabilityError,
    ToolExecutionAuthorization,
    ToolRiskClass,
    authorize_tool_execution,
)


class ToolCapabilityDescriptorTests(unittest.TestCase):
    def test_omitted_authority_is_denied(self):
        descriptor = ToolCapabilityDescriptor(
            capability_id="arin.read-evidence",
            version="1",
            operation=OperationClass.READ,
            risk_class=ToolRiskClass.LOW,
        )
        self.assertFalse(descriptor.filesystem_allowed)
        self.assertFalse(descriptor.network_allowed)
        self.assertFalse(descriptor.subprocess_allowed)
        self.assertFalse(descriptor.filesystem_write)

    def test_network_requires_explicit_destination(self):
        with self.assertRaises(ToolCapabilityError):
            ToolCapabilityDescriptor(
                capability_id="arin.fetch",
                version="1",
                operation=OperationClass.NETWORK,
                risk_class=ToolRiskClass.LOW,
            )

    def test_execute_requires_explicit_subprocess_authority(self):
        with self.assertRaises(ToolCapabilityError):
            ToolCapabilityDescriptor(
                capability_id="arin.exec",
                version="1",
                operation=OperationClass.EXECUTE,
                risk_class=ToolRiskClass.PRIVILEGED,
                approval_required=True,
            )

    def test_privileged_descriptor_requires_approval(self):
        with self.assertRaises(ToolCapabilityError):
            ToolCapabilityDescriptor(
                capability_id="arin.write",
                version="1",
                operation=OperationClass.WRITE,
                risk_class=ToolRiskClass.PRIVILEGED,
                filesystem_roots=("/workspace",),
                filesystem_write=True,
            )

    def test_policy_denial_fails_closed(self):
        descriptor = ToolCapabilityDescriptor(
            capability_id="arin.read-evidence",
            version="1",
            operation=OperationClass.READ,
            risk_class=ToolRiskClass.LOW,
        )
        with self.assertRaises(ToolCapabilityError):
            authorize_tool_execution(descriptor, ToolExecutionAuthorization(policy_allowed=False))

    def test_policy_denial_cannot_be_overridden_by_filesystem_authority(self):
        descriptor = ToolCapabilityDescriptor(
            capability_id="arin.workspace-write",
            version="1",
            operation=OperationClass.WRITE,
            risk_class=ToolRiskClass.PRIVILEGED,
            filesystem_roots=("/workspace",),
            filesystem_write=True,
            approval_required=True,
        )
        with self.assertRaises(ToolCapabilityError):
            authorize_tool_execution(
                descriptor,
                ToolExecutionAuthorization(policy_allowed=False, approval_evidence="approval-123"),
            )

    def test_policy_denial_cannot_be_overridden_by_network_allowlist(self):
        descriptor = ToolCapabilityDescriptor(
            capability_id="arin.fetch-approved",
            version="1",
            operation=OperationClass.NETWORK,
            risk_class=ToolRiskClass.PRIVILEGED,
            network_destinations=("https://tools.internal.example",),
            approval_required=True,
        )
        with self.assertRaises(ToolCapabilityError):
            authorize_tool_execution(
                descriptor,
                ToolExecutionAuthorization(policy_allowed=False, approval_evidence="approval-123"),
            )

    def test_policy_denial_cannot_be_overridden_by_subprocess_authority(self):
        descriptor = ToolCapabilityDescriptor(
            capability_id="arin.exec-approved",
            version="1",
            operation=OperationClass.EXECUTE,
            risk_class=ToolRiskClass.CRITICAL,
            subprocess_allowed=True,
            approval_required=True,
        )
        with self.assertRaises(ToolCapabilityError):
            authorize_tool_execution(
                descriptor,
                ToolExecutionAuthorization(policy_allowed=False, approval_evidence="approval-123"),
            )

    def test_privileged_execution_requires_approval_evidence(self):
        descriptor = ToolCapabilityDescriptor(
            capability_id="arin.write",
            version="1",
            operation=OperationClass.WRITE,
            risk_class=ToolRiskClass.PRIVILEGED,
            filesystem_roots=("/workspace",),
            filesystem_write=True,
            approval_required=True,
        )
        with self.assertRaises(ToolCapabilityError):
            authorize_tool_execution(descriptor, ToolExecutionAuthorization(policy_allowed=True))

        authorize_tool_execution(
            descriptor,
            ToolExecutionAuthorization(policy_allowed=True, approval_evidence="approval-123"),
        )

    def test_unbounded_or_unscoped_descriptors_are_rejected(self):
        with self.assertRaises(ToolCapabilityError):
            ToolCapabilityDescriptor(
                capability_id="arin.read",
                version="1",
                operation=OperationClass.READ,
                risk_class=ToolRiskClass.LOW,
                tenant_bound=False,
            )
        with self.assertRaises(ToolCapabilityError):
            ToolCapabilityDescriptor(
                capability_id="arin.read",
                version="1",
                operation=OperationClass.READ,
                risk_class=ToolRiskClass.LOW,
                timeout_seconds=31,
            )


if __name__ == "__main__":
    unittest.main()
