import unittest

from scripts.world_room_evidence_contract import (
    MAX_WORLD_ROOM_LATENCY_MS,
    WorldRoomEvidenceError,
    validate_world_room_realtime,
)


def valid_evidence():
    return {
        "status": "passed",
        "realtime_session_established": True,
        "audio_sent": True,
        "audio_response_received": True,
        "governed_turn_completed": True,
        "end_to_end_latency_ms": 850,
    }


class WorldRoomEvidenceContractTests(unittest.TestCase):
    def test_complete_realtime_audio_turn_passes(self):
        item = valid_evidence()
        self.assertIs(validate_world_room_realtime(item, "world_room"), item)

    def test_no_audio_proxy_smoke_is_rejected(self):
        item = {"status": "passed", "smoke_case": "upstream unconfigured; no audio session exchanged"}
        with self.assertRaisesRegex(WorldRoomEvidenceError, "realtime_session_established must be true"):
            validate_world_room_realtime(item, "world_room")

    def test_each_machine_verifiable_signal_is_mandatory(self):
        for field in (
            "realtime_session_established",
            "audio_sent",
            "audio_response_received",
            "governed_turn_completed",
        ):
            with self.subTest(field=field):
                item = valid_evidence()
                del item[field]
                with self.assertRaises(WorldRoomEvidenceError):
                    validate_world_room_realtime(item, "world_room")

    def test_truthy_strings_do_not_satisfy_boolean_contract(self):
        item = valid_evidence()
        item["audio_response_received"] = "true"
        with self.assertRaisesRegex(WorldRoomEvidenceError, "audio_response_received must be true"):
            validate_world_room_realtime(item, "rollback.world_room")

    def test_latency_must_be_positive_and_bounded(self):
        for latency in (0, -1, MAX_WORLD_ROOM_LATENCY_MS + 1):
            with self.subTest(latency=latency):
                item = valid_evidence()
                item["end_to_end_latency_ms"] = latency
                with self.assertRaises(WorldRoomEvidenceError):
                    validate_world_room_realtime(item, "world_room")

    def test_boolean_latency_is_rejected(self):
        item = valid_evidence()
        item["end_to_end_latency_ms"] = True
        with self.assertRaisesRegex(WorldRoomEvidenceError, "must be numeric"):
            validate_world_room_realtime(item, "world_room")


if __name__ == "__main__":
    unittest.main()
