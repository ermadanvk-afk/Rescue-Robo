import cv2
import json
import time
from datetime import datetime
from pathlib import Path

import config
from core.camera import PiCamera
from core.detector import PersonDetector
from core.serial_link import SerialTelemetry
from core.navigator import AutonomousNavigator
from core.mapping import LocalMapper
from core.event_manager import EventManager
from core.cloud_client import CloudClient


def main():
    print("==================================================")
    print("   AI SEARCH & RESCUE ROBOT - RASPBERRY PI 5      ")
    print("==================================================")

    # 1. Initialize Core Subsystems
    camera = PiCamera(config.CAMERA_SIZE, backend=config.CAMERA_BACKEND)
    detector = PersonDetector(
        config.YOLO_MODEL,
        confidence=config.YOLO_CONFIDENCE,
        target_classes=config.TARGET_CLASSES
    )
    serial_link = SerialTelemetry(
        port=config.SERIAL_PORT,
        baud=config.SERIAL_BAUD,
        timeout=config.SERIAL_TIMEOUT
    )
    mapper = LocalMapper(config.MAP_SIZE, config.MAP_PIXELS_PER_METER)
    navigator = AutonomousNavigator(
        serial_link,
        obstacle_threshold=config.OBSTACLE_DISTANCE_THRESHOLD,
        critical_threshold=config.CRITICAL_STOP_DISTANCE
    )
    event_mgr = EventManager(
        log_dir=config.LOG_DIR,
        alert_dir=config.ALERT_DIR,
        debounce_sec=config.CLOUD_ALERT_DEBOUNCE_SEC
    )
    cloud = CloudClient(
        server_url=config.CLOUD_SERVER_URL,
        api_key=config.CLOUD_API_KEY,
        navigator=navigator,
        enabled=config.CLOUD_ENABLED
    )

    gesture = None
    if config.ENABLE_GESTURES:
        try:
            from core.gestures import GestureRecognizer
            gesture = GestureRecognizer()
            print("[Gestures] Gesture recognizer enabled.")
        except Exception as exc:
            print(f"[Gestures] Could not initialize gestures: {exc}")

    writer = None
    recording = False
    frame_count = 0
    detections = []
    last_flame_val = 0

    print(f"[Main] Detector Mode: {detector.mode}")
    print("[Main] Hotkeys (in GUI window):")
    print("   [Space] : Toggle AUTONOMOUS SEARCH / MANUAL OVERRIDE")
    print("   [R]     : Start/Stop Video Recording")
    print("   [M]     : Save Map Snapshot")
    print("   [W/A/S/D]: Manual Drive (when in MANUAL mode)")
    print("   [Q/Esc] : Quit cleanly")
    print("==================================================\n")

    try:
        while True:
            # 1. Capture Camera Frame
            frame = camera.read()
            if config.CAMERA_FLIP and frame is not None:
                frame = cv2.flip(frame, 1)
            frame_count += 1

            # 2. Ingest Latest ESP32 Sensor Telemetry
            telemetry = serial_link.get_latest()
            mapper.update(telemetry)

            # 3. Vision Detection (Skipping frames to save CPU cycles)
            if frame_count % config.DETECTION_EVERY_N_FRAMES == 0:
                detections = detector.detect(frame)

            # 4. Autonomous Navigation Step
            nav_state = navigator.update(telemetry, detections, frame_size=config.CAMERA_SIZE)

            # 5. Event Handling & Debouncing
            if detections:
                alert_evt = event_mgr.handle_detection(detections, frame, telemetry, mapper=mapper)
                if alert_evt:
                    cloud.queue_event(alert_evt)

            current_flame = int(telemetry.get("flame", 0) or 0)
            if current_flame == 1 and last_flame_val == 0:
                flame_evt = event_mgr.handle_flame_alert(telemetry, mapper=mapper)
                if flame_evt:
                    cloud.queue_event(flame_evt)
            last_flame_val = current_flame

            # 6. Stream to Remote Cloud Server
            cloud.update_telemetry(telemetry, mapper=mapper)
            cloud.update_frame(frame)

            # 7. Render On-Screen Display (HUD)
            if frame is not None and cv2 is not None:
                # Draw vision bounding boxes
                for det in detections:
                    x, y, w, h = det["box"]
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    lbl = f"{det['label']} {det['confidence']:.2f}"
                    cv2.putText(frame, lbl, (x, max(20, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

                # Draw Status Banners
                mode_str = f"MODE: {nav_state}"
                mode_color = (0, 255, 0) if "SEARCH" in nav_state else (0, 165, 255)
                cv2.putText(frame, mode_str, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, mode_color, 2)

                cv2.putText(frame, f"Yaw: {float(telemetry.get('yaw', 0.0)):.1f} deg | MPU6050", (10, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                ultrasonic_val = telemetry.get("ultrasonic_cm")
                if ultrasonic_val is not None:
                    u_col = (0, 0, 255) if float(ultrasonic_val) < config.OBSTACLE_DISTANCE_THRESHOLD else (255, 255, 255)
                    cv2.putText(frame, f"Ultrasonic: {float(ultrasonic_val):.1f} cm", (10, 72),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, u_col, 1)

                if current_flame:
                    cv2.putText(frame, "!!! FIRE HAZARD DETECTED !!!", (10, 110),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 3)

                # Cloud connection indicator
                cloud_col = (0, 255, 0) if cloud.is_connected else (100, 100, 100)
                cv2.circle(frame, (frame.shape[1] - 20, 20), 7, cloud_col, -1)
                cv2.putText(frame, "CLOUD", (frame.shape[1] - 80, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, cloud_col, 1)

                # Recording Indicator
                if recording:
                    cv2.circle(frame, (frame.shape[1] - 20, 45), 7, (0, 0, 255), -1)
                    cv2.putText(frame, "REC", (frame.shape[1] - 65, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
                    if writer:
                        writer.write(frame)

            # 8. Window Display and Keyboard Controls
            key = 255
            if config.DISPLAY_WINDOW and frame is not None and cv2 is not None:
                cv2.imshow("Rescue Robot - Live View", frame)
                cv2.imshow("Rescue Robot - 2D Map", mapper.snapshot())
                key = cv2.waitKey(1) & 0xFF

            # Keybindings
            if key == ord(' '):  # Toggle Mode
                new_mode = "MANUAL" if not navigator.manual_override else "AUTO"
                navigator.set_mode(new_mode)
            elif key == ord('r'):  # Video recording toggle
                if not recording:
                    rec_path = config.RECORD_DIR / f"rescue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.avi"
                    fourcc = cv2.VideoWriter_fourcc(*"XVID")
                    writer = cv2.VideoWriter(str(rec_path), fourcc, 20.0, config.CAMERA_SIZE)
                    if writer.isOpened():
                        recording = True
                        print(f"[Main] Started recording to: {rec_path}")
                else:
                    recording = False
                    if writer:
                        writer.release()
                        writer = None
                    print("[Main] Recording stopped.")
            elif key == ord('m'):  # Snapshot map
                map_path = config.RECORD_DIR / f"map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                cv2.imwrite(str(map_path), mapper.snapshot())
                print(f"[Main] Saved map snapshot: {map_path}")
            elif key in (ord('w'), ord('W')):
                navigator.manual_drive("FORWARD")
            elif key in (ord('s'), ord('S')):
                navigator.manual_drive("BACKWARD")
            elif key in (ord('a'), ord('A')):
                navigator.manual_drive("LEFT")
            elif key in (ord('d'), ord('D')):
                navigator.manual_drive("RIGHT")
            elif key == ord('x'):
                navigator.manual_drive("STOP")
            elif key in (ord('q'), 27):  # Q or Escape to quit
                break

    except KeyboardInterrupt:
        print("\n[Main] Received KeyboardInterrupt; shutting down gracefully...")
    finally:
        if writer:
            writer.release()
        cloud.close()
        navigator.manual_drive("STOP")
        serial_link.close()
        camera.close()
        if cv2 is not None:
            cv2.destroyAllWindows()
        print("[Main] Rescue robot application exited safely.")


if __name__ == "__main__":
    main()
