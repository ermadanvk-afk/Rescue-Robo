import os
import sys
import time
import json
import asyncio
import logging
import threading
from typing import Set, Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import serial
import serial.tools.list_ports

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("RobotServer")

# Paths
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

# Environment / Serial settings
SERIAL_BAUD = int(os.getenv("SERIAL_BAUD", "115200"))
SERIAL_PORT = os.getenv("SERIAL_PORT", None)

app = FastAPI(title="ESP32 Robot Controller API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# SERIAL COMMUNICATION MANAGER
# ---------------------------------------------------------------------------
class SerialBridge:
    def __init__(self, baud: int = 115200, preferred_port: Optional[str] = None):
        self.baud = baud
        self.preferred_port = preferred_port
        self.ser: Optional[serial.Serial] = None
        self.lock = threading.Lock()
        self.running = False
        self.read_thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.fire_detected = False
        self.latest_telemetry = {
            "distance": 0.0,
            "fire": False,
            "state": "STOP",
            "connected": False
        }

    def find_serial_port(self) -> Optional[str]:
        if self.preferred_port and os.path.exists(self.preferred_port):
            return self.preferred_port

        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            # Common ESP32/CH340/CP2102/FTDI identifiers
            desc = (port.description or "").lower()
            hwid = (port.hwid or "").lower()
            if any(k in desc or k in hwid for k in ["cp210", "ch340", "ch341", "usb serial", "esp32", "uart"]):
                logger.info(f"Auto-detected ESP32 at: {port.device} ({port.description})")
                return port.device

        # Linux common defaults on Raspberry Pi
        for common in ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyACM1"]:
            if os.path.exists(common):
                logger.info(f"Found existing serial port: {common}")
                return common

        if ports:
            logger.info(f"Falling back to first available port: {ports[0].device}")
            return ports[0].device

        return None

    def connect(self) -> bool:
        port = self.find_serial_port()
        if not port:
            logger.warning("No serial port found for ESP32. Running in SIMULATION/DISCONNECTED mode.")
            self.latest_telemetry["connected"] = False
            return False

        try:
            with self.lock:
                self.ser = serial.Serial(port, self.baud, timeout=0.1)
                time.sleep(1.5)  # Allow ESP32 reboot delay
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
            self.latest_telemetry["connected"] = True
            logger.info(f"Connected to ESP32 on {port} at {self.baud} baud.")
            return True
        except Exception as e:
            logger.error(f"Failed to open serial port {port}: {e}")
            self.latest_telemetry["connected"] = False
            return False

    def send_command(self, cmd: str) -> bool:
        clean_cmd = cmd.strip().upper()
        if not clean_cmd:
            return False

        # Commands are forwarded directly to ESP32 without being blocked,
        # allowing operator to steer or back away even when fire alert is active.
        payload = (clean_cmd + "\n").encode("utf-8")
        if self.ser and self.ser.is_open:
            try:
                with self.lock:
                    self.ser.write(payload)
                    self.ser.flush()
                logger.debug(f"Sent to ESP32: {clean_cmd}")
                return True
            except Exception as e:
                logger.error(f"Error writing to serial: {e}")
                return False
        else:
            logger.info(f"[SIMULATION] ESP32 received: {clean_cmd}")
            return True

    def start_reading(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.running = True
        self.read_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.read_thread.start()

    def _reader_loop(self):
        while self.running:
            if not self.ser or not self.ser.is_open:
                time.sleep(1.0)
                # Attempt auto-reconnect
                self.connect()
                continue

            try:
                line = ""
                with self.lock:
                    if self.ser.in_waiting > 0:
                        line = self.ser.readline().decode("utf-8", errors="replace").strip()
                
                if line:
                    logger.info(f"[ESP32 -> RPi] {line}")
                    self._handle_serial_line(line)
            except Exception as e:
                logger.error(f"Serial read error: {e}")
                time.sleep(0.5)

            time.sleep(0.01)

    def _handle_serial_line(self, line: str):
        if line.startswith("EVENT:FIRE_DETECTED"):
            self.fire_detected = True
            self.latest_telemetry["fire"] = True
            self.latest_telemetry["state"] = "STOP"
            msg = {"type": "fire_alert", "fire": True, "message": "FIRE DETECTED! Motors stopped."}
            self._broadcast(msg)

        elif line.startswith("EVENT:FIRE_CLEARED"):
            self.fire_detected = False
            self.latest_telemetry["fire"] = False
            msg = {"type": "fire_alert", "fire": False, "message": "Fire hazard cleared."}
            self._broadcast(msg)

        elif line.startswith("EVENT:OBSTACLE_DETECTED"):
            msg = {"type": "obstacle_alert", "message": "Obstacle detected in front!"}
            self._broadcast(msg)

        elif line.startswith("TELEMETRY:"):
            try:
                raw_json = line[len("TELEMETRY:"):].strip()
                data = json.loads(raw_json)
                self.latest_telemetry.update(data)
                self.latest_telemetry["connected"] = True
                self.fire_detected = bool(data.get("fire", False))
                msg = {"type": "telemetry", "data": self.latest_telemetry}
                self._broadcast(msg)
            except Exception as ex:
                logger.debug(f"Telemetry parse error: {ex}")

    def _broadcast(self, payload: dict):
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(manager.broadcast(payload), self.loop)

    def close(self):
        self.running = False
        if self.ser and self.ser.is_open:
            with self.lock:
                self.ser.close()

bridge = SerialBridge(baud=SERIAL_BAUD, preferred_port=SERIAL_PORT)

# ---------------------------------------------------------------------------
# WEBSOCKET CONNECTION MANAGER
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self.lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")
        # Send initial state immediately
        await websocket.send_json({
            "type": "init",
            "telemetry": bridge.latest_telemetry,
            "fire": bridge.fire_detected
        })

    async def disconnect(self, websocket: WebSocket):
        async with self.lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        async with self.lock:
            dead_sockets = set()
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_sockets.add(connection)
            for dead in dead_sockets:
                self.active_connections.discard(dead)

manager = ConnectionManager()

# ---------------------------------------------------------------------------
# FASTAPI LIFECYCLE & ROUTES
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_running_loop()
    bridge.connect()
    bridge.start_reading(loop)
    logger.info("Robot Backend startup complete. Ready for frontend clients.")

@app.on_event("shutdown")
def shutdown_event():
    bridge.send_command("STOP")
    bridge.close()
    logger.info("Robot Backend shutdown complete.")

@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "fire_detected": bridge.fire_detected,
        "telemetry": bridge.latest_telemetry
    }

@app.post("/api/command/{cmd}")
async def post_command(cmd: str):
    success = bridge.send_command(cmd)
    return {"command": cmd, "success": success, "fire_active": bridge.fire_detected}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                cmd = msg.get("cmd") or msg.get("action")
                if cmd:
                    bridge.send_command(str(cmd))
            except json.JSONDecodeError:
                # Direct string command e.g. "F", "STOP"
                bridge.send_command(data.strip())
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
        await manager.disconnect(websocket)

# ---------------------------------------------------------------------------
# STATIC FRONTEND SERVING
# ---------------------------------------------------------------------------
@app.get("/")
async def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"error": "Frontend index.html not found"}, status_code=404)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

if __name__ == "__main__":
    # Host on 0.0.0.0 so any device on the local network / Wi-Fi can access it
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
