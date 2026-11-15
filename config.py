from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
RECORD_DIR = BASE_DIR / "recordings"
ALERT_DIR = RECORD_DIR / "alerts"
LOG_DIR = BASE_DIR / "logs"

# Ensure directories exist
for folder in [MODEL_DIR, RECORD_DIR, ALERT_DIR, LOG_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# =====================================================================
# CAMERA SETTINGS
# =====================================================================
CAMERA_SIZE = (640, 480)
CAMERA_FPS = 30
CAMERA_FLIP = False  # Set True if camera is mounted upside down
DISPLAY_WINDOW = bool(os.environ.get("DISPLAY_WINDOW", "True").lower() in ("true", "1"))
CAMERA_BACKEND = "auto"  # "auto", "picamera2", "opencv"

# =====================================================================
# OBJECT DETECTION (YOLO & FALLBACK)
# =====================================================================
# Path to YOLO model weights (.onnx for Raspberry Pi CPU, or .pt if using PyTorch)
YOLO_MODEL = MODEL_DIR / "yolov8n.onnx"
# Fallback model if yolov8n.onnx is missing
YOLO_MODEL_FALLBACK = MODEL_DIR / "yolo11n.pt"

YOLO_CONFIDENCE = 0.35
# Classes to detect: 0 is 'person' in COCO. Set to None to detect all classes.
TARGET_CLASSES = [0]
DETECTION_EVERY_N_FRAMES = 2  # Inference cadence to save CPU cycles on Pi

# =====================================================================
# ESP32 SERIAL PROTOCOL & PINS
# =====================================================================
# Set to specific port e.g. "/dev/ttyUSB0", "/dev/ttyACM0" or None for auto-scan
SERIAL_PORT = None
SERIAL_BAUD = 115200
SERIAL_TIMEOUT = 1.0

# =====================================================================
# AUTONOMOUS SPACE EXPLORATION & SAFETY
# =====================================================================
AUTONOMOUS_SEARCH_ENABLED = True
OBSTACLE_DISTANCE_THRESHOLD = 30.0  # cm; stop and turn if distance <= this
CRITICAL_STOP_DISTANCE = 18.0       # cm; emergency stop and reverse
SEARCH_SWEEP_ANGLE = 75             # degrees per turn during exploration
SERVO_SCAN_POSITIONS = [30, 90, 150] # Right, Center, Left sweep angles

# =====================================================================
# 2D LOCAL MAP
# =====================================================================
MAP_SIZE = 600
MAP_PIXELS_PER_METER = 30

# =====================================================================
# REMOTE CLOUD SERVER & TELEMETRY SYNC
# =====================================================================
CLOUD_ENABLED = True
# Remote server URL (e.g. "https://your-rescue-server.onrender.com" or "http://localhost:8000")
CLOUD_SERVER_URL = os.environ.get("RESCUE_CLOUD_URL", "http://localhost:8000")
CLOUD_API_KEY = os.environ.get("RESCUE_API_KEY", "rescue-robot-secret-key-2026")
CLOUD_TELEMETRY_INTERVAL_SEC = 0.5  # Send telemetry 2x per second
CLOUD_ALERT_DEBOUNCE_SEC = 3.0      # Don't flood server with alerts for same target
CLOUD_STREAM_FPS = 5                # Live preview stream to cloud dashboard

# =====================================================================
# OPTIONAL GESTURE RECOGNITION
# =====================================================================
ENABLE_GESTURES = False
