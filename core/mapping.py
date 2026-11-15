import math
import time
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


class LocalMapper:
    """2D spatial grid map tracking robot trajectory, obstacles, detected survivors, and fire hazards."""

    def __init__(self, size=600, pixels_per_meter=30):
        self.size = size
        self.ppm = pixels_per_meter
        self.grid = np.zeros((size, size, 3), dtype=np.uint8)
        self.x = 0.0  # metres in local coordinate frame
        self.y = 0.0
        self.theta = 0.0  # radians (0 pointing along +X)

        self.last_update_time = time.time()
        self.last_telemetry = {}
        self.events = []
        self.trajectory = []
        self._draw_background()

    def update(self, telemetry):
        if not telemetry:
            return

        now = time.time()
        dt = max(0.01, min(0.5, now - self.last_update_time))
        self.last_update_time = now

        # 1. Update Heading (prefer absolute MPU6050 yaw if available)
        if "yaw" in telemetry:
            self.theta = math.radians(float(telemetry["yaw"]))
        elif "delta_theta_deg" in telemetry:
            self.theta += math.radians(float(telemetry["delta_theta_deg"]))

        # 2. Update Position
        # If encoder distance is available:
        if "distance_cm" in telemetry and float(telemetry["distance_cm"]) != 0:
            dist_m = float(telemetry["distance_cm"]) / 100.0
        else:
            # Estimate movement from motor state & speed
            state = str(telemetry.get("state", "STOP")).upper()
            speed = float(telemetry.get("speed", 180)) / 255.0
            nominal_velocity = 0.35 * speed  # approx 0.35 m/s at full throttle

            if "FORWARD" in state:
                dist_m = nominal_velocity * dt
            elif "BACKWARD" in state:
                dist_m = -nominal_velocity * dt
            else:
                dist_m = 0.0

        self.x += dist_m * math.cos(self.theta)
        self.y += dist_m * math.sin(self.theta)

        # Record trajectory point periodically
        if not self.trajectory or math.hypot(self.x - self.trajectory[-1][0], self.y - self.trajectory[-1][1]) > 0.08:
            self.trajectory.append((self.x, self.y))
            if len(self.trajectory) > 500:
                self.trajectory.pop(0)

        # 3. Add Obstacle from Ultrasonic Sensor
        obstacle_cm = telemetry.get("ultrasonic_cm")
        if obstacle_cm is not None:
            try:
                d = float(obstacle_cm) / 100.0
                if 0.05 < d < 3.0:
                    ox = self.x + d * math.cos(self.theta)
                    oy = self.y + d * math.sin(self.theta)
                    # Don't duplicate obstacles too close to existing ones
                    if not any(e["type"] == "obstacle" and math.hypot(ox - e["x_m"], oy - e["y_m"]) < 0.2 for e in self.events):
                        self.add_event("obstacle", ox, oy)
            except (TypeError, ValueError):
                pass

        # 4. Check Flame Hazard
        if int(telemetry.get("flame", 0) or 0) == 1:
            if not any(e["type"] == "fire" and math.hypot(self.x - e["x_m"], self.y - e["y_m"]) < 0.3 for e in self.events):
                self.add_event("fire", self.x, self.y)

        self.last_telemetry = telemetry

    def add_event(self, kind, x=None, y=None):
        x = self.x if x is None else x
        y = self.y if y is None else y
        self.events.append({
            "type": kind,
            "x_m": round(x, 2),
            "y_m": round(y, 2),
            "timestamp": time.time()
        })
        # Keep recent events bounded
        if len(self.events) > 100:
            self.events.pop(0)

    def _to_px(self, x, y):
        cx = self.size // 2
        cy = self.size // 2
        px = int(cx + x * self.ppm)
        py = int(cy - y * self.ppm)
        return px, py

    def _draw_background(self):
        self.grid[:] = (245, 245, 245)
        if cv2 is None:
            return
        cx = self.size // 2
        cy = self.size // 2
        # Grid lines every 1 meter
        meter_px = int(self.ppm)
        for offset in range(-cx, cx, meter_px):
            cv2.line(self.grid, (cx + offset, 0), (cx + offset, self.size), (230, 230, 230), 1)
            cv2.line(self.grid, (0, cy + offset), (self.size, cy + offset), (230, 230, 230), 1)
        # Coordinate axes
        cv2.line(self.grid, (cx, 0), (cx, self.size), (200, 200, 200), 2)
        cv2.line(self.grid, (0, cy), (self.size, cy), (200, 200, 200), 2)

    def snapshot(self):
        self._draw_background()
        if cv2 is None:
            return self.grid.copy()

        # Draw Trajectory
        if len(self.trajectory) > 1:
            points = [self._to_px(tx, ty) for tx, ty in self.trajectory]
            for i in range(len(points) - 1):
                cv2.line(self.grid, points[i], points[i + 1], (180, 180, 180), 2)

        # Draw Events
        colors = {
            "robot": (255, 80, 0),
            "person": (0, 180, 0),
            "obstacle": (0, 140, 255),
            "fire": (0, 0, 255)
        }
        for event in self.events:
            p = self._to_px(event["x_m"], event["y_m"])
            col = colors.get(event["type"], (50, 50, 50))
            cv2.circle(self.grid, p, 6, col, -1)
            cv2.putText(
                self.grid,
                event["type"].upper(),
                (p[0] + 8, p[1] - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (40, 40, 40),
                1,
            )

        # Draw Robot Pose and Direction Pointer
        rx, ry = self._to_px(self.x, self.y)
        cv2.circle(self.grid, (rx, ry), 10, (255, 100, 0), -1)
        # Heading arrow
        arrow_len = 22
        hx = int(rx + arrow_len * math.cos(self.theta))
        hy = int(ry - arrow_len * math.sin(self.theta))
        cv2.arrowedLine(self.grid, (rx, ry), (hx, hy), (0, 0, 220), 2, tipLength=0.35)

        # Legend / Pose Info
        cv2.putText(
            self.grid,
            f"Robot: ({self.x:.2f}m, {self.y:.2f}m) | Heading: {math.degrees(self.theta)%360:.1f} deg",
            (15, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (20, 20, 20),
            1,
        )
        return self.grid.copy()
