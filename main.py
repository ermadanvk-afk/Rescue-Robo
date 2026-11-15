import cv2
import json
import time
from datetime import datetime

import config
from core.camera import PiCamera
from core.detector import PersonDetector
from core.serial_link import SerialTelemetry
from core.mapping import LocalMapper


def main():
    config.RECORD_DIR.mkdir(parents=True, exist_ok=True)
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    events_path = config.LOG_DIR / "events.jsonl"

    camera = PiCamera(config.CAMERA_SIZE)
    detector = PersonDetector(config.YOLO_MODEL, config.YOLO_CONFIDENCE)
    telemetry_link = SerialTelemetry(config.SERIAL_PORT, config.SERIAL_BAUD)
    mapper = LocalMapper(config.MAP_SIZE, config.MAP_PIXELS_PER_METER)

    gesture = None
    if config.ENABLE_GESTURES:
        from core.gestures import GestureRecognizer
        gesture = GestureRecognizer()

    writer = None
    recording = False
    frame_count = 0
    detections = []
    last_flame_state = 0
    last_gesture = ""

    print("Rescue robot camera started")
    print("Detector mode:", detector.mode)
    print("Keys: R=record toggle | M=save map | Q/Esc=quit")

    try:
        while True:
            frame = camera.read()
            if config.CAMERA_FLIP:
                frame = cv2.flip(frame, 1)
            frame_count += 1

            telemetry = telemetry_link.get_latest()
            mapper.update(telemetry)

            if frame_count % config.DETECTION_EVERY_N_FRAMES == 0:
                detections = detector.detect(frame)

            for det in detections:
                x, y, w, h = det["box"]
                cv2.rectangle(frame, (x,y), (x+w,y+h), (0,255,0), 2)
                label = f"{det['label']} {det['confidence']:.2f}"
                cv2.putText(frame, label, (x, max(20,y-8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,0), 2)

            # Associate human event with current robot pose (not exact person coordinates).
            if detections and frame_count % 30 == 0:
                mapper.add_event("person")
                event = {"timestamp": datetime.now().isoformat(), "event": "person_detected",
                         "count": len(detections), "robot_pose": {"x_m": mapper.x, "y_m": mapper.y,
                         "heading_deg": round(mapper.theta*180/3.14159265, 1)}}
                with events_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")

            flame = int(telemetry.get("flame", 0) or 0)
            if flame and not last_flame_state:
                print("!!! FIRE/FLAME SENSOR ALERT !!!")
                event = {"timestamp": datetime.now().isoformat(), "event": "flame_alert",
                         "robot_pose": {"x_m": mapper.x, "y_m": mapper.y}}
                with events_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")
            last_flame_state = flame

            cv2.putText(frame, f"People: {len(detections)} | Detector: {detector.mode}", (10,25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 1)
            cv2.putText(frame, f"Robot pose: x={mapper.x:.2f}m y={mapper.y:.2f}m", (10,48),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
            if "ultrasonic_cm" in telemetry:
                cv2.putText(frame, f"Ultrasonic: {telemetry['ultrasonic_cm']} cm", (10,71),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
            if flame:
                cv2.putText(frame, "FIRE ALERT", (10,105), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,0,255), 3)

            if gesture is not None:
                frame, last_gesture = gesture.process(frame)
                cv2.putText(frame, f"Gesture: {last_gesture}", (10,130), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (255,200,0), 2)

            if recording:
                cv2.circle(frame, (frame.shape[1]-25,25), 8, (0,0,255), -1)
                cv2.putText(frame, "REC", (frame.shape[1]-75,30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)
                writer.write(frame)

            if config.DISPLAY_WINDOW:
                cv2.imshow("AI Search & Rescue Robot - Live Camera", frame)
                cv2.imshow("Local Exploration Map (approx.)", mapper.snapshot())
                key = cv2.waitKey(1) & 0xFF
            else:
                key = 255

            if key == ord('r'):
                if not recording:
                    path = config.RECORD_DIR / f"rescue_{datetime.now().strftime('%Y%m%d_%H%M%S')}.avi"
                    fourcc = cv2.VideoWriter_fourcc(*"XVID")
                    writer = cv2.VideoWriter(str(path), fourcc, 20.0, config.CAMERA_SIZE)
                    if writer.isOpened():
                        recording = True
                        print("Recording:", path)
                    else:
                        writer.release(); writer = None
                        print("Could not open video writer")
                else:
                    recording = False
                    writer.release(); writer = None
                    print("Recording saved")
            elif key == ord('m'):
                path = config.RECORD_DIR / f"map_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                cv2.imwrite(str(path), mapper.snapshot())
                print("Map saved:", path)
            elif key in (ord('q'), 27):
                break

    except KeyboardInterrupt:
        pass
    finally:
        if writer is not None:
            writer.release()
        if gesture is not None:
            gesture.close()
        telemetry_link.close()
        camera.close()
        cv2.destroyAllWindows()
        print("Application stopped safely")

if __name__ == "__main__":
    main()
