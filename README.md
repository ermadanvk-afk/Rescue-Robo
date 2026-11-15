# AI Search & Rescue Autonomous Robot

An autonomous search & rescue rover system powered by **Raspberry Pi 5** and **ESP32**. The robot systematically navigates and explores space around it using sensor fusion (MPU6050 IMU, ultrasonic sensor on a sweeping servo, and flame hazard detection), detects humans/survivors using edge AI computer vision (YOLO11/YOLOv8), logs incidents with snapshot images, and streams telemetry and live alerts to a globally accessible web dashboard.

---

## System Architecture

```text
                  +----------------------------------------------+
                  |           GLOBAL CLOUD SERVER                |
                  |     FastAPI + WebSockets + Web Dashboard     |
                  |       (Render / Railway / VPS / Local)       |
                  +-----------------------^----------------------+
                                          |
                      Internet / 4G / Wi-Fi (JSON & Snapshots)
                                          |
+-----------------------------------------v-----------------------------------------+
|                                RASPBERRY PI 5                                     |
|  - Vision: YOLO11 / YOLOv8 edge inference (Person detection)                     |
|  - Camera: Raspberry Pi Camera Module 3 (Picamera2 / OpenCV)                      |
|  - Autonomous Navigator: Space coverage, visual servoing target centering         |
|  - Cloud Sync: Telemetry, event debouncing & evidence image uploads              |
+-----------------------------------------^-----------------------------------------+
                                          |
                        USB Serial (Bidirectional JSON @ 115200)
                                          |
+-----------------------------------------v-----------------------------------------+
|                                    ESP32                                          |
|  - Sensors: MPU6050 (Yaw/Pitch/Roll), HC-SR04 (Ultrasonic), HW-491 (Flame)        |
|  - Actuators: 4x DC Motors via L298N driver + 1x SG90 Servo (Scanner)             |
|  - Local Safety: Automatic emergency brake if obstacle < 18cm or fire detected   |
+-----------------------------------------------------------------------------------+
```

---

## 1. Quick Start on Raspberry Pi 5

Clone this repository directly to your Raspberry Pi:

```bash
git clone <your-repo-url> rescue_robot_pi
cd rescue_robot_pi
```

### Automated Setup
Run the setup script:
```bash
chmod +x setup_rpi.sh
./setup_rpi.sh
```
This automatically configures `python3-picamera2`, user group permissions (`dialout`, `video`, `i2c`), virtual environment `.venv`, python dependencies, and downloads pre-trained YOLO weights.

### Run the Robot Brain
```bash
source .venv/bin/activate
python3 main.py
```

### Keyboard Controls (in GUI Window)
* **`Space`**: Toggle between **AUTONOMOUS SEARCH** and **MANUAL OVERRIDE**.
* **`W` / `A` / `S` / `D`**: Manual drive when in Manual mode.
* **`R`**: Start / Stop video recording to `recordings/`.
* **`M`**: Save 2D exploration map snapshot.
* **`Q` / `Esc`**: Quit safely.

---

## 2. ESP32 Firmware Setup

1. Open `firmware/rescue_robot_esp32/rescue_robot_esp32.ino` (or top-level `esp.ino`) in Arduino IDE.
2. Ensure you have the `ESP32Servo` library installed via the Arduino Library Manager.
3. Select your ESP32 board and COM port.
4. Upload the code to the ESP32.
5. **Important:** When powering on, keep the robot completely still on a flat surface for 3 seconds while the MPU6050 calibrates its gyro offset.

### Pinout Mapping
* **L298N Motor Driver:** `ENA=32`, `IN1=18`, `IN2=19`, `IN3=25`, `IN4=26`, `ENB=33`
* **Ultrasonic (HC-SR04):** `TRIG=5`, `ECHO=27`
* **Servo (SG90):** `Signal=13`
* **MPU6050 IMU:** `SDA=21`, `SCL=22`
* **HW-491 Flame Sensor:** `AO=34`, `DO=35`

---

## 3. Global Remote Mission Control Server

The server provides a responsive web dashboard for real-time monitoring and control from anywhere in the world.

### Start Server Locally
```bash
source .venv/bin/activate
python3 server/app.py
```
Open **`http://localhost:8000`** in your browser.

### Features
* **Live Video Stream / Snapshot Pane**: Real-time camera feed with target detection bounding boxes.
* **2D Search Map Canvas**: Visualizes searched space, trajectory, MPU6050 heading angle pointer, obstacles, and detected victim markers.
* **Sensor Gauges**: Heading (Yaw), Ultrasonic range gauge, Flame alert banner with audio/visual alarm.
* **Mission Controls**: Switch between Autonomous Search and Manual D-Pad controls.
* **Incident Alert Log**: Event history with clickable evidence photos.

### Deploy Globally (Render / Railway / VPS)
You can deploy `server/` to **Render.com** (Free tier) with 1 click using the included `server/Dockerfile`.
Then update `config.py` on your robot:
```python
CLOUD_SERVER_URL = "https://your-rescue-dashboard.onrender.com"
```

---

## 4. Model Training & Fine-Tuning (`train.py`)

While pre-trained `yolo11n.pt` and `yolov8n.pt` already recognize the `person` class out of the box, you can fine-tune on custom rescue objects (e.g. fallen survivors, hazard signs, thermal blankets) using our training pipeline on a GPU machine or Google Colab:

### 1-Click Google Colab Notebook
Upload and run:
`training/Train_Rescue_Object_Colab.ipynb`

### Local Training CLI
```bash
# 1. Download base weights
python training/download_weights.py

# 2. Prepare and split dataset
python training/prepare_dataset.py --src-images path/to/images --classes "person,survivor,fire"

# 3. Train YOLO model
python training/train.py --data dataset/data.yaml --epochs 50 --batch 16 --model yolo11n.pt

# 4. Export to ONNX for 25+ FPS Raspberry Pi CPU inference
python training/export_model.py --model models/best.pt --format onnx --imgsz 480
```

---

## 5. Troubleshooting & Debug Guide

For detailed hardware debugging (brownouts, common ground, I2C scanner, USB permissions, baud rates, and cloud tunnels), see:
**[DEBUG_GUIDE.md](DEBUG_GUIDE.md)**

---

## 6. Running Tests

Run the automated test suite to verify serial protocol, navigator state transitions, event managers, and server endpoints:

```bash
python -m unittest discover -s tests -p "test_*.py"
```
