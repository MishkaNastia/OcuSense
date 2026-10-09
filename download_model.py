"""Download the MediaPipe Face Landmarker model into models/."""

import urllib.request
from pathlib import Path

URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = Path(__file__).parent / "models" / "face_landmarker.task"

if MODEL_PATH.exists():
    print(f"Model already present: {MODEL_PATH}")
else:
    MODEL_PATH.parent.mkdir(exist_ok=True)
    print("Downloading face_landmarker.task ...")
    urllib.request.urlretrieve(URL, MODEL_PATH)
    print(f"Saved to {MODEL_PATH}")
