"""OcuSense: live webcam blink counter using the Eye Aspect Ratio (EAR).

Run with:  python main.py
Keys (click the video window first):
  SPACE or C  start / redo personal calibration
  M           show / hide the face mesh
  Q           quit

Privacy: every frame is analysed in memory on this computer and then
thrown away. Nothing is saved to disk and nothing is uploaded.
"""

import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from blink_counter import CLOSE_BELOW, REOPEN_ABOVE, BlinkCounter
from calibration import GuidedCalibration
from eye_metrics import EYE_LANDMARKS, measure_eyes
from score_graph import ScoreHistory, draw_score_graph

MODEL_PATH = Path(__file__).parent / "models" / "face_landmarker.task"
CAMERA_INDEX = 0  # 0 = the laptop's built-in webcam
WINDOW_NAME = "OcuSense - press Q to quit"

GREEN = (0, 200, 0)
RED = (0, 0, 255)
YELLOW = (0, 220, 255)
WHITE = (255, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX

# Which landmark pairs MediaPipe joins to form the mesh.
MESH_CONNECTIONS = vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION
OUTLINE_CONNECTIONS = vision.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS
MESH_COLOR = (170, 170, 170)
OUTLINE_COLOR = (255, 200, 0)


def create_landmarker():
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
    )
    return vision.FaceLandmarker.create_from_options(options)


def draw_text(frame, text, y, color, scale=0.8):
    """Draw text; long text wraps onto extra lines. Returns the next free y."""
    max_width = frame.shape[1] - 20
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and cv2.getTextSize(candidate, FONT, scale, 2)[0][0] > max_width:
            _put(frame, line, y, color, scale)
            y += int(40 * scale)
            line = word
        else:
            line = candidate
    _put(frame, line, y, color, scale)
    return y + int(44 * scale)


def _put(frame, text, y, color, scale):
    # Black outline first, then the coloured text, so it's readable on any background.
    cv2.putText(frame, text, (10, y), FONT, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, text, (10, y), FONT, scale, color, 2, cv2.LINE_AA)


def draw_openness_bar(frame, openness, y, height=18):
    """Horizontal bar for personal eye openness, with the two thresholds marked."""
    x0, width = 10, 300
    cv2.rectangle(frame, (x0, y), (x0 + width, y + height), WHITE, 1)
    cv2.rectangle(frame, (x0, y), (x0 + int(width * openness), y + height), GREEN, -1)
    for threshold, color in ((CLOSE_BELOW, RED), (REOPEN_ABOVE, YELLOW)):
        x = x0 + int(width * threshold)
        cv2.line(frame, (x, y - 4), (x, y + height + 4), color, 2)
    return y + height + 30


def draw_mesh(frame, landmarks):
    """Draw the face mesh, the face/eye/lip outlines and the 12 EAR points."""
    height, width = frame.shape[:2]
    points = [(int(p.x * width), int(p.y * height)) for p in landmarks]
    for connections, color in ((MESH_CONNECTIONS, MESH_COLOR), (OUTLINE_CONNECTIONS, OUTLINE_COLOR)):
        for c in connections:
            cv2.line(frame, points[c.start], points[c.end], color, 1, cv2.LINE_AA)
    for indices in EYE_LANDMARKS.values():
        for i in indices:
            cv2.circle(frame, points[i], 3, RED, -1, cv2.LINE_AA)


def main():
    if not MODEL_PATH.exists():
        print(f"Model file not found: {MODEL_PATH}")
        print("Run this first:  python download_model.py")
        return 1

    camera = cv2.VideoCapture(CAMERA_INDEX)
    if not camera.isOpened():
        print("Could not open the webcam.")
        print("On a Mac: System Settings > Privacy & Security > Camera,")
        print("allow your Terminal (or VS Code), then quit and reopen it.")
        return 1

    counter = BlinkCounter()  # both eyes together (the main count)
    # One extra counter per eye, fed with that eye's own openness. These
    # also count one-eyed winks, which the main count ignores.
    eye_counters = {"left": BlinkCounter(), "right": BlinkCounter()}
    calibrator = GuidedCalibration()
    calibration = None  # PersonalCalibration once calibrated
    show_mesh = True
    history = ScoreHistory()  # last few seconds of openness, for the graph
    landmarker = create_landmarker()
    start = time.monotonic()
    last_timestamp_ms = -1

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("Could not read a frame from the webcam.")
                break
            now = time.monotonic()

            # Mirror the image so it behaves like a mirror.
            frame = cv2.flip(frame, 1)
            height, width = frame.shape[:2]

            # MediaPipe expects RGB colours; OpenCV gives BGR.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # VIDEO mode needs a timestamp that always increases.
            timestamp_ms = max(int((now - start) * 1000), last_timestamp_ms + 1)
            last_timestamp_ms = timestamp_ms
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            measurement = None
            if result.face_landmarks:
                measurement = measure_eyes(result.face_landmarks[0], width, height)
            reliable_ears = measurement.ears if measurement and measurement.reliable else None

            # --- calibration or counting ---
            openness = None  # (left, right, both) once measuring
            if calibrator.status == GuidedCalibration.RUNNING:
                step_before = calibrator.step.name
                calibrator.update(now, reliable_ears)
                if calibrator.step is None or calibrator.step.name != step_before:
                    if step_before == "closed":
                        print("\a", end="", flush=True)  # beep: you can open your eyes
                if calibrator.status == GuidedCalibration.DONE:
                    calibration = calibrator.result
                    print("Calibration complete. Your EAR references:")
                    for eye in ("left", "right"):
                        ref = getattr(calibration, eye)
                        print(f"  {eye:>5} eye: open {ref.open_ear:.3f}, closed {ref.closed_ear:.3f}")
                elif calibrator.status == GuidedCalibration.FAILED:
                    print(f"Calibration failed: {calibrator.error}")
            elif calibration is not None and reliable_ears is not None:
                openness = calibration.openness(reliable_ears)

            # None = calibrating or paused: resets any half-finished blink.
            blinked = counter.update(openness[2] if openness else None)
            if calibration is not None:
                history.add(now, openness, blinked)
            eye_counters["left"].update(openness[0] if openness else None)
            eye_counters["right"].update(openness[1] if openness else None)

            # --- drawing ---
            if show_mesh and result.face_landmarks:
                draw_mesh(frame, result.face_landmarks[0])
            y = draw_text(frame, f"Blinks: {counter.count}", 35, WHITE)
            if measurement is None:
                y = draw_text(frame, "Face: NOT tracked", y, RED)
            elif not measurement.reliable:
                y = draw_text(frame, f"Face: tracked - measurement paused ({measurement.reason})", y, YELLOW)
            else:
                y = draw_text(frame, "Face: tracked", y, GREEN)

            if calibrator.status == GuidedCalibration.RUNNING:
                step = calibrator.step
                phase = "now" if calibrator.measuring(now) else "get ready"
                y = draw_text(frame, f"CALIBRATION ({phase}, {calibrator.seconds_left(now):.0f}s): "
                                     f"{step.instruction}", y, YELLOW)
            elif calibrator.status == GuidedCalibration.FAILED:
                y = draw_text(frame, f"Calibration failed: {calibrator.error}", y, RED, 0.6)
                y = draw_text(frame, "Press C to try again", y, YELLOW)
            elif calibration is None:
                y = draw_text(frame, "Press SPACE to calibrate (about 30 seconds)", y, YELLOW)
            elif openness is not None:
                y = draw_text(frame, f"Personal eye openness (both): {openness[2]:.2f} "
                                     f"| eyes: {counter.state}", y, WHITE, 0.7)
                y = draw_openness_bar(frame, openness[2], y)
                for i, eye in enumerate(("left", "right")):
                    ref = getattr(calibration, eye)
                    y = draw_text(frame, f"{eye.capitalize()} eye: openness {openness[i]:.2f} "
                                         f"| blinks {eye_counters[eye].count} "
                                         f"| EAR {reliable_ears[eye]:.3f} "
                                         f"(open {ref.open_ear:.3f}, closed {ref.closed_ear:.3f})",
                                  y, WHITE, 0.55)
                    y = draw_openness_bar(frame, openness[i], y - 10, height=10)

            if calibration is not None:
                draw_score_graph(frame, history, now, y_bottom=height - 65)
            if measurement is not None and measurement.ears:
                ears = measurement.ears
                draw_text(frame, f"EAR left {ears['left']:.3f} | right {ears['right']:.3f}",
                          height - 45, WHITE, 0.5)
            draw_text(frame, "SPACE or C = calibrate | M = mesh on/off | Q = quit", height - 15, WHITE, 0.5)

            cv2.imshow(WINDOW_NAME, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                break
            if key in (ord("m"), ord("M")):
                show_mesh = not show_mesh
            if key in (ord(" "), ord("c"), ord("C")):
                calibration = None  # forget the old one; never mix old and new
                history.clear()
                calibrator.start(now)
    finally:
        # Always give the webcam back, even if something went wrong.
        landmarker.close()
        camera.release()
        cv2.destroyAllWindows()
        cv2.waitKey(1)  # lets macOS actually close the window

    print(f"Total blinks: {counter.count} "
          f"(left eye alone: {eye_counters['left'].count}, right eye alone: {eye_counters['right'].count})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
