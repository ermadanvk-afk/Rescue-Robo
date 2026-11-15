# AI Search & Rescue Robot — Comprehensive Debug & Troubleshooting Guide

This guide is designed to help you quickly diagnose and resolve every potential hardware, serial, vision, and cloud networking issue on both the **ESP32** and the **Raspberry Pi 5**.

---

## 1. ESP32 & Sensor Hardware Debugging

### Pinout Reference Table
| Component | Function / Pin | ESP32 GPIO | Notes |
| :--- | :--- | :--- | :--- |
| **L298N Motor Driver** | ENA (Left Speed PWM) | **GPIO 32** | Connect to PWM pin |
| | IN1 (Left Forward) | **GPIO 18** | Standard digital output |
| | IN2 (Left Backward) | **GPIO 19** | Standard digital output |
| | IN3 (Right Forward) | **GPIO 25** | Standard digital output |
| | IN4 (Right Backward) | **GPIO 26** | Standard digital output |
| | ENB (Right Speed PWM) | **GPIO 33** | Connect to PWM pin |
| **HC-SR04 Ultrasonic** | TRIG | **GPIO 5** | 10μs trigger pulse |
| | ECHO | **GPIO 27** | Recommended: voltage divider (1kΩ/2kΩ) |
| **SG90 Servo Motor** | Signal (PWM) | **GPIO 13** | 50Hz PWM signal |
| **MPU6050 (IMU)** | SDA | **GPIO 21** | I2C Data (default hardware I2C) |
| | SCL | **GPIO 22** | I2C Clock (default hardware I2C) |
| **HW-491 Flame Sensor** | AO (Analog Output) | **GPIO 34** | ADC input (0-4095) |
| | DO (Digital Output) | **GPIO 35** | Input only (Active HIGH) |

---

### Common ESP32 Hardware Issues & Fixes

#### Issue 1.1: Common Ground Missing (Motors stutter or ESP32 resets)
* **Symptom:** As soon as motors turn on, the ESP32 resets, serial disconnects, or motors twitch erratically.
* **Cause:** The battery ground is not connected to the ESP32 ground.
* **Fix:** **All grounds MUST be tied together.** Connect:
  - Battery Ground (`-`)
  - L298N `GND`
  - ESP32 `GND`

#### Issue 1.2: ESP32 Brownout / Power Starvation
* **Symptom:** Arduino Serial Monitor outputs `Brownout detector was triggered`.
* **Cause:** 4 DC motors draw 1-2 Amperes during acceleration, causing battery voltage to sag below 3.0V.
* **Fix:**
  - Never power 4 DC motors from the ESP32's 3.3V or 5V pin!
  - Use a separate 2S (7.4V) or 3S (11.1V) Li-Ion / 18650 battery pack to power the L298N power terminal (`12V` input).
  - Power the ESP32 from a regulated 5V power bank or 5V buck converter into the ESP32 `VIN` pin.

#### Issue 1.3: MPU6050 Not Detected or Yaw Drifts
* **Symptom:** Serial logs `ERROR: MPU6050 not detected!` or Yaw keeps spinning continuously while stationary.
* **Fix:**
  1. Check I2C wiring: `SDA -> GPIO 21`, `SCL -> GPIO 22`, `VCC -> 3.3V` (or 5V if module has onboard 3.3V regulator).
  2. Test I2C address using an I2C scanner sketch: verify it replies at `0x68` (or `0x69` if AD0 is HIGH).
  3. **Zero-Motion Calibration:** When powering up or resetting the robot, keep it **completely stationary on a flat surface** for the first 3 seconds while `calibrateMPU()` computes the gyro Z zero-offset.

#### Issue 1.4: Ultrasonic Echo Pin Voltage Level
* **Symptom:** Ultrasonic returns `OPEN_DISTANCE` (400 cm) or 0 cm constantly.
* **Fix:** HC-SR04 Echo pin outputs 5V logic. ESP32 pins are 3.3V tolerant. While GPIO 27 often survives 5V, using a simple voltage divider (1kΩ between ECHO and GPIO 27, 2kΩ between GPIO 27 and GND) produces a clean 3.3V echo signal and protects the pin.

#### Issue 1.5: Flame Sensor Sensitivity Adjustment
* **Symptom:** Flame sensor constantly alerts without fire, or fails to detect lighter flame.
* **Fix:** Use a small flathead screwdriver to turn the blue potentiometer on the HW-491 module until the onboard indicator LED turns OFF in ambient room lighting and only turns ON when a lighter/candle is held 30-50 cm away.

---

## 2. Raspberry Pi 5 & Camera Debugging

### Camera Hardware & Detection Check
Connect your Raspberry Pi Camera Module 3 to the `CAM/DISP 1` port on the Raspberry Pi 5 (ribbon cable blue tab facing Ethernet/USB ports).

Run:
```bash
# Check if camera hardware is detected by kernel
rpicam-hello --list-cameras
```
Expected output:
```text
Available cameras
0 : imx708 [4608x2592 10-bit RGGB] (/base/axi/pcie@120000/rp1/i2c@88000/imx708@1a)
```

Test camera preview (opens 5-second preview):
```bash
rpicam-hello -t 5000
```

### Camera Troubleshooting
* **`No cameras available` error:**
  - Power off the Pi (`sudo shutdown -h now`).
  - Reseat the camera ribbon cable on both the Raspberry Pi CSI port and the camera sensor board.
  - On Pi 5, ensure you are using the narrower 22-pin camera cable, locked firmly into the connector.
* **OpenCV / Picamera2 Conflict:**
  - Always activate your virtual environment created with `--system-site-packages`:
    ```bash
    source .venv/bin/activate
    python3 -c "from picamera2 import Picamera2; cam = Picamera2(); print('Picamera2 OK')"
    ```

---

## 3. USB Serial Communication (Pi <-> ESP32)

### Step 3.1: Locate the Serial Port
Plug the ESP32 into one of the Raspberry Pi USB ports. Run:
```bash
ls -l /dev/ttyUSB* /dev/ttyACM*
```
You should see `/dev/ttyUSB0` or `/dev/ttyACM0`.

### Step 3.2: Verify Permissions
If you get `Permission denied` when opening the serial port:
```bash
sudo usermod -a -G dialout $USER
sudo chmod 666 /dev/ttyUSB0
```
*(Log out and log back in for group changes to take effect).*

### Step 3.3: Inspect Live Serial JSON Stream
Test the live telemetry stream coming from the ESP32:
```bash
python3 -c "import serial; s=serial.Serial('/dev/ttyUSB0', 115200, timeout=1); [print(s.readline().decode('utf-8', errors='ignore').strip()) for _ in range(10)]"
```
Expected output:
```json
{"type":"telemetry","yaw":0.0,"ultrasonic_cm":45.2,"flame":0,"flame_analog":3800,"servo":90,"state":"STOP","mode":"REMOTE"}
```

---

## 4. Vision & Model Weights (YOLO11 / YOLOv8)

### Pre-trained Weights Download
If you see `FileNotFoundError` or warning about `models/yolo11n.pt`:
```bash
python3 training/download_weights.py
```
This downloads `yolo11n.pt` and `yolov8n.pt` directly into the `models/` directory.

### High CPU Usage / Framerate Tuning
On Raspberry Pi 5 CPU:
- Native PyTorch `yolo11n.pt` runs at ~8-12 FPS.
- To increase framerate to 20-30 FPS:
  1. Export model to ONNX:
     ```bash
     python3 training/export_model.py --model models/yolo11n.pt --format onnx --imgsz 480
     ```
  2. Set `YOLO_MODEL = MODEL_DIR / "yolo11n.onnx"` in `config.py`.
  3. Set `DETECTION_EVERY_N_FRAMES = 2` or `3` to perform inference every 2nd or 3rd frame while keeping camera capture silky smooth at 30 FPS.

---

## 5. Cloud Mission Control Server & Global Access

### Running Locally (Same WiFi Network)
Start the cloud server on your workstation or Raspberry Pi:
```bash
source .venv/bin/activate
python3 server/app.py
```
Open in browser:
- `http://localhost:8000` (on local machine)
- `http://<PI_IP_ADDRESS>:8000` (from any phone or laptop on the same WiFi network)

### Global Remote Access Over Internet
To control the robot and view telemetry from anywhere in the world:

#### Method A: Free Cloudflare Tunnel (Zero Port Forwarding)
On the machine running `server/app.py`:
1. Install `cloudflared`:
   - Linux/Pi: `curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb && sudo dpkg -i cloudflared.deb`
   - Windows: download `cloudflared.exe`
2. Start the tunnel:
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```
3. Copy the generated public URL (e.g. `https://random-words.trycloudflare.com`).
4. Update `config.py` on the robot:
   ```python
   CLOUD_SERVER_URL = "https://random-words.trycloudflare.com"
   ```

#### Method B: 1-Click Free Cloud Deployment (Render.com)
1. Push your repository to GitHub.
2. Sign in to [Render.com](https://render.com) and click **New Web Service**.
3. Select your repository.
4. Set:
   - **Environment:** Docker (uses `server/Dockerfile`)
   - **Root Directory:** `server`
   - **Plan:** Free
5. Click **Deploy**. Render gives you a permanent global URL (e.g. `https://rescue-mission-control.onrender.com`).
6. Update `config.py`:
   ```python
   CLOUD_SERVER_URL = "https://rescue-mission-control.onrender.com"
   ```

---

## 6. Full End-to-End Execution Checklist

Follow these steps in order when powering on the robot:

```text
[ ] 1. Power on ESP32 & L298N battery switch.
[ ] 2. Keep robot STILL for 3 seconds (MPU6050 gyro calibration).
[ ] 3. Plug ESP32 USB cable into Raspberry Pi 5.
[ ] 4. Start Cloud Server (server/app.py) or verify cloud URL is active.
[ ] 5. On Raspberry Pi 5:
        cd ~/rescue_robot_pi
        source .venv/bin/activate
        python3 main.py
[ ] 6. Open Web Dashboard in browser:
        - Verify robot status shows "ONLINE"
        - Verify camera preview updates
        - Verify yaw angle matches physical robot rotation
[ ] 7. Safety Verification:
        - Place hand in front of ultrasonic sensor (< 20cm) -> Verify motors halt immediately.
        - Trigger flame sensor -> Verify instant FLAME ALERT alarm and halt.
```
