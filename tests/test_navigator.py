import unittest
from core.serial_link import SerialTelemetry
from core.navigator import AutonomousNavigator


class TestNavigator(unittest.TestCase):
    def setUp(self):
        self.link = SerialTelemetry(simulated=True)
        self.nav = AutonomousNavigator(self.link, obstacle_threshold=30.0, critical_threshold=18.0)

    def tearDown(self):
        self.link.close()

    def test_forward_search_when_clear(self):
        telemetry = {"yaw": 0.0, "ultrasonic_cm": 150.0, "flame": 0}
        state = self.nav.update(telemetry, detections=[])
        self.assertEqual(state, AutonomousNavigator.STATE_SEARCH_FORWARD)
        cmd = self.link.get_latest().get("_last_cmd")
        self.assertEqual(cmd.get("action"), "FORWARD")

    def test_obstacle_turn_trigger(self):
        telemetry = {"yaw": 0.0, "ultrasonic_cm": 25.0, "flame": 0}
        state = self.nav.update(telemetry, detections=[])
        self.assertEqual(state, AutonomousNavigator.STATE_TURNING)

    def test_critical_obstacle_backup(self):
        telemetry = {"yaw": 0.0, "ultrasonic_cm": 12.0, "flame": 0}
        state = self.nav.update(telemetry, detections=[])
        self.assertEqual(state, AutonomousNavigator.STATE_SCANNING)
        cmd = self.link.get_latest().get("_last_cmd")
        self.assertEqual(cmd.get("action"), "BACKWARD")

    def test_flame_emergency_stop(self):
        telemetry = {"yaw": 0.0, "ultrasonic_cm": 100.0, "flame": 1}
        state = self.nav.update(telemetry, detections=[])
        self.assertEqual(state, AutonomousNavigator.STATE_EMERGENCY_STOP)
        cmd = self.link.get_latest().get("_last_cmd")
        self.assertEqual(cmd.get("action"), "STOP")

    def test_target_engaged_centering(self):
        # Target off to the left (cx = 50 in 640px wide frame)
        detections = [{"box": (10, 20, 80, 120), "confidence": 0.92, "label": "person", "center": (50, 80)}]
        telemetry = {"yaw": 0.0, "ultrasonic_cm": 120.0, "flame": 0}
        state = self.nav.update(telemetry, detections=detections, frame_size=(640, 480))
        self.assertEqual(state, AutonomousNavigator.STATE_TARGET_ENGAGED)
        cmd = self.link.get_latest().get("_last_cmd")
        self.assertEqual(cmd.get("action"), "LEFT")


if __name__ == "__main__":
    unittest.main()
