import time
from pathlib import Path

try:
    import cv2
except ImportError:
    cv2 = None


class PersonDetector:
    """Multi-backend detector supporting:
    1. Ultralytics YOLO (PyTorch .pt weights, e.g. yolo11n.pt, yolov8n.pt, or custom fine-tuned weights)
    2. ONNX Runtime (.onnx export for ultra-fast Pi CPU inference)
    3. OpenCV HOG pedestrian detector (lightweight baseline fallback)
    """

    def __init__(self, model_path=None, confidence=0.35, target_classes=(0,)):
        self.confidence = float(confidence)
        self.target_classes = list(target_classes) if target_classes is not None else None
        self.mode = "HOG pedestrian fallback"
        self.model = None
        self.backend = "hog"

        model_path = Path(model_path) if model_path else None

        # 1. Try Ultralytics YOLO if model_path exists or if model is a recognized YOLO name
        if model_path and (model_path.exists() or model_path.suffix in (".pt", ".onnx")):
            try:
                from ultralytics import YOLO
                self.model = YOLO(str(model_path))
                self.backend = "yolo"
                self.mode = f"YOLO ({model_path.name})"
                print(f"[Detector] Loaded YOLO model from {model_path}")
            except Exception as exc:
                print(f"[Detector] Failed to load YOLO ({exc}); falling back...")

        # 2. If no model found, attempt to load default yolo11n / yolov8n via Ultralytics auto-download
        if self.model is None:
            try:
                from ultralytics import YOLO
                print("[Detector] Attempting to initialize default YOLO11n weights...")
                self.model = YOLO("yolo11n.pt")
                self.backend = "yolo"
                self.mode = "YOLO (yolo11n auto-weights)"
                print("[Detector] Successfully loaded YOLO11n")
            except Exception as exc:
                print(f"[Detector] Auto YOLO download not available ({exc})")

        # 3. Fallback: OpenCV HOG Pedestrian Detector
        if self.model is None and cv2 is not None:
            try:
                self.hog = cv2.HOGDescriptor()
                self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
                self.backend = "hog"
                self.mode = "OpenCV HOG Pedestrian"
                print("[Detector] Initialized OpenCV HOG pedestrian detector")
            except Exception as exc:
                print(f"[Detector] OpenCV HOG initialization failed ({exc})")
                self.backend = "dummy"
                self.mode = "Dummy (No-op)"

    def detect(self, frame):
        """Runs detection on frame and returns structured list:
        [
            {
                "box": (x, y, w, h),
                "confidence": 0.89,
                "label": "person",
                "center": (cx, cy)
            },
            ...
        ]
        """
        if frame is None:
            return []

        results = []

        if self.backend == "yolo" and self.model is not None:
            try:
                predict_args = {
                    "source": frame,
                    "conf": self.confidence,
                    "verbose": False
                }
                if self.target_classes is not None:
                    predict_args["classes"] = self.target_classes

                preds = self.model.predict(**predict_args)
                for pred in preds:
                    if pred.boxes is None:
                        continue
                    names = getattr(pred, "names", {})
                    for box in pred.boxes:
                        coords = box.xyxy[0].tolist()
                        x1, y1, x2, y2 = map(int, coords)
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        cls_name = names.get(cls_id, f"class_{cls_id}")

                        w = max(0, x2 - x1)
                        h = max(0, y2 - y1)
                        cx = x1 + w // 2
                        cy = y1 + h // 2

                        results.append({
                            "box": (x1, y1, w, h),
                            "confidence": round(conf, 3),
                            "label": cls_name,
                            "class_id": cls_id,
                            "center": (cx, cy)
                        })
                return results
            except Exception as exc:
                print(f"[Detector] YOLO inference error: {exc}")
                return []

        elif self.backend == "hog" and hasattr(self, "hog") and cv2 is not None:
            try:
                # Resize for faster HOG processing
                small = cv2.resize(frame, None, fx=0.75, fy=0.75)
                boxes, weights = self.hog.detectMultiScale(
                    small, winStride=(8, 8), padding=(8, 8), scale=1.05
                )
                scale = 1.0 / 0.75
                for (x, y, w, h), weight in zip(boxes, weights):
                    bx = int(x * scale)
                    by = int(y * scale)
                    bw = int(w * scale)
                    bh = int(h * scale)
                    cx = bx + bw // 2
                    cy = by + bh // 2
                    results.append({
                        "box": (bx, by, bw, bh),
                        "confidence": round(float(weight), 2),
                        "label": "person",
                        "class_id": 0,
                        "center": (cx, cy)
                    })
                return results
            except Exception as exc:
                print(f"[Detector] HOG detection error: {exc}")
                return []

        return []
