"""Camera capture and per-frame image processing (MediaPipe + OpenCV).

pipeline.py turns one camera frame into structured results using the pure
calculations in ocusense/core. camera_worker.py runs that in a background
thread and sends results to the interface. No widgets here.
"""
