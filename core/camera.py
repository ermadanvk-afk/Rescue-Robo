import time
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


class PiCamera:
    """Universal camera interface.

    Supports:
    1. Raspberry Pi Camera Module 3 via Picamera2 (primary on RPi Bookworm)
    2. USB / V4L2 webcams via OpenCV VideoCapture (fallback)
    3. Synthetic test feed (if no camera is physically connected)
    """

    def __init__(self, size=(640, 480), backend="auto"):
        self.size = tuple(size)
        self.backend = None
        self.cam_obj = None
        self._frame_index = 0

        # Try Picamera2 first
        if backend in ("auto", "picamera2"):
            try:
                from picamera2 import Picamera2
                cam = Picamera2()
                config = cam.create_video_configuration(
                    main={"size": self.size, "format": "RGB888"}
                )
                cam.configure(config)
                cam.start()
                time.sleep(1.2)  # Sensor auto-exposure warm up
                self.cam_obj = cam
                self.backend = "picamera2"
                print(f"[Camera] Initialized Picamera2 (resolution: {self.size})")
            except Exception as exc:
                if backend == "picamera2":
                    raise
                print(f"[Camera] Picamera2 not available ({exc}); trying OpenCV fallback...")

        # Try OpenCV VideoCapture fallback
        if self.backend is None and cv2 is not None:
            for device_id in [0, 1, 2]:
                try:
                    cap = cv2.VideoCapture(device_id)
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.size[0])
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.size[1])
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None:
                            self.cam_obj = cap
                            self.backend = "opencv"
                            print(f"[Camera] Initialized OpenCV VideoCapture({device_id})")
                            break
                        cap.release()
                except Exception:
                    pass

        # Synthetic fallback
        if self.backend is None:
            self.backend = "synthetic"
            print("[Camera] No physical camera found; running in SYNTHETIC test mode.")

    def read(self):
        """Read BGR frame (consistent with OpenCV standard)."""
        self._frame_index += 1

        if self.backend == "picamera2":
            try:
                rgb = self.cam_obj.capture_array()
                if cv2 is not None:
                    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                return rgb
            except Exception as exc:
                print(f"[Camera] Picamera2 read error: {exc}")
                return self._generate_synthetic_frame()

        elif self.backend == "opencv":
            ret, frame = self.cam_obj.read()
            if ret and frame is not None:
                if (frame.shape[1], frame.shape[0]) != self.size:
                    if cv2 is not None:
                        frame = cv2.resize(frame, self.size)
                return frame
            return self._generate_synthetic_frame()

        else:
            return self._generate_synthetic_frame()

    def _generate_synthetic_frame(self):
        """Generates a test frame with moving crosshair for headless testing."""
        w, h = self.size
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        # Background grid
        frame[::40, :] = (40, 40, 40)
        frame[:, ::40] = (40, 40, 40)

        # Simulated moving target
        cx = int(w / 2 + (w / 3) * np.sin(self._frame_index * 0.05))
        cy = int(h / 2 + (h / 4) * np.cos(self._frame_index * 0.05))
        if cv2 is not None:
            cv2.circle(frame, (cx, cy), 30, (0, 165, 255), 2)
            cv2.putText(
                frame,
                f"SYNTHETIC CAMERA | Frame: {self._frame_index}",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                1,
            )
            cv2.putText(
                frame,
                time.strftime("%Y-%m-%d %H:%M:%S"),
                (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (200, 200, 200),
                1,
            )
        return frame

    def close(self):
        if self.backend == "picamera2" and self.cam_obj:
            try:
                self.cam_obj.stop()
            except Exception:
                pass
        elif self.backend == "opencv" and self.cam_obj:
            try:
                self.cam_obj.release()
            except Exception:
                pass
        self.cam_obj = None
        print("[Camera] Camera released.")
