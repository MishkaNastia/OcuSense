/** Display formatting: internal units (seconds, fractions) → readable text. "—" means unavailable. */

export const UNAVAILABLE = "—";
export const COLLECTING = "Collecting data";

export function percent(value: number | null): string {
  return value === null ? UNAVAILABLE : `${Math.round(value)}%`;
}

export function blinkRate(value: number | null, enough: boolean): string {
  if (!enough) return COLLECTING;
  return value === null ? UNAVAILABLE : `${value.toFixed(1)} blinks/min`;
}

/** Median closure is stored in seconds and shown in milliseconds. */
export function closureMs(seconds: number | null): string {
  return seconds === null ? UNAVAILABLE : `${Math.round(seconds * 1000)} ms`;
}

export function closedPercent(value: number | null, enough: boolean): string {
  if (!enough) return COLLECTING;
  return value === null ? UNAVAILABLE : `${value.toFixed(1)}%`;
}

export function duration(seconds: number): string {
  if (seconds < 59.5) return `${Math.round(seconds)} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h${minutes % 60 ? ` ${minutes % 60} min` : ""}`;
}

export function clock(seconds: number): string {
  const s = Math.floor(seconds);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
}
