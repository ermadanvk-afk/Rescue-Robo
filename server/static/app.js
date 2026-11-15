// Search & Rescue Robot - Cloud Mission Control Web Application

let ws = null;
let lastTelemetry = { x_m: 0, y_m: 0, yaw: 0, ultrasonic_cm: 0, flame: 0, state: "IDLE" };
let trajectory = [];
let mapEvents = [];

const mapCanvas = document.getElementById("mapCanvas");
const ctx = mapCanvas ? mapCanvas.getContext("2d") : null;

// =========================================================
// WEBSOCKET INITIALIZATION & RECONNECT
// =========================================================
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("[WS] Connected to Mission Control live stream.");
    updateStatus(true);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "telemetry") {
        handleTelemetry(msg.data);
      } else if (msg.type === "preview") {
        handlePreview(msg.frame);
      } else if (msg.type === "alert") {
        handleAlert(msg.event);
      } else if (msg.type === "initial_state") {
        if (msg.telemetry) handleTelemetry(msg.telemetry);
        if (msg.frame) handlePreview(msg.frame);
        if (msg.events) {
          msg.events.forEach((ev) => addEventToTable(ev, false));
        }
      }
    } catch (err) {
      console.error("[WS] Parse error:", err);
    }
  };

  ws.onclose = () => {
    console.log("[WS] Connection lost; retrying in 2 seconds...");
    updateStatus(false);
    setTimeout(connectWebSocket, 2000);
  };
}

// =========================================================
// TELEMETRY & STATUS HANDLING
// =========================================================
function updateStatus(online) {
  const dot = document.getElementById("robot-status-dot");
  const text = document.getElementById("robot-status-text");
  if (online) {
    dot.className = "status-dot online";
    text.textContent = "ONLINE (STREAMING)";
  } else {
    dot.className = "status-dot offline";
    text.textContent = "DISCONNECTED";
  }
}

function handleTelemetry(telem) {
  lastTelemetry = telem;
  updateStatus(true);

  document.getElementById("val-yaw").textContent = (telem.yaw !== undefined) ? Number(telem.yaw).toFixed(1) : "0.0";
  document.getElementById("val-distance").textContent = (telem.ultrasonic_cm !== undefined) ? Number(telem.ultrasonic_cm).toFixed(1) : "--";
  document.getElementById("val-state").textContent = telem.state || "IDLE";
  document.getElementById("telem-updated").textContent = "Updated: Just now";

  const flameBox = document.getElementById("box-flame");
  const flameVal = document.getElementById("val-flame");
  if (telem.flame === 1) {
    flameBox.className = "telemetry-box hazard-alert";
    flameVal.textContent = "FIRE ALERT!";
  } else {
    flameBox.className = "telemetry-box";
    flameVal.textContent = "CLEAR";
  }

  const px = Number(telem.x_m || 0).toFixed(2);
  const py = Number(telem.y_m || 0).toFixed(2);
  document.getElementById("pose-display").textContent = `(${px}m, ${py}m)`;

  // Update Trajectory
  const x = telem.x_m || 0;
  const y = telem.y_m || 0;
  if (!trajectory.length || Math.hypot(x - trajectory[trajectory.length - 1].x, y - trajectory[trajectory.length - 1].y) > 0.05) {
    trajectory.push({ x, y });
    if (trajectory.length > 400) trajectory.shift();
  }

  drawMap();
}

function handlePreview(base64Frame) {
  const videoImg = document.getElementById("liveVideo");
  const placeholder = document.getElementById("videoPlaceholder");
  if (base64Frame) {
    videoImg.src = `data:image/jpeg;base64,${base64Frame}`;
    videoImg.style.display = "block";
    placeholder.style.display = "none";
  }
}

function handleAlert(eventData) {
  addEventToTable(eventData, true);
  // Add to map markers
  if (eventData.robot_pose) {
    mapEvents.push({
      type: eventData.event_type.toLowerCase().includes("human") ? "person" : "fire",
      x: eventData.robot_pose.x_m,
      y: eventData.robot_pose.y_m
    });
    drawMap();
  }
}

// =========================================================
// 2D CANVAS MAP DRAWING
// =========================================================
function drawMap() {
  if (!ctx || !mapCanvas) return;
  const w = mapCanvas.width;
  const h = mapCanvas.height;
  const cx = w / 2;
  const cy = h / 2;
  const ppm = 35; // 35 pixels per meter

  // Clear
  ctx.fillStyle = "#090d13";
  ctx.fillRect(0, 0, w, h);

  // Grid lines
  ctx.strokeStyle = "#1b222d";
  ctx.lineWidth = 1;
  for (let x = cx % ppm; x < w; x += ppm) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
  }
  for (let y = cy % ppm; y < h; y += ppm) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }

  // Axes
  ctx.strokeStyle = "#273243";
  ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, h); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(0, cy); ctx.lineTo(w, cy); ctx.stroke();

  // Draw Trajectory Trail
  if (trajectory.length > 1) {
    ctx.strokeStyle = "#388bfd";
    ctx.lineWidth = 2;
    ctx.beginPath();
    trajectory.forEach((pt, i) => {
      const px = cx + pt.x * ppm;
      const py = cy - pt.y * ppm;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
  }

  // Draw Alert Markers
  mapEvents.forEach((ev) => {
    const px = cx + ev.x * ppm;
    const py = cy - ev.y * ppm;
    ctx.fillStyle = (ev.type === "person") ? "#238636" : "#da3633";
    ctx.beginPath();
    ctx.arc(px, py, 6, 0, Math.PI * 2);
    ctx.fill();
  });

  // Draw Robot Pose
  const rx = cx + (lastTelemetry.x_m || 0) * ppm;
  const ry = cy - (lastTelemetry.y_m || 0) * ppm;
  const headingRad = (lastTelemetry.yaw || 0) * (Math.PI / 180);

  // Robot Body
  ctx.fillStyle = "#f0883e";
  ctx.beginPath();
  ctx.arc(rx, ry, 9, 0, Math.PI * 2);
  ctx.fill();

  // Heading Pointer
  const arrowLen = 20;
  const hx = rx + arrowLen * Math.cos(headingRad);
  const hy = ry - arrowLen * Math.sin(headingRad);
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(rx, ry);
  ctx.lineTo(hx, hy);
  ctx.stroke();
}

// =========================================================
// TABLE & ALERTS
// =========================================================
function addEventToTable(ev, prepend = true) {
  const tbody = document.getElementById("events-tbody");
  // Remove placeholder if present
  if (tbody.children.length === 1 && tbody.children[0].innerText.includes("No alerts")) {
    tbody.innerHTML = "";
  }

  const tr = document.createElement("tr");
  const isHuman = (ev.event_type || "").includes("HUMAN");
  const badgeClass = isHuman ? "badge-human" : "badge-fire";

  const timeStr = ev.received_at || new Date().toLocaleTimeString();
  const label = ev.label || "person";
  const conf = ev.confidence ? `${(ev.confidence * 100).toFixed(0)}%` : "N/A";
  const coords = ev.robot_pose ? `(${ev.robot_pose.x_m}m, ${ev.robot_pose.y_m}m)` : "(0.0m, 0.0m)";

  let imgCol = "None";
  if (ev.image_url) {
    imgCol = `<a href="${ev.image_url}" target="_blank"><img src="${ev.image_url}" class="snapshot-thumb" alt="Evidence" /></a>`;
  }

  tr.innerHTML = `
    <td>${timeStr}</td>
    <td><span class="badge-event ${badgeClass}">${ev.event_type}</span></td>
    <td><strong>${label}</strong></td>
    <td>${conf}</td>
    <td>${coords}</td>
    <td>${imgCol}</td>
  `;

  if (prepend) {
    tbody.insertBefore(tr, tbody.firstChild);
  } else {
    tbody.appendChild(tr);
  }

  const countSpan = document.getElementById("event-count");
  if (countSpan) {
    countSpan.textContent = `${tbody.children.length} Events`;
  }
}

// =========================================================
// COMMAND DISPATCH
// =========================================================
function sendCommand(cmdObj) {
  fetch("/api/command", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cmdObj)
  }).catch((err) => console.error("Command error:", err));
}

function sendDrive(action) {
  sendCommand({ cmd: "drive", action: action, speed: 190 });
}

function sendEStop() {
  sendCommand({ cmd: "drive", action: "STOP", mode: "MANUAL" });
  setMode("MANUAL");
}

function setMode(mode) {
  const btnAuto = document.getElementById("btn-mode-auto");
  const btnManual = document.getElementById("btn-mode-manual");
  if (mode === "AUTO") {
    btnAuto.className = "btn-mode active";
    btnManual.className = "btn-mode";
  } else {
    btnAuto.className = "btn-mode";
    btnManual.className = "btn-mode active";
  }
  sendCommand({ cmd: "mode", mode: mode });
}

// Keyboard shortcuts for manual driving (W, A, S, D, Space)
window.addEventListener("keydown", (e) => {
  const key = e.key.toUpperCase();
  if (key === "W") sendDrive("FORWARD");
  else if (key === "S") sendDrive("BACKWARD");
  else if (key === "A") sendDrive("LEFT");
  else if (key === "D") sendDrive("RIGHT");
  else if (key === " " || key === "X") sendDrive("STOP");
});

window.onload = () => {
  connectWebSocket();
  drawMap();
};
