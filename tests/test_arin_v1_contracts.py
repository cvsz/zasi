"""Regression tests for the ARIN v1 canonical contract envelope."""

import unittest

from pydantic import ValidationError

from src.control_plane.contracts.arin_v1 import ARIN_CONTRACT_VERSION, ArinContractEnvelope


class ArinV1ContractEnvelopeTests(unittest.TestCase):
    def valid_payload(self):
        return {
            "contract_version": "arin.v1",
            "tenant_id": "tenant-a",
            "session_id": "session-a",
            "request_id": "request-a",
        }

    def test_accepts_v1_tenant_session_bound_payload(self):
        envelope = ArinContractEnvelope.model_validate(self.valid_payload())
        self.assertEqual(envelope.contract_version, ARIN_CONTRACT_VERSION)
        self.assertEqual(envelope.tenant_id, "tenant-a")
        self.assertEqual(envelope.session_id, "session-a")

    def test_defaults_to_v1_when_version_omitted(self):
        payload = self.valid_payload()
        payload.pop("contract_version")
        envelope = ArinContractEnvelope.model_validate(payload)
        self.assertEqual(envelope.contract_version, "arin.v1")

    def test_rejects_unknown_contract_version(self):
        payload = self.valid_payload()
        payload["contract_version"] = "arin.v2"
        with self.assertRaises(ValidationError):
            ArinContractEnvelope.model_validate(payload)

    def test_rejects_missing_tenant(self):
        payload = self.valid_payload()
        payload.pop("tenant_id")
        with self.assertRaises(ValidationError):
            ArinContractEnvelope.model_validate(payload)

    def test_rejects_missing_session(self):
        payload = self.valid_payload()
        payload.pop("session_id")
        with self.assertRaises(ValidationError):
            ArinContractEnvelope.model_validate(payload)

    def test_rejects_unknown_fields_fail_closed(self):
        payload = self.valid_payload()
        payload["actuator_command"] = {"joint": "raw"}
        with self.assertRaises(ValidationError):
            ArinContractEnvelope.model_validate(payload)

    def test_rejects_invalid_identifier_characters(self):
        payload = self.valid_payload()
        payload["tenant_id"] = "tenant/a"
        with self.assertRaises(ValidationError):
            ArinContractEnvelope.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
