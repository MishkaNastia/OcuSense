/**
 * Eye Aspect Ratio (EAR) from MediaPipe face landmarks — port of ocusense/core/eye_metrics.py.
 *
 *      p2   p3         EAR = (|p2−p6| + |p3−p5|) / (2·|p1−p4|)
 *  p1          p4      "how tall is the eye compared to how wide"
 *      p6   p5
 *
 * Distances are computed in pixel coordinates (camera images aren't square).
 */

import { MIN_EYE_WIDTH_PX, MIN_EYE_WIDTH_RATIO } from "./config";

export type EyeName = "left" | "right";
export type Point = readonly [number, number];
export interface Landmark { x: number; y: number }

/**
 * MediaPipe face-mesh indices p1..p6. As in the desktop app, frames are
 * mirrored before detection, so "left" (indices 33…) is the eye on the left
 * of the mirrored picture — the person's own left eye.
 */
export const EYE_LANDMARKS: Record<EyeName, readonly number[]> = {
  left: [33, 160, 158, 133, 153, 144],
  right: [362, 385, 387, 263, 373, 380],
};

export function distance(a: Point, b: Point): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

export function eyeAspectRatio(points: readonly Point[]): number | null {
  const [p1, p2, p3, p4, p5, p6] = points;
  const width = distance(p1, p4);
  if (width === 0) return null;
  return (distance(p2, p6) + distance(p3, p5)) / (2 * width);
}

export function eyePointsPx(landmarks: readonly Landmark[], indices: readonly number[], width: number, height: number): Point[] {
  return indices.map((i) => [landmarks[i].x * width, landmarks[i].y * height] as const);
}

export interface EyeMeasurement {
  ears: Partial<Record<EyeName, number>>;
  reliable: boolean;
  reason: string; // why it's unreliable ("" when reliable)
}

/** Compute both EARs and decide whether this frame is trustworthy. */
export function measureEyes(landmarks: readonly Landmark[], width: number, height: number): EyeMeasurement {
  const ears: Partial<Record<EyeName, number>> = {};
  const widths: Partial<Record<EyeName, number>> = {};
  for (const name of ["left", "right"] as const) {
    const indices = EYE_LANDMARKS[name];
    if (indices.some((i) => !(landmarks[i].x >= 0 && landmarks[i].x <= 1 && landmarks[i].y >= 0 && landmarks[i].y <= 1))) {
      return { ears: {}, reliable: false, reason: "eye outside the picture" };
    }
    const points = eyePointsPx(landmarks, indices, width, height);
    widths[name] = distance(points[0], points[3]);
    const ear = eyeAspectRatio(points);
    if (ear !== null) ears[name] = ear;
  }
  const w = [widths.left ?? 0, widths.right ?? 0];
  if (Math.min(...w) < MIN_EYE_WIDTH_PX) return { ears, reliable: false, reason: "face too small - move closer" };
  if (Math.min(...w) / Math.max(...w) < MIN_EYE_WIDTH_RATIO) return { ears, reliable: false, reason: "head turned - face the camera" };
  return { ears, reliable: true, reason: "" };
}
