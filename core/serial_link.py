import json
import threading
import time

class SerialTelemetry:
    def __init__(self, port=None, baud=115200):
        self.latest = {}
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        self.ser = None
        if not port:
            print("Serial telemetry disabled (SERIAL_PORT=None)")
            return
        try:
            import serial
            self.ser = serial.Serial(port, baud, timeout=1)
            time.sleep(2)
            self.running = True
            self.thread = threading.Thread(target=self._reader, daemon=True)
            self.thread.start()
            print(f"Listening for ESP32 telemetry on {port} @ {baud}")
        except Exception as exc:
            print(f"Could not open serial port {port}: {exc}")

    def _reader(self):
        while self.running and self.ser:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                data = json.loads(line)
                if isinstance(data, dict):
                    with self.lock:
                        self.latest = data
            except json.JSONDecodeError:
                print("Ignoring non-JSON serial line")
            except Exception as exc:
                print(f"Serial read error: {exc}")
                time.sleep(0.2)

    def get_latest(self):
        with self.lock:
            return dict(self.latest)

    def close(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        if self.ser:
            self.ser.close()
