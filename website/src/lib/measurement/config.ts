/**
 * Measurement defaults — a TypeScript mirror of the desktop app's
 * ocusense/config.py. Keep the two in sync; the shared test vectors in
 * __tests__/python-vectors.json check that both produce the same results.
 *
 * Units: seconds, openness fractions (1 = calibrated open, 0 = calibrated closed), pixels.
 */

// Blink rule (both-eyes personal openness)
export const CLOSE_BELOW = 0.35;
export const REOPEN_ABOVE = 0.65;

// Calibration acceptance
export const MIN_SAMPLES = 15;
export const MIN_RELATIVE_SEPARATION = 0.25;
export const MAX_SPREAD_FRACTION = 0.25;
export const MIN_CALIBRATION_BLINKS = 3;

// Tracking quality
export const MIN_EYE_WIDTH_PX = 15;
export const MIN_EYE_WIDTH_RATIO = 0.6;

// Live graph and rolling measurements
export const GRAPH_SECONDS = 10;
/** ENGINEERING CHOICE: frames further apart than this are a gap, not observed time. */
export const MAX_FRAME_GAP = 0.5;
export const ROLLING_WINDOW_SECONDS = 60;
/** ENGINEERING CHOICE (MVP): valid seconds needed before showing blink rate and closed time. */
export const MIN_VALID_SECONDS_FOR_RATE = 30;
export const PROCESSING_RATE_WINDOW = 5;

export const MEASUREMENT_VERSION = "ear-personal-v2";
