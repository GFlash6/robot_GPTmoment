import base64
import tempfile
import unittest
from pathlib import Path

from hackathon_mvp import InspectionAgent


PNG_1X1 = base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"minimal-real-image-bytes"
).decode()


class StubAgent(InspectionAgent):
    def _assess(self, goal, image_data_url):
        return {
            "status": "normal",
            "summary": "通道未见占用",
            "confidence": 0.9,
            "findings": [],
        }


class HackathonMVPTest(unittest.TestCase):
    def test_current_position_inspection_keeps_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            result = StubAgent(directory).run(
                "检查消防通道",
                "",
                f"data:image/png;base64,{PNG_1X1}",
            )
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual([step["status"] for step in result["steps"]], ["skipped", "succeeded", "succeeded", "succeeded"])
            evidence = result["steps"][-1]["output"]["evidence"][0]
            self.assertTrue(Path(evidence).is_file())

    def test_destination_requires_real_robot_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            result = StubAgent(directory).run(
                "检查消防通道",
                "A 区",
                f"data:image/png;base64,{PNG_1X1}",
            )
            self.assertEqual(result["status"], "failed")
            self.assertIn("ROBOT_SKILL_URL", result["error"])


if __name__ == "__main__":
    unittest.main()
