import time
import math


class AutonomousNavigator:
    """Coordinates autonomous area coverage, obstacle avoidance, and target tracking.

    States:
    - IDLE: Waiting for start command
    - SEARCH_FORWARD: Exploring open space
    - SCANNING: Obstacle encountered; evaluating left/right paths
    - TURNING: Rotating towards clear heading using MPU6050 yaw
    - TARGET_ENGAGED: Centering on detected survivor/object
    - EMERGENCY_STOP: Halting due to flame hazard or critical proximity
    - MANUAL_OVERRIDE: Remote cloud operator has manual control
    """

    STATE_IDLE = "IDLE"
    STATE_SEARCH_FORWARD = "SEARCH_FORWARD"
    STATE_SCANNING = "SCANNING"
    STATE_TURNING = "TURNING"
    STATE_TARGET_ENGAGED = "TARGET_ENGAGED"
    STATE_EMERGENCY_STOP = "EMERGENCY_STOP"
    STATE_MANUAL_OVERRIDE = "MANUAL_OVERRIDE"

    def __init__(self, serial_link, obstacle_threshold=30.0, critical_threshold=18.0):
        self.serial = serial_link
        self.obstacle_threshold = obstacle_threshold
        self.critical_threshold = critical_threshold

        self.state = self.STATE_SEARCH_FORWARD
        self.previous_state = self.STATE_IDLE
        self.manual_override = False

        self.target_yaw = 0.0
        self.turn_direction = "LEFT"
        self.state_enter_time = time.time()
        self.last_decision_time = time.time()
        self.last_command_sent = None

    def set_mode(self, mode_str):
        """Allows toggling between AUTO and MANUAL modes from cloud dashboard."""
        if mode_str.upper() == "MANUAL":
            self.manual_override = True
            self.state = self.STATE_MANUAL_OVERRIDE
            self._send_drive_command("STOP")
            print("[Navigator] Switched to MANUAL OVERRIDE mode.")
        elif mode_str.upper() in ("AUTO", "SEARCH"):
            self.manual_override = False
            self.state = self.STATE_SEARCH_FORWARD
            print("[Navigator] Switched to AUTONOMOUS SEARCH mode.")

    def update(self, telemetry, detections, frame_size=(640, 480)):
        """Main navigation step. Called every frame or cycle.

        telemetry: dict from ESP32 with 'yaw', 'ultrasonic_cm', 'flame', etc.
        detections: list of bounding boxes from detector.
        """
        now = time.time()
        yaw = float(telemetry.get("yaw", 0.0) or 0.0)
        ultrasonic_cm = float(telemetry.get("ultrasonic_cm", 200.0) or 200.0)
        flame = int(telemetry.get("flame", 0) or 0)

        # -----------------------------------------------------------------
        # 1. Critical Safety Checks (Always active regardless of mode)
        # -----------------------------------------------------------------
        if flame == 1:
            if self.state != self.STATE_EMERGENCY_STOP:
                print("[Navigator] !!! FLAME HAZARD DETECTED - EMERGENCY HALT !!!")
                self.state = self.STATE_EMERGENCY_STOP
                self._send_drive_command("STOP")
            return self.state

        if self.state == self.STATE_EMERGENCY_STOP:
            if flame == 0:
                self.state = self.STATE_SEARCH_FORWARD
            return self.state

        # If in manual mode, ignore autonomous state machine
        if self.manual_override:
            return self.STATE_MANUAL_OVERRIDE

        # -----------------------------------------------------------------
        # 2. Target Tracking Engagement (Survivor Spotted)
        # -----------------------------------------------------------------
        if detections and len(detections) > 0:
            # Pick largest/closest detection
            best_det = max(detections, key=lambda d: d["box"][2] * d["box"][3])
            cx, cy = best_det.get("center", (frame_size[0] // 2, frame_size[1] // 2))
            frame_w = frame_size[0]

            self.state = self.STATE_TARGET_ENGAGED

            # Visual servoing: center target horizontally
            center_tolerance = frame_w * 0.15  # +/- 15% center deadband
            diff = cx - (frame_w / 2)

            if abs(diff) > center_tolerance:
                if diff < 0:
                    self._send_drive_command("LEFT", speed=150)
                else:
                    self._send_drive_command("RIGHT", speed=150)
            else:
                # Target centered! Check distance
                if ultrasonic_cm > 60.0:
                    self._send_drive_command("FORWARD", speed=160)
                else:
                    # In close proximity to survivor: halt and broadcast
                    self._send_drive_command("STOP")
            return self.state

        # If target was lost while engaged, transition back to searching
        if self.state == self.STATE_TARGET_ENGAGED and not detections:
            print("[Navigator] Target out of view; resuming autonomous search.")
            self.state = self.STATE_SEARCH_FORWARD

        # -----------------------------------------------------------------
        # 3. Autonomous Search State Machine
        # -----------------------------------------------------------------
        if self.state == self.STATE_SEARCH_FORWARD:
            # Check obstacle
            if ultrasonic_cm <= self.critical_threshold:
                print(f"[Navigator] Critical obstacle ({ultrasonic_cm:.1f} cm)! Backing up.")
                self._send_drive_command("BACKWARD", speed=170)
                self.state = self.STATE_SCANNING
                self.state_enter_time = now
            elif ultrasonic_cm <= self.obstacle_threshold:
                print(f"[Navigator] Obstacle at {ultrasonic_cm:.1f} cm. Initiating turn.")
                self._send_drive_command("STOP")
                # Alternate or choose turn
                self.turn_direction = "LEFT" if (int(now) % 2 == 0) else "RIGHT"
                self.target_yaw = (yaw + (75 if self.turn_direction == "RIGHT" else -75)) % 360
                self.state = self.STATE_TURNING
                self.state_enter_time = now
            else:
                self._send_drive_command("FORWARD", speed=180)

        elif self.state == self.STATE_SCANNING:
            # Backing up briefly before turning
            if now - self.state_enter_time > 0.4:
                self._send_drive_command("STOP")
                self.turn_direction = "LEFT" if (int(now) % 2 == 0) else "RIGHT"
                self.target_yaw = (yaw + (90 if self.turn_direction == "RIGHT" else -90)) % 360
                self.state = self.STATE_TURNING
                self.state_enter_time = now

        elif self.state == self.STATE_TURNING:
            # Turn until yaw reaches target or timeout
            yaw_diff = abs((yaw - self.target_yaw + 180) % 360 - 180)
            timeout = (now - self.state_enter_time) > 2.0  # Max 2 seconds per turn

            if yaw_diff < 15.0 or timeout:
                self._send_drive_command("STOP")
                self.state = self.STATE_SEARCH_FORWARD
                self.state_enter_time = now
            else:
                self._send_drive_command(self.turn_direction, speed=160)

        return self.state

    def manual_drive(self, action, speed=200):
        """Dispatches manual control from remote web UI."""
        self.manual_override = True
        self.state = self.STATE_MANUAL_OVERRIDE
        action = action.upper()
        if action in ("FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"):
            self._send_drive_command(action, speed=speed)
            return True
        return False

    def _send_drive_command(self, action, speed=180):
        """Throttles identical commands to avoid flooding serial bus."""
        cmd = {"cmd": "drive", "action": action, "speed": speed}
        if self.last_command_sent == cmd:
            return
        self.last_command_sent = cmd
        self.serial.send_command(cmd)
