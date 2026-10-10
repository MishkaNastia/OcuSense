import type { Metadata } from "next";

export const metadata: Metadata = { title: "Credits & licences" };

const CREDITS = [
  { name: "MediaPipe Tasks Vision and Face Landmarker model", by: "Google", licence: "Apache License 2.0", url: "https://github.com/google-ai-edge/mediapipe" },
  { name: "Bricolage Grotesque", by: "Mathieu Triay", licence: "SIL Open Font License 1.1", url: "https://fonts.google.com/specimen/Bricolage+Grotesque" },
  { name: "Atkinson Hyperlegible Next and Mono", by: "Braille Institute of America", licence: "SIL Open Font License 1.1", url: "https://fonts.google.com/specimen/Atkinson+Hyperlegible+Next" },
  { name: "Next.js and React", by: "Vercel and Meta", licence: "MIT License", url: "https://github.com/vercel/next.js" },
  { name: "Supabase client libraries", by: "Supabase", licence: "MIT License", url: "https://github.com/supabase/supabase-js" },
];

export default function CreditsPage() {
  return (
    <div className="container page">
      <header className="prose">
        <p className="eyebrow">Credits & licences</p>
        <h1>Built on open work.</h1>
        <p className="lead">The OcuSense logo and illustrations are original artwork by the OcuSense team. We use these open-source components:</p>
      </header>
      <section className="section-rule">
        <dl className="def">
          {CREDITS.map((c) => (
            <div key={c.name} style={{ display: "contents" }}>
              <dt>{c.name}</dt>
              <dd>{c.by} · {c.licence} · <a href={c.url}>source</a></dd>
            </div>
          ))}
        </dl>
        <p className="muted">Fonts are served by this website (self-hosted at build time); no font service sees your visit.</p>
      </section>
    </div>
  );
}
