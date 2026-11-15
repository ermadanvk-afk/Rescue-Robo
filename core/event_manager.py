import json
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

try:
    import cv2
except ImportError:
    cv2 = None


class EventManager:
    """Manages detection alerts, local image archiving, debouncing, and event queuing for cloud synchronization."""

    def __init__(self, log_dir, alert_dir, debounce_sec=3.0):
        self.log_dir = Path(log_dir)
        self.alert_dir = Path(alert_dir)
        self.debounce_sec = debounce_sec

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.alert_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.log_dir / "events.jsonl"

        self.last_alert_times = {}
        self.pending_cloud_queue = []

    def handle_detection(self, detections, frame, telemetry, mapper=None):
        """Processes vision detections. If valid and debounced, logs event and queues for cloud."""
        if not detections:
            return None

        now = time.time()
        # Find best detection
        best = max(detections, key=lambda d: d.get("confidence", 0.0))
        label = best.get("label", "person")

        # Debounce per label
        last_time = self.last_alert_times.get(label, 0)
        if (now - last_time) < self.debounce_sec:
            return None

        self.last_alert_times[label] = now

        # Save snapshot
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"alert_{timestamp_str}_{label}.jpg"
        image_path = self.alert_dir / image_filename

        annotated_frame = frame.copy() if frame is not None else None
        if annotated_frame is not None and cv2 is not None:
            for det in detections:
                x, y, w, h = det["box"]
                conf = det.get("confidence", 0.0)
                lbl = det.get("label", "object")
                cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(
                    annotated_frame,
                    f"{lbl} {conf:.2f}",
                    (x, max(20, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 0),
                    2,
                )
            try:
                cv2.imwrite(str(image_path), annotated_frame)
            except Exception as exc:
                print(f"[EventManager] Could not save snapshot: {exc}")

        # Build structured event
        event = {
            "event_id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "HUMAN_DETECTED" if "person" in label.lower() else "OBJECT_DETECTED",
            "label": label,
            "confidence": best.get("confidence", 0.0),
            "bounding_boxes": [d["box"] for d in detections],
            "robot_pose": {
                "x_m": round(getattr(mapper, "x", 0.0), 2) if mapper else 0.0,
                "y_m": round(getattr(mapper, "y", 0.0), 2) if mapper else 0.0,
                "yaw_deg": round(float(telemetry.get("yaw", 0.0) or 0.0), 1)
            },
            "sensor_data": {
                "ultrasonic_cm": telemetry.get("ultrasonic_cm"),
                "flame": telemetry.get("flame", 0)
            },
            "image_filename": image_filename,
            "image_path": str(image_path)
        }

        self._record_event(event)
        if mapper:
            mapper.add_event("person")

        print(f"[EventManager] ALERT GENERATED: {event['event_type']} (ID: {event['event_id']}, Conf: {event['confidence']:.2f})")
        return event

    def handle_flame_alert(self, telemetry, mapper=None):
        """Processes flame sensor trigger."""
        now = time.time()
        last_time = self.last_alert_times.get("FLAME", 0)
        if (now - last_time) < self.debounce_sec:
            return None

        self.last_alert_times["FLAME"] = now
        event = {
            "event_id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "FLAME_ALERT",
            "label": "fire_hazard",
            "confidence": 1.0,
            "robot_pose": {
                "x_m": round(getattr(mapper, "x", 0.0), 2) if mapper else 0.0,
                "y_m": round(getattr(mapper, "y", 0.0), 2) if mapper else 0.0,
                "yaw_deg": round(float(telemetry.get("yaw", 0.0) or 0.0), 1)
            },
            "sensor_data": {
                "ultrasonic_cm": telemetry.get("ultrasonic_cm"),
                "flame": telemetry.get("flame", 1),
                "flame_analog": telemetry.get("flame_analog")
            },
            "image_filename": None,
            "image_path": None
        }

        self._record_event(event)
        if mapper:
            mapper.add_event("fire")

        print(f"[EventManager] CRITICAL ALERT: FLAME DETECTED at ({event['robot_pose']['x_m']}, {event['robot_pose']['y_m']})")
        return event

    def _record_event(self, event):
        """Appends event locally to jsonl and adds to pending cloud sync queue."""
        with open(self.events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        self.pending_cloud_queue.append(event)

    def get_pending_events(self):
        """Returns pending events for cloud upload."""
        pending = list(self.pending_cloud_queue)
        self.pending_cloud_queue.clear()
        return pending
