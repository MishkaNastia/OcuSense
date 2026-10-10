import type { Metadata } from "next";
import Link from "next/link";

import { QuietArt } from "@/components/art/Art";
import { REFERENCES, SCIENCE_SECTIONS } from "@/content/science";

export const metadata: Metadata = { title: "The science" };

const NUMBER = new Map(REFERENCES.map((r, i) => [r.id, i + 1]));

export default function SciencePage() {
  return (
    <div className="container page">
      <header className="page-head">
        <div>
          <p className="eyebrow">The science behind it</p>
          <h1>What your blinks can say about fatigue</h1>
          <p className="lead">
            Research on screen work and drowsiness links how we blink to dry, tired eyes and to falling alertness.
            Here is a short summary of what that research found, with the original articles.
          </p>
        </div>
        <QuietArt />
      </header>

      {SCIENCE_SECTIONS.map((section) => (
        <section key={section.id} className="section-rule" aria-labelledby={section.id}>
          <h2 id={section.id}>{section.title}</h2>
          <div className="prose">
            {section.paragraphs.map((p) => <p key={p.slice(0, 32)}>{p}</p>)}
            <p className="muted">
              Sources:{" "}
              {section.sources.map((id, i) => (
                <span key={id}>
                  {i > 0 ? ", " : ""}
                  <a href={`#ref-${id}`}>[{NUMBER.get(id)}]</a>
                </span>
              ))}
            </p>
          </div>
        </section>
      ))}

      <section className="section-rule" aria-labelledby="ocusense">
        <h2 id="ocusense">How OcuSense uses this — and what it doesn’t claim</h2>
        <div className="prose">
          <p>
            OcuSense measures the same kinds of signals these studies describe: your <b>blink rate</b>, how long each
            eye <b>closure</b> lasts, and the share of time your eyes are <b>classified as closed</b> — all relative to
            your own calibration. It uses them to offer check-ins and break suggestions, and asks you how you feel.
          </p>
          <p>
            The studies describe patterns across groups of people, mostly in laboratory settings. OcuSense is not a
            medical device: it does not diagnose tiredness, dry eye or any other condition, and its suggestions are
            not clinically validated. If your eyes often feel dry or sore, talk to an optician or doctor.
          </p>
          <p><Link href="/how-it-works">How OcuSense measures your eyes</Link></p>
        </div>
      </section>

      <section className="section-rule" aria-labelledby="references">
        <h2 id="references">References</h2>
        <ol className="prose">
          {REFERENCES.map((r) => (
            <li key={r.id} id={`ref-${r.id}`}>
              {r.authors} ({r.year}). {r.title}{/[?!]$/.test(r.title) ? "" : "."} <i>{r.journal}</i>.{" "}
              <a href={`https://doi.org/${r.doi}`} rel="noopener noreferrer">doi:{r.doi}</a>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
