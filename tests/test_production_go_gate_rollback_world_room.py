import unittest

from scripts.production_go_gate import GateError, validate_evidence
from test_production_go_gate import COMMIT, NOW, evidence, rulesets


class RollbackWorldRoomEvidenceTests(unittest.TestCase):
    def validate(self, item):
        return validate_evidence(item, expected_commit=COMMIT, rulesets=rulesets(), now=NOW)

    def test_valid_rollback_world_room_status_is_go(self):
        item = evidence()
        item["rollback"]["world_room_status"] = "passed"
        self.assertEqual(self.validate(item)["decision"], "GO")

    def test_failed_rollback_world_room_status_is_rejected(self):
        item = evidence()
        item["rollback"]["world_room_status"] = "failed"
        with self.assertRaisesRegex(GateError, "rollback.world_room_status"):
            self.validate(item)

    def test_missing_rollback_world_room_status_is_rejected(self):
        item = evidence()
        with self.assertRaisesRegex(GateError, "rollback.world_room_status"):
            self.validate(item)


if __name__ == "__main__":
    unittest.main()
