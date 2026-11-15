# AI-Powered Search & Rescue Robot — Raspberry Pi 5 software

This is the Raspberry Pi-side starter package. It covers:
- Raspberry Pi Camera Module 3 live preview and video recording
- Human detection using an optional Ultralytics YOLO model (with OpenCV HOG fallback)
- Optional MediaPipe hand gesture recognition
- Optional serial input from ESP32/Arduino for ultrasonic distance, flame sensor and odometry
- Approximate 2-D robot/object mapping and event logging

## Important hardware/software split

**Raspberry Pi:** camera, AI inference, local monitoring window, recording, map, event logs, serial communication.

**ESP32/Arduino:** read ultrasonic/flame/IR sensors, motor driver and motor control, wheel encoder/odometry. The Pi package does not drive motors directly.

The serial JSON protocol below is a proposed interface. Your ESP32 firmware must send the same fields, or `core/serial_link.py` must be adapted to your actual firmware. Do not connect sensors/motors to GPIO until pinout, voltage levels and wiring are confirmed.

## 1. Install Raspberry Pi OS packages

Use Raspberry Pi OS 64-bit. In a Raspberry Pi desktop terminal:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y python3-picamera2 python3-opencv python3-numpy python3-serial python3-venv
```

Test the camera:

```bash
rpicam-hello --list-cameras
rpicam-hello -t 5000
```

## 2. Create Python environment (system camera libraries)

Picamera2 is installed by apt. On Raspberry Pi OS Bookworm, create a venv that can see system packages:

```bash
cd ~/rescue_robot_pi
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you copied this folder elsewhere, `cd` into that folder first.

## 3. Human detection model

The app works without a model using OpenCV's HOG pedestrian detector. This is a basic fallback and may miss people, especially seated/lying people or unusual camera angles.

For better detection, install Ultralytics separately if it supports your Pi OS/Python combination:

```bash
pip install ultralytics
```

Place a compatible YOLO `.pt` model at `models/yolo11n.pt` (or update `YOLO_MODEL` in `config.py`). First run may need internet to download model weights if using a model name. For offline operation, copy the weights to the Pi beforehand. YOLO inference on Pi CPU can be slow; lower resolution or use a supported accelerator/exported model if available.

## 4. Run

```bash
source .venv/bin/activate
python3 main.py
```

Controls in the OpenCV window:
- `r`: start/stop recording
- `m`: save a map snapshot
- `q` or `Esc`: quit

Recordings are saved in `recordings/`. Events are appended to `logs/events.jsonl`.

Run from the Raspberry Pi Connect **desktop** terminal if you want the OpenCV window to appear on the remote desktop. A shell-only session cannot display a local OpenCV window. The app still captures and logs, but you need a separate streaming/dashboard solution for shell-only access.

## 5. ESP32/Arduino serial message format

Set `SERIAL_PORT` and `SERIAL_BAUD` in `config.py`. The Pi expects one JSON object per line, for example:

```json
{"type":"telemetry","distance_cm":12.5,"delta_theta_deg":0,"ultrasonic_cm":12.5,"flame":0,"ir_left":0,"ir_right":0}
```

- `distance_cm`: distance the robot moved since the previous message (positive forward, negative reverse)
- `delta_theta_deg`: change in heading since the previous message (positive counter-clockwise)
- `ultrasonic_cm`: measured distance to obstacle in front
- `flame`: 1 when flame/hazard is detected, otherwise 0
- `ir_left`, `ir_right`: optional digital sensor states

If you have wheel encoders, calculate `distance_cm` and `delta_theta_deg` on the ESP32. Without encoders, the map is only a rough demonstration. Camera detections are associated with the robot's current estimated position; a person's exact coordinates require range/depth estimation and camera calibration.

## 6. Gesture recognition

Gesture recognition is optional and disabled by default. Install MediaPipe only if a compatible wheel is available for your Pi OS/Python version:

```bash
pip install mediapipe
```

Then set `ENABLE_GESTURES = True` in `config.py`. Gesture commands are display/log events only in this starter package; they do not directly control motors. Connect them to a safe, tested ESP32 command protocol only after implementing an emergency stop and validating the robot on blocks/with wheels lifted.

## 7. Files

- `main.py`: integrates camera, detection, serial telemetry, map and recording
- `core/camera.py`: Picamera2 capture
- `core/detector.py`: YOLO or HOG person detection
- `core/serial_link.py`: optional ESP32 JSON serial receiver
- `core/mapping.py`: approximate 2-D pose and map
- `core/gestures.py`: optional MediaPipe hand gesture recognizer
- `config.py`: settings

## Safety / limitations

This is a prototype for a controlled demonstration, not a certified rescue system. Do not rely on it for real emergency response. Flame sensors are not fire-safety instruments. Test motor controls separately, provide a physical emergency stop, and never let gesture recognition override an emergency stop.
