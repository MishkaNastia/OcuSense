"""OcuSense: live webcam blink counter.

Run with:  python main.py
Press Q in the video window to quit.

Privacy: every frame is analysed in memory on this computer and then
thrown away. Nothing is saved to disk and nothing is uploaded.
"""

import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from blink_counter import BlinkCounter

MODEL_PATH = Path(__file__).parent / "models" / "face_landmarker.task"
CAMERA_INDEX = 0  # 0 = the laptop's built-in webcam
WINDOW_NAME = "OcuSense - press Q to quit"

GREEN = (0, 200, 0)
RED = (0, 0, 255)
WHITE = (255, 255, 255)


def create_landmarker():
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        # Blendshapes include "eyeBlinkLeft" and "eyeBlinkRight" scores.
        output_face_blendshapes=True,
    )
    return vision.FaceLandmarker.create_from_options(options)


def get_eye_closed_score(result):
    """Return how closed the eyes are (0 = open, 1 = closed), or None if no face."""
    if not result.face_blendshapes:
        return None
    scores = {b.category_name: b.score for b in result.face_blendshapes[0]}
    return (scores["eyeBlinkLeft"] + scores["eyeBlinkRight"]) / 2


def draw_text(frame, text, y, color):
    # Black outline first, then the coloured text, so it's readable on any background.
    cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)


def main():
    if not MODEL_PATH.exists():
        print(f"Model file not found: {MODEL_PATH}")
        print("Run this first:  python download_model.py")
        return 1

    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        print("Could not open the webcam.")
        print("On a Mac: System Settings > Privacy & Security > Camera,")
        print("allow your Terminal app, then quit and reopen Terminal.")
        return 1

    counter = BlinkCounter()
    landmarker = create_landmarker()
    start = time.monotonic()
    last_timestamp_ms = -1

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("Could not read a frame from the webcam.")
                break

            # Mirror the image so it behaves like a mirror.
            frame = cv2.flip(frame, 1)

            # MediaPipe expects RGB colours; OpenCV gives BGR.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # VIDEO mode needs a timestamp that always increases.
            timestamp_ms = max(int((time.monotonic() - start) * 1000), last_timestamp_ms + 1)
            last_timestamp_ms = timestamp_ms
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            score = get_eye_closed_score(result)
            counter.update(score)

            draw_text(frame, f"Blinks: {counter.count}", 35, WHITE)
            if score is None:
                draw_text(frame, "Face: NOT tracked", 70, RED)
            else:
                draw_text(frame, "Face: tracked", 70, GREEN)
                draw_text(frame, f"Eyes: {counter.state}  (closed score {score:.2f})", 105, WHITE)

            cv2.imshow(WINDOW_NAME, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                break
    finally:
        # Always give the webcam back, even if something went wrong.
        landmarker.close()
        camera.release()
        cv2.destroyAllWindows()
        cv2.waitKey(1)  # lets macOS actually close the window

    print(f"Total blinks: {counter.count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
