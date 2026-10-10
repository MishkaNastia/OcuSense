/**
 * Original Miró-inspired vector compositions for OcuSense (editable SVG).
 * Decorative only: always aria-hidden and placed in empty space, never behind text or controls.
 */

const INK = "var(--ink)";

export function Star({ x, y, r = 12, color = INK, width = 2.4 }: { x: number; y: number; r?: number; color?: string; width?: number }) {
  const d = r * 0.7;
  return (
    <g stroke={color} strokeWidth={width} strokeLinecap="round">
      <path d={`M${x} ${y - r} V${y + r}`} />
      <path d={`M${x - r} ${y} H${x + r}`} />
      <path d={`M${x - d} ${y - d} L${x + d} ${y + d}`} />
      <path d={`M${x + d} ${y - d} L${x - d} ${y + d}`} />
    </g>
  );
}

function Crescent({ cx, cy, r, color = "var(--golden)" }: { cx: number; cy: number; r: number; color?: string }) {
  // A crescent drawn as one path: outer arc minus an offset inner arc.
  const inner = r * 0.78;
  return (
    <path
      d={`M${cx} ${cy - r} A${r} ${r} 0 1 0 ${cx + r * 0.62} ${cy + r * 0.78} A${inner} ${inner} 0 1 1 ${cx} ${cy - r} Z`}
      fill={color} stroke={INK} strokeWidth={2} strokeLinejoin="round"
    />
  );
}

/** Large hero composition: an open eye drawn in one gesture, with sun, crescent and stars. */
export function HeroArt({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 520 440" aria-hidden="true" focusable="false">
      <g className="blink">
        <path d="M40 250 C 120 120, 360 90, 470 220 C 380 330, 150 350, 70 280" fill="none" stroke={INK} strokeWidth={9} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        <circle cx="268" cy="228" r="58" fill="var(--cobalt)" />
        <circle cx="290" cy="208" r="11" fill="var(--paper)" />
      </g>
      <path d="M96 150 C 150 70, 250 40, 330 70" fill="none" stroke={INK} strokeWidth={3} strokeLinecap="round" />
      <circle cx="420" cy="88" r="26" fill="var(--vermilion)" />
      <Crescent cx={110} cy={372} r={34} />
      <Star x={360} y={372} r={16} />
      <Star x={470} y={300} r={9} color="var(--vermilion)" width={2.2} />
      <circle cx="210" cy="400" r="7" fill="var(--green)" />
      <circle cx="58" cy="96" r="5" fill={INK} />
      <path d="M380 380 C 410 350, 450 350, 480 380" fill="none" stroke={INK} strokeWidth={2.4} strokeLinecap="round" />
    </svg>
  );
}

/** Quiet composition for empty space (same family as the desktop app's study screen). */
export function QuietArt({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 320 250" aria-hidden="true" focusable="false">
      <path d="M14 232 C 30 130, 112 64, 178 112 S 268 196, 296 74" fill="none" stroke={INK} strokeWidth={3} strokeLinecap="round" />
      <circle cx="214" cy="66" r="34" fill="var(--cobalt)" />
      <Crescent cx={58} cy={214} r={22} />
      <circle cx="296" cy="74" r="8" fill="var(--vermilion)" />
      <Star x={104} y={35} r={13} width={2.2} />
      <circle cx="252" cy="214" r="5" fill="var(--green)" />
    </svg>
  );
}

/** Small marks for the five steps (calibrate, study, notice, break, reflect). */
export function StepMark({ step, size = 72 }: { step: "calibrate" | "study" | "notice" | "break" | "reflect"; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 72 72" aria-hidden="true" focusable="false">
      {step === "calibrate" && (<>
        <path d="M8 38 C 20 20, 52 18, 64 34 C 52 50, 22 52, 12 42" fill="none" stroke={INK} strokeWidth={3.5} strokeLinecap="round" />
        <circle cx="37" cy="35" r="9" fill="var(--cobalt)" />
        <path d="M37 6 V16 M37 56 V66" stroke="var(--vermilion)" strokeWidth={2.6} strokeLinecap="round" />
      </>)}
      {step === "study" && (<>
        <rect x="12" y="18" width="48" height="32" rx="4" fill="none" stroke={INK} strokeWidth={3} />
        <path d="M6 56 H66" stroke={INK} strokeWidth={3} strokeLinecap="round" />
        <circle cx="36" cy="34" r="6" fill="var(--cobalt)" />
      </>)}
      {step === "notice" && (<>
        <path d="M6 30 H22 L28 54 L36 30 H66" fill="none" stroke="var(--cobalt)" strokeWidth={3} strokeLinejoin="round" strokeLinecap="round" />
        <circle cx="28" cy="54" r="5" fill="var(--vermilion)" stroke={INK} strokeWidth={1.5} />
        <Star x={56} y={14} r={7} width={2} />
      </>)}
      {step === "break" && (<>
        <path d="M14 46 A 22 22 0 0 1 58 46 Z" fill="var(--golden)" stroke={INK} strokeWidth={2} strokeLinejoin="round" />
        <path d="M6 48 C 24 42, 46 54, 66 46" fill="none" stroke={INK} strokeWidth={3} strokeLinecap="round" />
      </>)}
      {step === "reflect" && (<>
        <path d="M30 10 A 24 24 0 1 0 56 44 A 18 18 0 1 1 30 10 Z" fill="var(--cobalt)" />
        <Star x={58} y={16} r={7} color="var(--vermilion)" width={2.2} />
        <circle cx="14" cy="60" r="4" fill="var(--green)" />
      </>)}
    </svg>
  );
}

/** "Stays on your device": an eye inside a device outline, with a line that stops at its edge. */
export function LocalArt({ className, blinking = false }: { className?: string; blinking?: boolean }) {
  return (
    <svg className={className} viewBox="0 0 280 200" aria-hidden="true" focusable="false">
      <rect x="20" y="24" width="168" height="120" rx="12" fill="var(--paper-light)" stroke={INK} strokeWidth={3} />
      <path d="M4 168 H204" stroke={INK} strokeWidth={3} strokeLinecap="round" />
      <g className={blinking ? "blink" : undefined}>
        <path d="M52 86 C 72 58, 136 54, 158 80 C 136 106, 74 110, 60 96" fill="none" stroke={INK} strokeWidth={3.5} strokeLinecap="round" />
        <circle cx="106" cy="83" r="13" fill="var(--cobalt)" />
      </g>
      <path d="M200 84 H244" stroke={INK} strokeWidth={2.4} strokeDasharray="4 6" strokeLinecap="round" />
      <path d="M252 70 L272 98 M272 70 L252 98" stroke="var(--vermilion)" strokeWidth={3} strokeLinecap="round" />
      <Star x={232} y={30} r={10} />
    </svg>
  );
}
