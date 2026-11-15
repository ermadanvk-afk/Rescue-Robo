import time
from pathlib import Path
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


# COCO Class 0 is 'person'
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush"
]


class PersonDetector:
    """Zero-Torch Lightweight Edge Detector for Raspberry Pi.

    Inference Backends (in priority order):
    1. OpenCV DNN Engine (ONNX model, e.g. yolov8n.onnx) -> Ultra-fast C++ on ARM CPU, 0% torch dependency!
    2. ONNX Runtime (onnxruntime engine) -> Pure C++ inference without PyTorch.
    3. Ultralytics YOLO (PyTorch .pt) -> Only if ultralytics is already installed (e.g. desktop/workstation).
    4. OpenCV HOG Pedestrian -> Built-in legacy fallback.
    """

    def __init__(self, model_path=None, confidence=0.35, target_classes=(0,)):
        self.confidence = float(confidence)
        self.target_classes = list(target_classes) if target_classes is not None else [0]
        self.mode = "HOG pedestrian fallback"
        self.backend = None
        self.net = None
        self.ort_session = None
        self.yolo_model = None
        self.input_size = (640, 640)

        model_path = Path(model_path) if model_path else None
        candidate_models = []

        if model_path:
            candidate_models.append(model_path)

        # Check default models in models/ directory (prefer ONNX for edge Pi)
        base_dir = Path(__file__).resolve().parent.parent / "models"
        candidate_models.extend([
            base_dir / "yolov8n.onnx",
            base_dir / "yolo11n.onnx",
            base_dir / "yolo11n.pt",
            base_dir / "yolov8n.pt"
        ])

        # Find first existing model file
        chosen_path = None
        for cand in candidate_models:
            if cand and cand.exists():
                chosen_path = cand
                break

        # -------------------------------------------------------------
        # 1. Try OpenCV DNN with ONNX (Recommended for Raspberry Pi)
        # -------------------------------------------------------------
        if chosen_path and chosen_path.suffix.lower() == ".onnx" and cv2 is not None:
            try:
                self.net = cv2.dnn.readNetFromONNX(str(chosen_path))
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                self.backend = "opencv_dnn"
                self.mode = f"OpenCV DNN ({chosen_path.name}) [Zero-Torch]"
                print(f"[Detector] Initialized OpenCV DNN engine with {chosen_path.name} (Zero PyTorch needed)")
            except Exception as exc:
                print(f"[Detector] OpenCV DNN failed to load ONNX ({exc})")

        # -------------------------------------------------------------
        # 2. Try ONNX Runtime (if installed and OpenCV DNN not used)
        # -------------------------------------------------------------
        if self.backend is None and chosen_path and chosen_path.suffix.lower() == ".onnx":
            try:
                import onnxruntime as ort
                self.ort_session = ort.InferenceSession(str(chosen_path), providers=["CPUExecutionProvider"])
                # Dynamically inspect model input dimensions
                in_shape = self.ort_session.get_inputs()[0].shape
                if len(in_shape) == 4:
                    h = in_shape[2] if isinstance(in_shape[2], int) and in_shape[2] > 0 else 640
                    w = in_shape[3] if isinstance(in_shape[3], int) and in_shape[3] > 0 else 640
                    self.input_size = (w, h)
                self.backend = "onnxruntime"
                self.mode = f"ONNXRuntime ({chosen_path.name}) [Zero-Torch]"
                print(f"[Detector] Initialized ONNX Runtime with {chosen_path.name} (input size: {self.input_size})")
            except Exception:
                pass

        # -------------------------------------------------------------
        # 3. Try Ultralytics (Only if installed on workstation with PyTorch)
        # -------------------------------------------------------------
        if self.backend is None and chosen_path and chosen_path.suffix.lower() == ".pt":
            try:
                from ultralytics import YOLO
                self.yolo_model = YOLO(str(chosen_path))
                self.backend = "ultralytics"
                self.mode = f"Ultralytics ({chosen_path.name})"
                print(f"[Detector] Loaded PyTorch model via Ultralytics ({chosen_path.name})")
            except Exception:
                pass

        # -------------------------------------------------------------
        # 4. Fallback: OpenCV HOG Pedestrian Detector
        # -------------------------------------------------------------
        if self.backend is None and cv2 is not None:
            try:
                self.hog = cv2.HOGDescriptor()
                self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
                self.backend = "hog"
                self.mode = "OpenCV HOG Pedestrian Detector"
                print("[Detector] Fallback: Initialized OpenCV HOG pedestrian detector")
            except Exception as exc:
                self.backend = "dummy"
                self.mode = "Dummy (No-op)"

    def detect(self, frame):
        """Runs inference and returns detections:
        [
            {
                "box": (x, y, w, h),
                "confidence": 0.89,
                "label": "person",
                "class_id": 0,
                "center": (cx, cy)
            }
        ]
        """
        if frame is None:
            return []

        h_orig, w_orig = frame.shape[:2]

        # 1. OpenCV DNN (Native ONNX)
        if self.backend == "opencv_dnn" and self.net is not None:
            return self._detect_opencv_dnn(frame, w_orig, h_orig)

        # 2. ONNX Runtime
        elif self.backend == "onnxruntime" and self.ort_session is not None:
            return self._detect_onnxruntime(frame, w_orig, h_orig)

        # 3. Ultralytics YOLO
        elif self.backend == "ultralytics" and self.yolo_model is not None:
            return self._detect_ultralytics(frame)

        # 4. OpenCV HOG Fallback
        elif self.backend == "hog" and hasattr(self, "hog") and cv2 is not None:
            return self._detect_hog(frame)

        return []

    def _detect_opencv_dnn(self, frame, w_orig, h_orig):
        """Zero-Torch fast YOLO post-processing via OpenCV DNN."""
        try:
            blob = cv2.dnn.blobFromImage(frame, 1.0 / 255.0, self.input_size, swapRB=True, crop=False)
            self.net.setInput(blob)
            outputs = self.net.forward()

            return self._parse_yolo_outputs(outputs, w_orig, h_orig)
        except Exception as exc:
            print(f"[Detector] OpenCV DNN error: {exc}")
            return []

    def _detect_onnxruntime(self, frame, w_orig, h_orig):
        """ONNX Runtime post-processing."""
        try:
            if cv2 is not None:
                img = cv2.resize(frame, self.input_size)
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            else:
                from PIL import Image
                img = np.array(Image.fromarray(frame).resize(self.input_size).convert("RGB"))

            img = img.astype(np.float32) / 255.0
            blob = np.transpose(img, (2, 0, 1))[np.newaxis, ...]

            input_name = self.ort_session.get_inputs()[0].name
            outputs = self.ort_session.run(None, {input_name: blob})[0]

            return self._parse_yolo_outputs(outputs, w_orig, h_orig)
        except Exception as exc:
            print(f"[Detector] ONNXRuntime error: {exc}")
            return []

    def _parse_yolo_outputs(self, outputs, w_orig, h_orig):
        """Parses YOLOv8 / YOLO11 tensor format: (1, 84, 8400) -> [cx, cy, w, h, class_scores...]."""
        outputs = np.squeeze(outputs)
        if outputs.ndim == 2 and outputs.shape[0] < outputs.shape[1]:
            outputs = outputs.T  # Transpose to (8400, 84)

        if outputs.ndim != 2 or outputs.shape[1] < 5:
            return []

        boxes = []
        confidences = []
        class_ids = []

        x_factor = w_orig / float(self.input_size[0])
        y_factor = h_orig / float(self.input_size[1])

        # Vectorized extraction
        scores_matrix = outputs[:, 4:]
        max_cls_ids = np.argmax(scores_matrix, axis=1)
        max_scores = scores_matrix[np.arange(len(scores_matrix)), max_cls_ids]

        # Filter by confidence and target classes
        mask = max_scores >= self.confidence
        if self.target_classes is not None:
            mask = mask & np.isin(max_cls_ids, self.target_classes)

        filtered_boxes = outputs[mask, :4]
        filtered_scores = max_scores[mask]
        filtered_cls = max_cls_ids[mask]

        for (cx, cy, bw, bh), score, cid in zip(filtered_boxes, filtered_scores, filtered_cls):
            bx = int((cx - bw / 2.0) * x_factor)
            by = int((cy - bh / 2.0) * y_factor)
            box_w = int(bw * x_factor)
            box_h = int(bh * y_factor)

            boxes.append([bx, by, box_w, box_h])
            confidences.append(float(score))
            class_ids.append(int(cid))

        if not boxes:
            return []

        # Apply Non-Maximum Suppression
        if cv2 is not None:
            indices = cv2.dnn.NMSBoxes(boxes, confidences, self.confidence, nms_threshold=0.45)
            if hasattr(indices, "flatten"):
                valid_indices = indices.flatten().tolist()
            else:
                valid_indices = list(indices)
        else:
            # Simple confidence sorting if OpenCV is not installed
            valid_indices = sorted(range(len(confidences)), key=lambda k: confidences[k], reverse=True)[:10]

        results = []
        for i in valid_indices:
            bx, by, bw, bh = boxes[i]
            cid = class_ids[i]
            lbl = COCO_CLASSES[cid] if cid < len(COCO_CLASSES) else f"class_{cid}"
            results.append({
                "box": (bx, by, bw, bh),
                "confidence": round(confidences[i], 3),
                "label": lbl,
                "class_id": cid,
                "center": (bx + bw // 2, by + bh // 2)
            })

        return results

    def _detect_ultralytics(self, frame):
        """Fallback for desktop using PyTorch."""
        results = []
        try:
            preds = self.yolo_model.predict(
                source=frame,
                conf=self.confidence,
                classes=self.target_classes,
                verbose=False
            )
            for pred in preds:
                if pred.boxes is None:
                    continue
                names = getattr(pred, "names", {})
                for box in pred.boxes:
                    coords = box.xyxy[0].tolist()
                    x1, y1, x2, y2 = map(int, coords)
                    conf = float(box.conf[0])
                    cid = int(box.cls[0])
                    lbl = names.get(cid, COCO_CLASSES[cid] if cid < len(COCO_CLASSES) else "person")
                    w = max(0, x2 - x1)
                    h = max(0, y2 - y1)
                    results.append({
                        "box": (x1, y1, w, h),
                        "confidence": round(conf, 3),
                        "label": lbl,
                        "class_id": cid,
                        "center": (x1 + w // 2, y1 + h // 2)
                    })
        except Exception as exc:
            print(f"[Detector] Ultralytics error: {exc}")
        return results

    def _detect_hog(self, frame):
        """OpenCV HOG pedestrian detector."""
        results = []
        try:
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
                results.append({
                    "box": (bx, by, bw, bh),
                    "confidence": round(float(weight), 2),
                    "label": "person",
                    "class_id": 0,
                    "center": (bx + bw // 2, by + bh // 2)
                })
        except Exception:
            pass
        return results
