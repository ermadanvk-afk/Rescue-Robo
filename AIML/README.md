# ESP32 Robot Controller with FastAPI & WebSocket UI

This project provides a complete robot control system featuring a **FastAPI backend** running on a **Raspberry Pi**, an **ESP32 motor & sensor controller** (with MPU removed and flame detection retained), and a **responsive virtual joystick web frontend**.

---

## 📁 Project Structure

```
AIML/
├── backend/
│   ├── main.py              # FastAPI server, Serial bridge & WebSocket manager
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── index.html           # UI layout with Joystick, D-Pad & Fire Alarm Modal
│   ├── style.css            # Dark cyber-robotics responsive stylesheet
│   └── script.js            # WebSocket client, Virtual Joystick & Web Audio siren
├── esp32/
│   └── esp32_robot.ino      # Updated ESP32 firmware (No MPU, Serial commands, Fire safety)
└── PRAC.ino                 # Original reference code
```

---

## 🚀 Quick Setup Instructions

### 1. Flash the ESP32
1. Open `esp32/esp32_robot.ino` in the Arduino IDE.
2. Select your ESP32 board and COM port.
3. Install the `ESP32Servo` library if not already installed (`Sketch -> Include Library -> Manage Libraries...`).
4. Click **Upload**.

### 2. Connect ESP32 to Raspberry Pi
- Plug the ESP32 into one of the Raspberry Pi's USB ports using a standard USB-to-Data cable.
- This creates a reliable serial port (e.g. `/dev/ttyUSB0` or `/dev/ttyACM0`).

### 3. Run the Backend on Raspberry Pi
Open a terminal on your Raspberry Pi:

```bash
# Navigate to project directory
cd backend

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server listening on 0.0.0.0 (all network interfaces)
python main.py
```

### 4. Access the Joystick from Any Device on the Same Wi-Fi
1. Find your Raspberry Pi's local IP address:
   ```bash
   hostname -I
   ```
   *(Example: `192.168.1.45`)*
2. On any smartphone, tablet, or laptop connected to the same Wi-Fi, open your browser:
   ```
   http://<YOUR_RPI_IP>:8000
   ```
3. Control the robot using the **Virtual Joystick**, **Tactile D-Pad**, or **Keyboard (WASD / Arrows)**.

---

## 🔥 Fire Detection Event Flow
1. HW-491 Flame sensor detects fire on GPIO 35 (`FLAME_DO`).
2. ESP32 **instantly stops all motors** and transmits `EVENT:FIRE_DETECTED\n` over USB Serial.
3. FastAPI backend immediately broadcasts `{"type": "fire_alert", "fire": true}` over WebSockets.
4. Frontend triggers:
   - Fullscreen flashing emergency hazard modal.
   - Synthesized siren alarm via Web Audio API.
   - Mobile haptic vibration (`navigator.vibrate`).
   - Movement controls lock out until fire clears.
