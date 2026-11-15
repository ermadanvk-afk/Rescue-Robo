import math
import cv2
import numpy as np

class LocalMapper:
    """Simple dead-reckoning map. Accuracy depends on valid odometry from ESP32."""
    def __init__(self, size=600, pixels_per_meter=30):
        self.size = size
        self.ppm = pixels_per_meter
        self.grid = np.zeros((size, size, 3), dtype=np.uint8)
        self.x = 0.0  # metres, local frame
        self.y = 0.0
        self.theta = 0.0  # radians; 0 points along +x
        self.last_telemetry = {}
        self.events = []
        self._draw_background()

    def update(self, telemetry):
        if not telemetry:
            return
        # Integrate incremental movement/turn supplied by ESP32.
        distance = float(telemetry.get("distance_cm", 0.0)) / 100.0
        turn = math.radians(float(telemetry.get("delta_theta_deg", 0.0)))
        self.theta += turn
        self.x += distance * math.cos(self.theta)
        self.y += distance * math.sin(self.theta)
        self.last_telemetry = telemetry
        obstacle_cm = telemetry.get("ultrasonic_cm")
        if obstacle_cm is not None:
            try:
                d = float(obstacle_cm) / 100.0
                if 0 < d < 4:
                    ox = self.x + d * math.cos(self.theta)
                    oy = self.y + d * math.sin(self.theta)
                    self.add_event("obstacle", ox, oy)
            except (TypeError, ValueError):
                pass
        if int(telemetry.get("flame", 0) or 0) == 1:
            self.add_event("fire", self.x, self.y)

    def add_event(self, kind, x=None, y=None):
        x = self.x if x is None else x
        y = self.y if y is None else y
        self.events.append({"type": kind, "x_m": round(x, 2), "y_m": round(y, 2)})
        self._draw_event(kind, x, y)

    def _to_px(self, x, y):
        cx = self.size // 2
        return int(cx + x*self.ppm), int(self.size//2 - y*self.ppm)

    def _draw_background(self):
        self.grid[:] = 245
        cv2.line(self.grid, (self.size//2, 0), (self.size//2, self.size), (220,220,220), 1)
        cv2.line(self.grid, (0, self.size//2), (self.size, self.size//2), (220,220,220), 1)

    def _draw_event(self, kind, x, y):
        p = self._to_px(x, y)
        colors = {"robot": (255, 80, 0), "person": (0, 180, 0), "obstacle": (0, 140, 255), "fire": (0, 0, 255)}
        cv2.circle(self.grid, p, 6, colors.get(kind, (0,0,0)), -1)
        cv2.putText(self.grid, kind, (p[0]+7, p[1]-7), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (20,20,20), 1)

    def snapshot(self):
        self._draw_background()
        for event in self.events:
            self._draw_event(event["type"], event["x_m"], event["y_m"])
        self._draw_event("robot", self.x, self.y)
        return self.grid.copy()
