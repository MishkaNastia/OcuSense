# OcuSense

Live webcam blink counter using OpenCV and Google MediaPipe Face Landmarker.
All video is processed locally in memory: nothing is recorded or uploaded.

## Setup (once)

```
cd ~/Projects/OcuSense
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python download_model.py
```

## Run

```
source .venv/bin/activate
python main.py
```

Press **Q** in the video window to quit.

## Tests

```
python -m unittest
```
