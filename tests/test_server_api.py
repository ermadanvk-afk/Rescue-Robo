import unittest
import json
from fastapi.testclient import TestClient
from server.app import app


class TestServerAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_dashboard(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("AI Search & Rescue Robot", response.text)

    def test_telemetry_flow(self):
        payload = {
            "telemetry": {
                "yaw": 45.2,
                "ultrasonic_cm": 60.5,
                "flame": 0,
                "x_m": 1.2,
                "y_m": 0.8,
                "state": "FORWARD"
            }
        }
        res_post = self.client.post("/api/telemetry", json=payload)
        self.assertEqual(res_post.status_code, 200)

        res_get = self.client.get("/api/telemetry")
        self.assertEqual(res_get.status_code, 200)
        data = res_get.json()
        self.assertTrue(data["online"])
        self.assertEqual(data["telemetry"]["yaw"], 45.2)

    def test_command_queue(self):
        cmd = {"cmd": "drive", "action": "FORWARD", "speed": 200}
        res_cmd = self.client.post("/api/command", json=cmd)
        self.assertEqual(res_cmd.status_code, 200)

        # Telemetry post should pop the pending command
        res_telem = self.client.post("/api/telemetry", json={"telemetry": {}})
        self.assertEqual(res_telem.status_code, 200)
        self.assertEqual(res_telem.json().get("pending_command"), cmd)

    def test_event_ingestion(self):
        event_dict = {
            "event_id": "test_evt_1",
            "event_type": "HUMAN_DETECTED",
            "label": "person",
            "confidence": 0.95,
            "robot_pose": {"x_m": 2.0, "y_m": 1.5, "yaw_deg": 90.0}
        }
        res_event = self.client.post(
            "/api/events",
            data={"event_json": json.dumps(event_dict)}
        )
        self.assertEqual(res_event.status_code, 200)

        res_list = self.client.get("/api/events")
        self.assertEqual(res_list.status_code, 200)
        events = res_list.json().get("events", [])
        self.assertTrue(any(e.get("event_id") == "test_evt_1" for e in events))


if __name__ == "__main__":
    unittest.main()
