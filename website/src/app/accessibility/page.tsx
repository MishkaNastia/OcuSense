import type { Metadata } from "next";

export const metadata: Metadata = { title: "Accessibility" };

export default function AccessibilityPage() {
  return (
    <div className="container page">
      <header className="prose">
        <p className="eyebrow">Accessibility</p>
        <h1>Made to be usable by everyone.</h1>
        <p className="lead">What we’ve done so far, and what we know still needs work.</p>
      </header>
      <section className="section-rule prose" aria-labelledby="done">
        <h2 id="done">What we aim for</h2>
        <ul>
          <li>Every control works with a keyboard, with a clearly visible focus outline.</li>
          <li>Text meets contrast guidelines; colours are never the only way information is shown (shapes and labels too).</li>
          <li>Readable typefaces: Atkinson Hyperlegible, designed for low-vision readers.</li>
          <li>If your system asks for reduced motion, transitions are switched off. Nothing animates on its own.</li>
          <li>Prompts are announced politely to screen readers and never move your focus.</li>
          <li>The camera demo is optional; everything can be explored with the sample session.</li>
        </ul>
      </section>
      <section className="section-rule prose" aria-labelledby="limits">
        <h2 id="limits">Known limitations</h2>
        <ul>
          <li>Live graphs are visual; their key numbers are also shown as text next to them.</li>
          <li>Eye measurement needs a visible face and reasonable light, and hasn’t been evaluated across all eye shapes, skin tones and glasses yet.</li>
          <li>We haven’t yet tested with every screen reader. If something doesn’t work for you, please tell us via the project’s GitHub page.</li>
        </ul>
      </section>
    </div>
  );
}
