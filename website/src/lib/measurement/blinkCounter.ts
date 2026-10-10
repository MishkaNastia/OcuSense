/**
 * The blink rule — port of ocusense/core/blink_counter.py (unchanged behaviour).
 *
 * Fed the both-eyes personal openness each frame (or null when measurement is
 * paused). Closed below CLOSE_BELOW, open again only above REOPEN_ABOVE; one
 * blink is counted on the closed → open transition. Starting with closed eyes
 * never counts, and losing tracking forgets a half-finished blink.
 */

import { CLOSE_BELOW, REOPEN_ABOVE } from "./config";

export type DetectorState = "unknown" | "open" | "closed";

export class BlinkCounter {
  count = 0;
  state: DetectorState = "unknown";

  constructor(readonly closeBelow = CLOSE_BELOW, readonly reopenAbove = REOPEN_ABOVE) {
    if (closeBelow >= reopenAbove) throw new Error("closeBelow must be lower than reopenAbove");
  }

  /** Returns true if this frame finished a blink. */
  update(openness: number | null): boolean {
    if (openness === null) {
      this.state = "unknown";
      return false;
    }
    if (this.state === "unknown") {
      if (openness > this.reopenAbove) this.state = "open";
      return false;
    }
    if (this.state === "open") {
      if (openness < this.closeBelow) this.state = "closed";
      return false;
    }
    if (openness > this.reopenAbove) {
      this.state = "open";
      this.count += 1;
      return true;
    }
    return false;
  }
}
