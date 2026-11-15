import json
import threading
import time
import glob
import sys

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None


class SerialTelemetry:
    """Full-duplex serial interface between Raspberry Pi and ESP32.

    Features:
    - Auto-detects ESP32 serial port if not explicitly configured
    - Non-blocking background thread reading JSON telemetry
    - Thread-safe command sender (`send_command`)
    - Automatic reconnection handling
    - Simulated fallback mode for development without hardware
    """

    def __init__(self, port=None, baud=115200, timeout=1.0, simulated=False):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.simulated = simulated

        self.latest = {
            "type": "telemetry",
            "yaw": 0.0,
            "pitch": 0.0,
            "roll": 0.0,
            "ultrasonic_cm": 150.0,
            "flame": 0,
            "flame_analog": 4095,
            "servo": 90,
            "state": "IDLE"
        }
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.ser = None

        if self.simulated or serial is None:
            print("[Serial] Running in SIMULATED telemetry mode.")
            self._start_simulated_thread()
            return

        # Auto-discover port if not provided
        if not self.port:
            self.port = self._find_esp32_port()

        if self.port:
            self._connect()
        else:
            print("[Serial] No ESP32 serial port detected; falling back to simulated mode.")
            self._start_simulated_thread()

    def _find_esp32_port(self):
        """Auto-detects typical ESP32 serial ports on Linux/Pi or Windows."""
        if serial is None:
            return None

        # Check via serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in ("ch340", "cp210", "usb-serial", "ftdi", "esp32", "uart")):
                print(f"[Serial] Auto-detected ESP32 at: {p.device} ({p.description})")
                return p.device

        # Common Linux device nodes
        candidate_patterns = ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/serial0"]
        for pattern in candidate_patterns:
            matches = glob.glob(pattern)
            if matches:
                print(f"[Serial] Auto-selected first matching port: {matches[0]}")
                return matches[0]

        return None

    def _connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
            time.sleep(2.0)  # Allow ESP32 boot/reset to settle
            self.running = True
            self.thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.thread.start()
            print(f"[Serial] Connected to ESP32 on {self.port} @ {self.baud} baud.")
        except Exception as exc:
            print(f"[Serial] Connection failed on {self.port}: {exc}")
            self.ser = None
            self._start_simulated_thread()

    def _reader_loop(self):
        """Continuously reads newline-delimited JSON telemetry from ESP32."""
        buffer = ""
        while self.running and self.ser:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                # Parse JSON telemetry
                if line.startswith("{") and line.endswith("}"):
                    try:
                        data = json.loads(line)
                        if isinstance(data, dict):
                            with self.lock:
                                self.latest.update(data)
                                self.latest["_last_received"] = time.time()
                    except json.JSONDecodeError:
                        pass
                else:
                    # Print raw debug message from ESP32 if not JSON
                    if any(key in line for key in ("FLAME", "OBSTACLE", "READY", "ERROR", "MPU")):
                        print(f"[ESP32 Log] {line}")

            except serial.SerialException as exc:
                print(f"[Serial] Disconnected: {exc}. Attempting reconnection...")
                self._reconnect()
                break
            except Exception as exc:
                print(f"[Serial] Read error: {exc}")
                time.sleep(0.1)

    def _reconnect(self):
        """Attempts to reconnect to ESP32 upon cable reconnect."""
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

        time.sleep(2.0)
        if self.port and self.running:
            self._connect()

    def send_command(self, cmd_dict):
        """Sends a JSON command string down to the ESP32.

        Example:
        send_command({"cmd": "drive", "action": "FORWARD", "speed": 180})
        """
        if not isinstance(cmd_dict, dict):
            return False

        line = json.dumps(cmd_dict) + "\n"

        if self.ser and self.ser.is_open:
            try:
                with self.lock:
                    self.ser.write(line.encode("utf-8"))
                    self.ser.flush()
                return True
            except Exception as exc:
                print(f"[Serial] Write error: {exc}")
                return False
        elif self.simulated:
            # Echo simulated command
            with self.lock:
                self.latest["_last_cmd"] = cmd_dict
            return True
        return False

    def _start_simulated_thread(self):
        """Generates realistic telemetry when running without hardware."""
        self.simulated = True
        self.running = True

        def sim_worker():
            t0 = time.time()
            sim_yaw = 0.0
            while self.running:
                dt = time.time() - t0
                # Simulate smooth heading drift and random ultrasonic distance
                with self.lock:
                    cmd = self.latest.get("_last_cmd", {})
                    action = cmd.get("action", "FORWARD") if isinstance(cmd, dict) else "FORWARD"

                    if action == "LEFT":
                        sim_yaw = (sim_yaw - 2.5) % 360
                    elif action == "RIGHT":
                        sim_yaw = (sim_yaw + 2.5) % 360

                    # Realistic distance variation
                    dist = 60.0 + 30.0 * (1.0 + 0.5 * (dt % 5.0))

                    self.latest.update({
                        "type": "telemetry",
                        "yaw": round(sim_yaw, 1),
                        "pitch": 0.0,
                        "roll": 0.0,
                        "ultrasonic_cm": round(dist, 1),
                        "flame": 0,
                        "servo": 90,
                        "state": action,
                        "_simulated": True,
                        "_last_received": time.time()
                    })
                time.sleep(0.1)

        self.thread = threading.Thread(target=sim_worker, daemon=True)
        self.thread.start()

    def get_latest(self):
        with self.lock:
            return dict(self.latest)

    def close(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
        print("[Serial] Serial link closed.")
