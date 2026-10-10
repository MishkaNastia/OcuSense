/**
 * The approved OcuSense logo B ("one-line eye"): a single black stroke that
 * doesn't quite close, a cobalt pupil and a small vermilion star.
 * Same vector geometry as the design board (64 × 64 grid).
 */
export function LogoMark({ size = 40, mono = false, title }: { size?: number; mono?: boolean; title?: string }) {
  const ink = mono ? "currentColor" : "var(--ink)";
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role={title ? "img" : undefined} aria-hidden={title ? undefined : true}>
      {title ? <title>{title}</title> : null}
      <path d="M6 33 C 16 17, 46 13, 58 29 C 47 45, 20 48, 10 38" fill="none" stroke={ink}
        strokeWidth={mono ? 6 : 4.5} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="33" cy="31" r={mono ? 9 : 8.5} fill={mono ? "currentColor" : "var(--cobalt)"} />
      <g stroke={mono ? "currentColor" : "var(--vermilion)"} strokeWidth={mono ? 3.4 : 2.6} strokeLinecap="round">
        <path d="M53 3 V15" /><path d="M47 9 H59" />
        {mono ? null : (<><path d="M49 5 L57 13" /><path d="M57 5 L49 13" /></>)}
      </g>
    </svg>
  );
}

export function Wordmark({ size = 26 }: { size?: number }) {
  return (
    <span style={{
      fontFamily: "var(--font-display)", fontWeight: 750, fontSize: size, letterSpacing: "-0.03em",
      fontVariationSettings: '"opsz" 96', lineHeight: 1,
    }}>
      OcuSense
    </span>
  );
}
