import time
import cv2
from picamera2 import Picamera2

class PiCamera:
    def __init__(self, size=(640, 480)):
        self.camera = Picamera2()
        config = self.camera.create_video_configuration(
            main={"size": tuple(size), "format": "RGB888"}
        )
        self.camera.configure(config)
        self.camera.start()
        time.sleep(1.5)

    def read(self):
        # RGB888 from Picamera2; convert to OpenCV's BGR ordering.
        rgb = self.camera.capture_array()
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def close(self):
        self.camera.stop()
