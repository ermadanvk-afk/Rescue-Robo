// ==========================================================================
// ESP32 ROBOT CONTROLLER - CLIENT SCRIPT
// ==========================================================================

// Global state
let socket = null;
let currentCommand = 'STOP';
let isFireAlertActive = false;
let isAudioMuted = false;
let audioContext = null;
let sirenInterval = null;

// UI Elements
const connectionPill = document.getElementById('connection-pill');
const connectionText = document.getElementById('connection-text');
const firePill = document.getElementById('fire-pill');
const fireStatusText = document.getElementById('fire-status-text');
const distanceVal = document.getElementById('distance-val');
const distanceBar = document.getElementById('distance-bar');
const stateVal = document.getElementById('state-val');
const fireOverlay = document.getElementById('fire-overlay');
const fireStrip = document.getElementById('fire-strip');
const silenceBtn = document.getElementById('silence-alarm-btn');
const dismissBtn = document.getElementById('dismiss-overlay-btn');

// Joystick elements
const joystickZone = document.getElementById('joystick-zone');
const joystickKnob = document.getElementById('joystick-knob');
const MAX_RADIUS = 70; // Max movement radius of joystick handle
const DEADZONE = 20;

// ==========================================================================
// 1. WEBSOCKET CONNECTION & AUTO-RECONNECT
// ==========================================================================
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  connectionText.textContent = 'CONNECTING...';
  connectionPill.className = 'pill disconnected';

  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    connectionText.textContent = 'CONNECTED';
    connectionPill.className = 'pill connected';
  };

  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleServerMessage(data);
    } catch (e) {
      console.warn('Malformed WS message:', event.data);
    }
  };

  socket.onclose = () => {
    connectionText.textContent = 'RECONNECTING...';
    connectionPill.className = 'pill disconnected';
    setTimeout(initWebSocket, 2000);
  };

  socket.onerror = (err) => {
    console.error('WebSocket encountered error:', err);
    socket.close();
  };
}

// ==========================================================================
// 2. MESSAGE & TELEMETRY HANDLER
// ==========================================================================
function handleServerMessage(data) {
  if (data.type === 'init' || data.type === 'telemetry') {
    const telem = data.telemetry || data.data;
    if (telem) {
      updateTelemetry(telem);
    }
  }

  if (data.type === 'fire_alert') {
    setFireAlert(data.fire);
  }
}

function updateTelemetry(telem) {
  // Update Distance
  if (telem.distance !== undefined && telem.distance !== null) {
    const dist = parseFloat(telem.distance);
    if (dist >= 350 || dist < 0) {
      distanceVal.textContent = '> 350';
      distanceBar.style.width = '100%';
      distanceBar.style.backgroundColor = 'var(--accent-cyan)';
    } else {
      distanceVal.textContent = dist.toFixed(1);
      const percentage = Math.min(100, Math.max(5, (dist / 100) * 100));
      distanceBar.style.width = `${percentage}%`;

      if (dist < 25) {
        distanceBar.style.backgroundColor = 'var(--danger-red)';
      } else if (dist < 50) {
        distanceBar.style.backgroundColor = 'var(--warning-amber)';
      } else {
        distanceBar.style.backgroundColor = 'var(--accent-cyan)';
      }
    }
  }

  // Update State Display
  if (telem.state) {
    stateVal.textContent = telem.state;
    stateVal.className = `metric-val state-${telem.state.toLowerCase()}`;
  }

  // Fire state from telemetry
  if (telem.fire !== undefined) {
    setFireAlert(telem.fire);
  }
}

// ==========================================================================
// 3. FIRE ALARM & AUDIO / VIBRATION SYSTEM
// ==========================================================================
function setFireAlert(isActive) {
  if (isActive === isFireAlertActive) return;
  isFireAlertActive = isActive;

  if (isFireAlertActive) {
    // Show Alert Overlay & Persistent Warning Strip
    fireOverlay.classList.remove('hidden');
    fireStrip.classList.remove('hidden');
    firePill.className = 'pill hazard';
    fireStatusText.textContent = 'FIRE DETECTED!';
    stateVal.textContent = 'STOPPED (FIRE DETECTED)';
    stateVal.className = 'metric-val state-stop';

    // Start siren & vibration
    startSiren();
    if (navigator.vibrate) {
      navigator.vibrate([400, 200, 400, 200, 600]);
    }
  } else {
    // Dismiss Alert
    fireOverlay.classList.add('hidden');
    fireStrip.classList.add('hidden');
    firePill.className = 'pill safe';
    fireStatusText.textContent = 'NO FIRE';
    stopSiren();
  }
}

function startSiren() {
  if (isAudioMuted || sirenInterval) return;

  try {
    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContext.state === 'suspended') {
      audioContext.resume();
    }

    let toggleFreq = false;
    const playTone = () => {
      if (isAudioMuted || !isFireAlertActive) return;
      const osc = audioContext.createOscillator();
      const gain = audioContext.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(toggleFreq ? 950 : 650, audioContext.currentTime);
      gain.gain.setValueAtTime(0.18, audioContext.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.35);

      osc.connect(gain);
      gain.connect(audioContext.destination);

      osc.start();
      osc.stop(audioContext.currentTime + 0.35);
      toggleFreq = !toggleFreq;
    };

    playTone();
    sirenInterval = setInterval(playTone, 400);
  } catch (e) {
    console.warn('AudioContext autoplay policy prevented siren:', e);
  }
}

function stopSiren() {
  if (sirenInterval) {
    clearInterval(sirenInterval);
    sirenInterval = null;
  }
}

silenceBtn.addEventListener('click', () => {
  isAudioMuted = !isAudioMuted;
  if (isAudioMuted) {
    stopSiren();
    silenceBtn.textContent = 'UNMUTE SOUND';
    silenceBtn.style.background = '#475569';
  } else {
    silenceBtn.textContent = 'MUTE SOUND';
    silenceBtn.style.background = '#dc2626';
    if (isFireAlertActive) startSiren();
  }
});

dismissBtn?.addEventListener('click', () => {
  // Hide fullscreen modal so operator can see joystick & steer robot away,
  // while keeping top fire-strip and hazard pill active
  fireOverlay.classList.add('hidden');
});

// ==========================================================================
// 4. COMMAND TRANSMITTER
// ==========================================================================
function sendCommand(cmd) {
  // Commands are always transmitted to RPi/ESP32, allowing the operator
  // to steer away or stop the robot even when fire is detected!
  if (currentCommand === cmd) return;
  currentCommand = cmd;

  // Send via WebSocket for ultra-low latency
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ cmd: cmd }));
  } else {
    // Fallback to REST API if WS dropped
    fetch(`/api/command/${cmd}`, { method: 'POST' }).catch(() => {});
  }
}

// ==========================================================================
// 5. VIRTUAL JOYSTICK (TOUCH / MOUSE)
// ==========================================================================
let isDragging = false;
let joyCenter = { x: 0, y: 0 };

function calculateJoystickCommand(dx, dy) {
  const dist = Math.hypot(dx, dy);
  if (dist < DEADZONE) {
    return 'S';
  }

  // Angle in degrees (-180 to 180)
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;

  // Up/Front: -135 to -45
  if (angle >= -135 && angle <= -45) {
    return 'F';
  }
  // Down/Back: 45 to 135
  if (angle >= 45 && angle <= 135) {
    return 'B';
  }
  // Left: > 135 or < -135
  if (angle > 135 || angle < -135) {
    return 'L';
  }
  // Right: -45 to 45
  return 'R';
}

function onJoystickPointerDown(e) {
  isDragging = true;
  const rect = joystickZone.getBoundingClientRect();
  joyCenter = {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2
  };
  onJoystickPointerMove(e);
}

function onJoystickPointerMove(e) {
  if (!isDragging) return;

  const clientX = e.clientX || (e.touches && e.touches[0].clientX);
  const clientY = e.clientY || (e.touches && e.touches[0].clientY);

  let dx = clientX - joyCenter.x;
  let dy = clientY - joyCenter.y;
  const dist = Math.hypot(dx, dy);

  // Clamp handle inside circle
  if (dist > MAX_RADIUS) {
    const angle = Math.atan2(dy, dx);
    dx = Math.cos(angle) * MAX_RADIUS;
    dy = Math.sin(angle) * MAX_RADIUS;
  }

  joystickKnob.style.transform = `translate(${dx}px, ${dy}px)`;

  const cmd = calculateJoystickCommand(dx, dy);
  sendCommand(cmd);
}

function onJoystickPointerUp() {
  if (!isDragging) return;
  isDragging = false;
  joystickKnob.style.transform = `translate(0px, 0px)`;
  sendCommand('S');
}

joystickZone.addEventListener('pointerdown', onJoystickPointerDown);
window.addEventListener('pointermove', onJoystickPointerMove);
window.addEventListener('pointerup', onJoystickPointerUp);
window.addEventListener('pointercancel', onJoystickPointerUp);

// ==========================================================================
// 6. TACTILE D-PAD BUTTONS
// ==========================================================================
const dpadButtons = document.querySelectorAll('.dpad-btn');

dpadButtons.forEach((btn) => {
  const cmd = btn.getAttribute('data-cmd');

  const startPress = (e) => {
    e.preventDefault();
    btn.classList.add('active');
    sendCommand(cmd);
    if (navigator.vibrate) navigator.vibrate(25);
  };

  const endPress = (e) => {
    e.preventDefault();
    btn.classList.remove('active');
    if (cmd !== 'S') {
      sendCommand('S');
    }
  };

  btn.addEventListener('pointerdown', startPress);
  btn.addEventListener('pointerup', endPress);
  btn.addEventListener('pointerleave', endPress);
  btn.addEventListener('pointercancel', endPress);
});

// ==========================================================================
// 7. KEYBOARD CONTROLS (WASD / ARROW KEYS)
// ==========================================================================
const keyMap = {
  ArrowUp: { cmd: 'F', id: 'btn-up' },
  KeyW: { cmd: 'F', id: 'btn-up' },
  ArrowDown: { cmd: 'B', id: 'btn-down' },
  KeyS: { cmd: 'B', id: 'btn-down' },
  ArrowLeft: { cmd: 'L', id: 'btn-left' },
  KeyA: { cmd: 'L', id: 'btn-left' },
  ArrowRight: { cmd: 'R', id: 'btn-right' },
  KeyD: { cmd: 'R', id: 'btn-right' },
  Space: { cmd: 'S', id: 'btn-stop' }
};

window.addEventListener('keydown', (e) => {
  if (e.repeat) return;
  const match = keyMap[e.code];
  if (match) {
    e.preventDefault();
    document.getElementById(match.id)?.classList.add('active');
    sendCommand(match.cmd);
  }
});

window.addEventListener('keyup', (e) => {
  const match = keyMap[e.code];
  if (match) {
    e.preventDefault();
    document.getElementById(match.id)?.classList.remove('active');
    sendCommand('S');
  }
});

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
  initWebSocket();
});
