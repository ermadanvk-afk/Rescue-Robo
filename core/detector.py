import cv2
from pathlib import Path

class PersonDetector:
    """YOLO person detector when Ultralytics + weights are available; HOG fallback."""
    def __init__(self, model_path, confidence=0.35):
        self.confidence = confidence
        self.yolo = None
        self.mode = "HOG pedestrian fallback"
        model_path = Path(model_path)
        if model_path.exists():
            try:
                from ultralytics import YOLO
                self.yolo = YOLO(str(model_path))
                self.mode = "YOLO"
            except Exception as exc:
                print(f"YOLO could not load ({exc}); using HOG fallback")
        self.hog = None
        if self.yolo is None:
            self.hog = cv2.HOGDescriptor()
            self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame):
        results = []
        if self.yolo is not None:
            prediction = self.yolo.predict(frame, conf=self.confidence, verbose=False, classes=[0])
            for result in prediction:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    score = float(box.conf[0])
                    results.append({"box": (x1, y1, x2-x1, y2-y1), "confidence": score, "label": "PERSON"})
        else:
            # HOG detects upright pedestrians, not general human poses.
            small = cv2.resize(frame, None, fx=0.75, fy=0.75)
            boxes, weights = self.hog.detectMultiScale(
                small, winStride=(8, 8), padding=(8, 8), scale=1.05
            )
            for (x, y, w, h), weight in zip(boxes, weights):
                scale = 1.0 / 0.75
                results.append({
                    "box": (int(x*scale), int(y*scale), int(w*scale), int(h*scale)),
                    "confidence": float(weight), "label": "PERSON (HOG)"
                })
        return results
