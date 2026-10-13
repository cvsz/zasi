import unittest

from scripts.world_room_realtime_evidence import RealtimeEvidenceError, validate_realtime_evidence


def phase():
    return {
        "upstream_configured": True,
        "realtime_session_established": True,
        "audio_sent": True,
        "audio_received": True,
        "completed_turns": 1,
        "response_latency_ms": 750,
    }


def evidence():
    return {"world_room": phase(), "rollback": phase()}


class WorldRoomRealtimeEvidenceTests(unittest.TestCase):
    def test_real_candidate_and_rollback_evidence_passes(self):
        validate_realtime_evidence(evidence())

    def test_missing_upstream_configuration_fails_closed(self):
        item = evidence()
        item["world_room"]["upstream_configured"] = False
        with self.assertRaisesRegex(RealtimeEvidenceError, "upstream_configured"):
            validate_realtime_evidence(item)

    def test_missing_audio_receive_fails_closed(self):
        item = evidence()
        item["world_room"]["audio_received"] = False
        with self.assertRaisesRegex(RealtimeEvidenceError, "audio_received"):
            validate_realtime_evidence(item)

    def test_zero_completed_turns_fails_closed(self):
        item = evidence()
        item["world_room"]["completed_turns"] = 0
        with self.assertRaisesRegex(RealtimeEvidenceError, "completed_turns"):
            validate_realtime_evidence(item)

    def test_excessive_latency_fails_closed(self):
        item = evidence()
        item["world_room"]["response_latency_ms"] = 5001
        with self.assertRaisesRegex(RealtimeEvidenceError, "response_latency_ms"):
            validate_realtime_evidence(item)

    def test_rollback_requires_same_realtime_proof(self):
        item = evidence()
        item["rollback"]["realtime_session_established"] = False
        with self.assertRaisesRegex(RealtimeEvidenceError, "rollback.realtime_session_established"):
            validate_realtime_evidence(item)

    def test_boolean_latency_is_not_numeric_evidence(self):
        item = evidence()
        item["world_room"]["response_latency_ms"] = True
        with self.assertRaisesRegex(RealtimeEvidenceError, "must be numeric"):
            validate_realtime_evidence(item)


if __name__ == "__main__":
    unittest.main()
