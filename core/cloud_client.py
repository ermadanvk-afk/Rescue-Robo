import time
import threading
import json
import base64
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

try:
    import cv2
except ImportError:
    cv2 = None


class CloudClient:
    """Synchronizes robot telemetry, alert events, and camera frames to the global remote server,
    and receives remote control commands.
    """

    def __init__(self, server_url, api_key="secret", navigator=None, enabled=True):
        self.server_url = (server_url or "").rstrip("/")
        self.api_key = api_key
        self.navigator = navigator
        self.enabled = bool(enabled and requests is not None and self.server_url)

        self.running = False
        self.thread = None
        self.latest_telemetry = {}
        self.latest_frame = None
        self.lock = threading.Lock()
        self.event_queue = []
        self.is_connected = False

        if not self.enabled:
            print("[CloudClient] Cloud sync disabled or missing requests package.")
            return

        self.running = True
        self.thread = threading.Thread(target=self._sync_loop, daemon=True)
        self.thread.start()
        print(f"[CloudClient] Initialized cloud client targeting: {self.server_url}")

    def update_telemetry(self, telemetry, mapper=None):
        """Buffers latest telemetry for cloud transmission."""
        with self.lock:
            self.latest_telemetry = dict(telemetry)
            if mapper:
                self.latest_telemetry["x_m"] = round(mapper.x, 2)
                self.latest_telemetry["y_m"] = round(mapper.y, 2)

    def update_frame(self, frame):
        """Buffers latest video frame for cloud streaming."""
        with self.lock:
            self.latest_frame = frame

    def queue_event(self, event):
        """Queues an alert event for upload."""
        if not self.enabled:
            return
        with self.lock:
            self.event_queue.append(event)

    def _sync_loop(self):
        """Worker loop sending telemetry and polling for cloud commands."""
        headers = {
            "X-API-Key": self.api_key
        }

        last_telemetry_time = 0
        last_stream_time = 0

        while self.running:
            now = time.time()

            # 1. Upload Pending Alert Events (High Priority)
            pending_events = []
            with self.lock:
                if self.event_queue:
                    pending_events = list(self.event_queue)
                    self.event_queue.clear()

            for event in pending_events:
                self._upload_event(event, headers)

            # 2. Push Periodic Telemetry & Check for Commands (e.g. at 2Hz)
            if now - last_telemetry_time >= 0.5:
                last_telemetry_time = now
                with self.lock:
                    telem = dict(self.latest_telemetry)

                if telem:
                    self._push_telemetry(telem, headers)

            # 3. Push Live Video Frame (e.g. at 3-5 FPS to save bandwidth)
            if now - last_stream_time >= 0.25:
                last_stream_time = now
                with self.lock:
                    frame = self.latest_frame

                if frame is not None and cv2 is not None:
                    self._push_preview_frame(frame, headers)

            time.sleep(0.05)

    def _push_telemetry(self, telemetry, headers):
        """Pushes telemetry and checks response for any remote drive commands."""
        url = f"{self.server_url}/api/telemetry"
        payload = {
            "timestamp": time.time(),
            "telemetry": telemetry
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=1.5)
            if resp.status_code == 200:
                self.is_connected = True
                data = resp.json()
                # Check if server queued a command for the robot
                cmd = data.get("pending_command")
                if cmd and self.navigator:
                    self._handle_server_command(cmd)
        except Exception:
            self.is_connected = False

    def _upload_event(self, event, headers):
        """Uploads an alert event with snapshot image."""
        url = f"{self.server_url}/api/events"
        image_path = event.get("image_path")

        files = None
        data = {
            "event_json": json.dumps(event)
        }

        if image_path and Path(image_path).exists():
            try:
                files = {"file": open(image_path, "rb")}
            except Exception as exc:
                print(f"[CloudClient] Could not read image for event {event.get('event_id')}: {exc}")

        try:
            resp = requests.post(url, data=data, files=files, headers=headers, timeout=5.0)
            if resp.status_code in (200, 201):
                print(f"[CloudClient] Event {event.get('event_id')} successfully synced to cloud!")
            else:
                # Re-queue on server failure
                with self.lock:
                    self.event_queue.append(event)
        except Exception as exc:
            print(f"[CloudClient] Event upload failed ({exc}); will retry later.")
            with self.lock:
                self.event_queue.append(event)
        finally:
            if files and "file" in files:
                try:
                    files["file"].close()
                except Exception:
                    pass

    def _push_preview_frame(self, frame, headers):
        """Compresses JPEG frame and pushes to server preview stream."""
        url = f"{self.server_url}/api/preview"
        try:
            # Resize frame to 320x240 for efficient bandwidth transmission
            small = cv2.resize(frame, (320, 240))
            _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 55])
            b64_frame = base64.b64encode(buf).decode("utf-8")
            requests.post(url, json={"frame": b64_frame}, headers=headers, timeout=0.8)
        except Exception:
            pass

    def _handle_server_command(self, cmd):
        """Executes remote command received from dashboard."""
        action = cmd.get("action", "").upper()
        mode = cmd.get("mode", "").upper()

        print(f"[CloudClient] Received remote command from cloud: {cmd}")

        if mode in ("MANUAL", "AUTO", "SEARCH"):
            self.navigator.set_mode(mode)

        if action in ("FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"):
            speed = int(cmd.get("speed", 180))
            self.navigator.manual_drive(action, speed=speed)

    def close(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        print("[CloudClient] Cloud client stopped.")
