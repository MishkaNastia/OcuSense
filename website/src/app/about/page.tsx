import type { Metadata } from "next";
import Link from "next/link";

import { QuietArt } from "@/components/art/Art";
import { team } from "@/content/team";

export const metadata: Metadata = { title: "About us" };

export default function AboutPage() {
  return (
    <div className="container page">
      <header className="page-head">
        <div>
          <p className="eyebrow">About us</p>
          <h1>Students who stare at screens too long, like you.</h1>
          <p className="lead">{team.intro}</p>
        </div>
        <QuietArt />
      </header>

      <section className="section-rule" aria-labelledby="approach">
        <h2 id="approach">Our approach</h2>
        <div className="three-col">
          {team.approach.map((item) => (
            <div key={item.title}>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </div>
          ))}
        </div>
        <p className="muted">
          What OcuSense doesn’t do: diagnose tiredness, dry eye or any other condition. Its reminders aren’t clinically
          tested. It tells you what the camera saw and leaves the conclusions to you.
        </p>
      </section>

      <section className="section-rule" aria-labelledby="team">
        <h2 id="team">The team</h2>
        {team.members.length ? (
          <ul className="three-col" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {team.members.map((m) => (
              <li key={m.name}>
                <h3>{m.name}</h3>
                <p className="muted">{m.role}</p>
                {m.bio ? <p>{m.bio}</p> : null}
                {m.link ? <a href={m.link.href}>{m.link.label}</a> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="prose">
            We’re a small team of computer science engineering, life sciences engineering and data science students. Proper
            introductions are coming soon, once we find photos where our eyes are open.
          </p>
        )}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <Link href="/demo" className="btn btn-primary">Try the demo</Link>
          <Link href="/how-it-works" className="btn btn-secondary">How it works</Link>
        </div>
      </section>
    </div>
  );
}
