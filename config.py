from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
RECORD_DIR = BASE_DIR / "recordings"
LOG_DIR = BASE_DIR / "logs"

# Camera Module 3
CAMERA_SIZE = (640, 480)
CAMERA_FLIP = True
DISPLAY_WINDOW = True

# Detection: set to a local YOLO weights path to use YOLO; otherwise HOG fallback.
YOLO_MODEL = MODEL_DIR / "yolo11n.pt"
YOLO_CONFIDENCE = 0.35
DETECTION_EVERY_N_FRAMES = 2

# Optional ESP32/Arduino telemetry. Leave None until the firmware protocol is ready.
SERIAL_PORT = None  # e.g. "/dev/ttyUSB0" or "/dev/ttyACM0"
SERIAL_BAUD = 115200

# Approximate map size and scale
MAP_SIZE = 600
MAP_PIXELS_PER_METER = 30

# Optional MediaPipe gestures; install mediapipe and enable explicitly.
ENABLE_GESTURES = False
