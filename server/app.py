import os
import time
import json
import uuid
import shutil
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Request, File, Form, UploadFile, WebSocket, WebSocketDisconnect, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

SERVER_DIR = Path(__file__).resolve().parent
STATIC_DIR = SERVER_DIR / "static"
UPLOADS_DIR = STATIC_DIR / "uploads"
TEMPLATES_DIR = SERVER_DIR / "templates"

for folder in [STATIC_DIR, UPLOADS_DIR, TEMPLATES_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Search & Rescue Robot - Cloud Mission Control")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# In-Memory State
latest_telemetry = {
    "yaw": 0.0,
    "ultrasonic_cm": 0.0,
    "flame": 0,
    "x_m": 0.0,
    "y_m": 0.0,
    "state": "OFFLINE",
    "_last_seen": 0
}
latest_preview_frame = None  # Base64 string
event_history: List[dict] = []
pending_robot_commands: List[dict] = []
active_browser_websockets: List[WebSocket] = []

API_KEY = os.environ.get("RESCUE_API_KEY", "rescue-robot-secret-key-2026")


def check_auth(x_api_key: Optional[str] = Header(None)):
    # Optional header check for robot API calls
    if API_KEY and x_api_key and x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return True


@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """Renders the main Mission Control Dashboard."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "Search & Rescue Robot - Global Mission Control"}
    )


@app.post("/api/telemetry")
async def post_telemetry(payload: dict, x_api_key: Optional[str] = Header(None)):
    """Receives periodic telemetry from the robot on the Raspberry Pi."""
    global latest_telemetry
    check_auth(x_api_key)

    telem = payload.get("telemetry", {})
    latest_telemetry.update(telem)
    latest_telemetry["_last_seen"] = time.time()

    # Broadcast to all connected web browsers via WebSocket
    await broadcast_ws({
        "type": "telemetry",
        "data": latest_telemetry
    })

    # Pop oldest pending command for robot to execute (if any)
    cmd = pending_robot_commands.pop(0) if pending_robot_commands else None
    return {"status": "ok", "pending_command": cmd}


@app.get("/api/telemetry")
async def get_telemetry():
    """Returns the latest robot telemetry and connection health."""
    is_online = (time.time() - latest_telemetry.get("_last_seen", 0)) < 3.5
    return {
        "online": is_online,
        "telemetry": latest_telemetry
    }


@app.post("/api/preview")
async def post_preview(payload: dict, x_api_key: Optional[str] = Header(None)):
    """Receives a compressed JPEG frame from robot camera for live streaming."""
    global latest_preview_frame
    check_auth(x_api_key)
    b64_frame = payload.get("frame")
    if b64_frame:
        latest_preview_frame = b64_frame
        await broadcast_ws({
            "type": "preview",
            "frame": b64_frame
        })
    return {"status": "ok"}


@app.get("/api/preview")
async def get_preview():
    """Returns latest preview frame."""
    return {"frame": latest_preview_frame}


@app.post("/api/events")
async def post_event(
    event_json: str = Form(...),
    file: Optional[UploadFile] = File(None),
    x_api_key: Optional[str] = Header(None)
):
    """Receives target detection alerts and hazard events with snapshot images."""
    check_auth(x_api_key)
    try:
        event_data = json.loads(event_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid event JSON")

    # Save uploaded image if attached
    if file and file.filename:
        safe_name = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).name}"
        dest_path = UPLOADS_DIR / safe_name
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        event_data["image_url"] = f"/static/uploads/{safe_name}"
    else:
        event_data["image_url"] = None

    event_data["received_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    event_history.insert(0, event_data)
    if len(event_history) > 200:
        event_history.pop()

    # Broadcast alert event to dashboard browsers immediately
    await broadcast_ws({
        "type": "alert",
        "event": event_data
    })

    return {"status": "success", "event_id": event_data.get("event_id")}


@app.get("/api/events")
async def get_events():
    """Returns recent incident events."""
    return {"events": event_history}


@app.post("/api/command")
async def post_command(command: dict):
    """Receives remote manual control or mode change commands from the Web Dashboard."""
    # Example: {"action": "FORWARD", "speed": 180} or {"mode": "AUTO"}
    pending_robot_commands.append(command)
    print(f"[Server] Queued remote command for robot: {command}")
    return {"status": "queued", "command": command}


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time WebSocket connection for live telemetry, map, alerts, and preview."""
    await websocket.accept()
    active_browser_websockets.append(websocket)
    try:
        # Send initial state
        await websocket.send_text(json.dumps({
            "type": "initial_state",
            "telemetry": latest_telemetry,
            "events": event_history[:20],
            "frame": latest_preview_frame
        }))
        while True:
            # Keep-alive loop; receive potential operator inputs
            msg = await websocket.receive_text()
            try:
                cmd_data = json.loads(msg)
                if "cmd" in cmd_data or "action" in cmd_data or "mode" in cmd_data:
                    pending_robot_commands.append(cmd_data)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        if websocket in active_browser_websockets:
            active_browser_websockets.remove(websocket)


async def broadcast_ws(message_dict):
    """Sends message to all connected web clients."""
    if not active_browser_websockets:
        return
    msg_str = json.dumps(message_dict)
    dead_sockets = []
    for ws in active_browser_websockets:
        try:
            await ws.send_text(msg_str)
        except Exception:
            dead_sockets.append(ws)
    for ws in dead_sockets:
        if ws in active_browser_websockets:
            active_browser_websockets.remove(ws)


if __name__ == "__main__":
    import uvicorn
    print("[Server] Starting Cloud Mission Control on 0.0.0.0:8000...")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
