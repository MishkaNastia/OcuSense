/**
 * Sample study history for the "personal patterns" view — SYNTHETIC, for the demo only.
 * Internally consistent: totals are computed from these rows, never typed separately.
 */

export type Activity = "walking" | "stretching" | "lookaway" | "rest" | "nap" | "other";

export const ACTIVITIES: { id: Activity; label: string; hint: string }[] = [
  { id: "walking", label: "Walking", hint: "Move around, indoors or out" },
  { id: "stretching", label: "Stretching", hint: "Neck, shoulders, back" },
  { id: "lookaway", label: "Looking away from screens", hint: "Rest your eyes on something far away" },
  { id: "rest", label: "Quiet rest", hint: "Sit or lie down without screens" },
  { id: "nap", label: "Nap", hint: "A short sleep" },
  { id: "other", label: "Other", hint: "Add your own label" },
];

export const SLEEPY_LABELS = ["Not at all sleepy", "Slightly sleepy", "Somewhat sleepy", "Quite sleepy", "Very sleepy"];
export const COMFORT_LABELS = ["Very uncomfortable", "Uncomfortable", "Neutral", "Comfortable", "Very comfortable"];
export type Helpful = "not" | "little" | "very";
export const HELPFUL_LABELS: Record<Helpful, string> = { not: "Not helpful", little: "A little", very: "Very helpful" };

/** One logged break with optional self-reports (1–5). */
export interface BreakRecord {
  id: string;
  day: string; // e.g. "Mon"
  activity: Activity;
  label: string;
  minutes: number;
  sleepy: [number | null, number | null]; // before, after
  comfort: [number | null, number | null];
  helpful: Helpful | null;
  note?: string;
  sample: boolean; // true = synthetic history, false = entered in this demo
}

/** Simulated measurements per study day (camera-derived numbers, synthetic). */
export interface SampleDay {
  day: string;
  studyMinutes: number;
  trackedShare: number; // 0–1
  blinkRate: number; // blinks/min
  medianClosureMs: number;
  closedPercent: number;
}

export const SAMPLE_DAYS: SampleDay[] = [
  { day: "Mon", studyMinutes: 95, trackedShare: 0.95, blinkRate: 15.5, medianClosureMs: 180, closedPercent: 2.8 },
  { day: "Tue", studyMinutes: 120, trackedShare: 0.96, blinkRate: 15.1, medianClosureMs: 186, closedPercent: 3.0 },
  { day: "Wed", studyMinutes: 0, trackedShare: 0, blinkRate: 0, medianClosureMs: 0, closedPercent: 0 },
  { day: "Thu", studyMinutes: 140, trackedShare: 0.93, blinkRate: 14.2, medianClosureMs: 196, closedPercent: 3.4 },
  { day: "Fri", studyMinutes: 110, trackedShare: 0.94, blinkRate: 14.9, medianClosureMs: 188, closedPercent: 3.1 },
  { day: "Sat", studyMinutes: 155, trackedShare: 0.94, blinkRate: 14.7, medianClosureMs: 191, closedPercent: 3.2 },
];

const b = (id: string, day: string, activity: Activity, minutes: number,
  sleepy: [number | null, number | null], comfort: [number | null, number | null], helpful: Helpful | null): BreakRecord => ({
  id, day, activity, label: ACTIVITIES.find((a) => a.id === activity)!.label, minutes, sleepy, comfort, helpful, sample: true,
});

export const SAMPLE_BREAKS: BreakRecord[] = [
  b("s1", "Mon", "walking", 10, [3, 3], [3, 3], "little"),
  b("s2", "Mon", "rest", 10, [4, 3], [3, 3], "little"),
  b("s3", "Tue", "walking", 15, [4, 3], [2, 3], "very"),
  b("s4", "Tue", "stretching", 5, [3, 3], [2, 3], "little"),
  b("s5", "Thu", "lookaway", 5, [3, 2], [2, 3], "very"),
  b("s6", "Thu", "walking", 10, [3, 4], [3, 3], "not"),
  b("s7", "Thu", "rest", 10, [3, null], [3, null], null),
  b("s8", "Fri", "walking", 10, [4, 2], [3, 3], "very"),
  b("s9", "Fri", "stretching", 5, [4, null], [3, null], null),
  b("s10", "Sat", "walking", 10, [4, 2], [3, 4], "very"),
  b("s11", "Sat", "lookaway", 5, [3, 3], [2, 4], "little"),
  b("s12", "Sat", "stretching", 5, [3, 2], [3, 3], "little"),
];

/** At least this many breaks with both check-ins before we describe a tendency. */
export const STILL_LEARNING_BELOW = 5;

export interface ActivitySummary {
  activity: Activity;
  label: string;
  logged: number;
  complete: number;
  improved: number;
  stillLearning: boolean;
}

/** "What seems helpful": counts of self-reported improvement — never a claim of cause. */
export function summarise(breaks: BreakRecord[], measure: "sleepy" | "comfort"): ActivitySummary[] {
  return ACTIVITIES.flatMap((a) => {
    const list = breaks.filter((x) => x.activity === a.id);
    if (!list.length) return [];
    const complete = list.filter((x) => x[measure][0] !== null && x[measure][1] !== null);
    const improved = complete.filter((x) =>
      measure === "sleepy" ? x.sleepy[1]! < x.sleepy[0]! : x.comfort[1]! > x.comfort[0]!).length;
    return [{ activity: a.id, label: a.label, logged: list.length, complete: complete.length, improved, stillLearning: complete.length < STILL_LEARNING_BELOW }];
  });
}
