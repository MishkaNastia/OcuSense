"""Draws the live graph of personal eye openness for the OpenCV prototype.

The data comes from ocusense.core.history.ScoreHistory.
"""

import cv2

from ocusense.core.blink_counter import CLOSE_BELOW, REOPEN_ABOVE

# BGR colours, matching the openness bars in main.py where they overlap.
LEFT_COLOR = (255, 150, 50)
RIGHT_COLOR = (50, 150, 255)
BOTH_COLOR = (255, 255, 255)
CLOSE_COLOR = (0, 0, 255)
REOPEN_COLOR = (0, 220, 255)
BLINK_COLOR = (0, 200, 0)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def draw_score_graph(frame, history, now, y_bottom, height=100):
    """Draw the graph across the frame, ending at y_bottom."""
    x0, x1 = 10, frame.shape[1] - 10
    y0, y1 = y_bottom - height, y_bottom
    width = x1 - x0

    # Darken the background so the lines stand out on any picture.
    frame[y0:y1, x0:x1] //= 3
    cv2.rectangle(frame, (x0, y0), (x1, y1), (255, 255, 255), 1)

    def to_x(t):
        return x0 + int(width * (1 - (now - t) / history.seconds))

    def to_y(value):
        return y1 - int(height * value)

    for threshold, color in ((CLOSE_BELOW, CLOSE_COLOR), (REOPEN_ABOVE, REOPEN_COLOR)):
        cv2.line(frame, (x0, to_y(threshold)), (x1, to_y(threshold)), color, 1)

    previous = None
    for t, openness, blinked in history.samples:
        if blinked:
            cv2.line(frame, (to_x(t), y0), (to_x(t), y0 + 12), BLINK_COLOR, 2)
        if openness is not None and previous is not None:
            t_prev, openness_prev = previous
            for i, color, thickness in ((0, LEFT_COLOR, 1), (1, RIGHT_COLOR, 1), (2, BOTH_COLOR, 2)):
                cv2.line(frame, (to_x(t_prev), to_y(openness_prev[i])),
                         (to_x(t), to_y(openness[i])), color, thickness, cv2.LINE_AA)
        previous = (t, openness) if openness is not None else None

    x = x0 + 6
    for label, color in (("left", LEFT_COLOR), ("right", RIGHT_COLOR), ("both", BOTH_COLOR)):
        cv2.putText(frame, label, (x, y0 + 28), FONT, 0.45, color, 1, cv2.LINE_AA)
        x += cv2.getTextSize(label, FONT, 0.45, 1)[0][0] + 12
    cv2.putText(frame, f"last {history.seconds:.0f}s", (x1 - 70, y0 + 28), FONT, 0.45,
                (255, 255, 255), 1, cv2.LINE_AA)
