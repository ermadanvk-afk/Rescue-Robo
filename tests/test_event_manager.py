import unittest
import tempfile
import shutil
import json
from pathlib import Path
from core.event_manager import EventManager


class TestEventManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.log_dir = self.temp_dir / "logs"
        self.alert_dir = self.temp_dir / "alerts"
        self.event_mgr = EventManager(self.log_dir, self.alert_dir, debounce_sec=1.0)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_handle_detection_debounce(self):
        detections = [{"box": (10, 20, 100, 150), "confidence": 0.88, "label": "person", "center": (60, 95)}]
        telemetry = {"yaw": 45.0, "ultrasonic_cm": 80.0, "flame": 0}

        # First event should trigger
        evt1 = self.event_mgr.handle_detection(detections, None, telemetry)
        self.assertIsNotNone(evt1)
        self.assertEqual(evt1["event_type"], "HUMAN_DETECTED")
        self.assertEqual(evt1["confidence"], 0.88)

        # Immediate second event should be debounced
        evt2 = self.event_mgr.handle_detection(detections, None, telemetry)
        self.assertIsNone(evt2)

        # Pending cloud queue should contain exactly 1 event
        pending = self.event_mgr.get_pending_events()
        self.assertEqual(len(pending), 1)

        # Check file persistence in events.jsonl
        events_file = self.log_dir / "events.jsonl"
        self.assertTrue(events_file.exists())
        with open(events_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 1)
            saved = json.loads(lines[0])
            self.assertEqual(saved["event_id"], evt1["event_id"])

    def test_handle_flame_alert(self):
        telemetry = {"yaw": 12.0, "ultrasonic_cm": 40.0, "flame": 1}
        evt = self.event_mgr.handle_flame_alert(telemetry)
        self.assertIsNotNone(evt)
        self.assertEqual(evt["event_type"], "FLAME_ALERT")


if __name__ == "__main__":
    unittest.main()
