import unittest
import numpy as np
import config
from core.detector import PersonDetector


class TestDetector(unittest.TestCase):
    def test_detector_initialization(self):
        detector = PersonDetector(config.YOLO_MODEL, confidence=0.35)
        # Should initialize in opencv_dnn, onnxruntime, or hog
        self.assertIsNotNone(detector.backend)
        self.assertIn(detector.backend, ["opencv_dnn", "onnxruntime", "ultralytics", "hog", "dummy"])

    def test_detector_empty_frame(self):
        detector = PersonDetector(config.YOLO_MODEL, confidence=0.35)
        res = detector.detect(None)
        self.assertEqual(res, [])

    def test_detector_synthetic_frame(self):
        detector = PersonDetector(config.YOLO_MODEL, confidence=0.35)
        # 640x480 black image
        synthetic_img = np.zeros((480, 640, 3), dtype=np.uint8)
        res = detector.detect(synthetic_img)
        self.assertIsInstance(res, list)


if __name__ == "__main__":
    unittest.main()
