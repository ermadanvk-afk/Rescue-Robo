class GestureRecognizer:
    """Optional MediaPipe gesture recognizer. Emits labels; does not control motors."""
    def __init__(self):
        try:
            import mediapipe as mp
            self.mp = mp
            self.hands = mp.solutions.hands.Hands(
                static_image_mode=False, max_num_hands=1,
                min_detection_confidence=0.6, min_tracking_confidence=0.6
            )
            self.drawer = mp.solutions.drawing_utils
        except Exception as exc:
            raise RuntimeError(f"MediaPipe unavailable: {exc}")

    def process(self, frame):
        import cv2
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.hands.process(rgb)
        label = "NO HAND"
        if result.multi_hand_landmarks:
            hand = result.multi_hand_landmarks[0]
            self.drawer.draw_landmarks(frame, hand, self.mp.solutions.hands.HAND_CONNECTIONS)
            # Basic open-palm / fist heuristic from finger-tip vs PIP y positions.
            lm = hand.landmark
            tips = [8, 12, 16, 20]
            pips = [6, 10, 14, 18]
            extended = sum(lm[t].y < lm[p].y for t, p in zip(tips, pips))
            if extended >= 3:
                label = "OPEN PALM"
            elif extended == 0:
                label = "FIST"
            else:
                label = "HAND DETECTED"
        return frame, label

    def close(self):
        self.hands.close()
