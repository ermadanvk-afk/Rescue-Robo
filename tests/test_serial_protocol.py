import unittest
import json
from core.serial_link import SerialTelemetry


class TestSerialProtocol(unittest.TestCase):
    def setUp(self):
        # Initialize in simulated mode
        self.link = SerialTelemetry(simulated=True)

    def tearDown(self):
        self.link.close()

    def test_simulated_telemetry_fields(self):
        data = self.link.get_latest()
        self.assertIn("yaw", data)
        self.assertIn("ultrasonic_cm", data)
        self.assertIn("flame", data)
        self.assertIn("state", data)
        self.assertEqual(data["type"], "telemetry")

    def test_send_command_serialization(self):
        cmd = {"cmd": "drive", "action": "FORWARD", "speed": 180}
        success = self.link.send_command(cmd)
        self.assertTrue(success)
        latest = self.link.get_latest()
        self.assertEqual(latest.get("_last_cmd"), cmd)


if __name__ == "__main__":
    unittest.main()
