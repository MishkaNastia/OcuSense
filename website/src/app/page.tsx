import Link from "next/link";

import { AlertGallery } from "@/components/alerts/Alerts";
import { HeroArt, LocalArt, QuietArt, StepMark } from "@/components/art/Art";
import { SCIENCE_HIGHLIGHTS } from "@/content/science";
import { team } from "@/content/team";

import styles from "./home.module.css";

const STEPS = [
  { mark: "calibrate", title: "Calibrate", text: "Thirty seconds: eyes comfortably open, gently closed, a few natural blinks. Every measurement is then relative to you.", status: "In the Mac app and the camera demo" },
  { mark: "study", title: "Study", text: "OcuSense watches eye openness and counts completed blinks while you work. Images are processed on your device.", status: "In the Mac app and the camera demo" },
  { mark: "notice", title: "Notice patterns", text: "Blink rate, closure duration and time classified as closed over the last minute — with tracking gaps left out, never counted as zero.", status: "Measurements: available · pattern prompts: experimental" },
  { mark: "break", title: "Take a break", text: "A gentle reminder at your planned interval. Pick a walk, a stretch, looking away, quiet rest or a nap.", status: "Demo on this site · planned for the Mac app" },
  { mark: "reflect", title: "Reflect", text: "Rate sleepiness and eye comfort before and after. Over time you see which breaks you said helped — your words, not a verdict.", status: "Demo on this site · planned for the Mac app" },
] as const;

export default function Home() {
  return (
    <>
      <section className={`container ${styles.hero}`}>
        <div className={styles.heroText}>
          <h1>Big Brother watches you. OcuSense looks out for you.</h1>
          <p className="lead">
            OcuSense monitors your blinking and eye patterns in real time through your webcam, offering personalised
            check-ins and break suggestions to help you stay mindful of eye dryness and fatigue during long hours at
            your computer.
          </p>
          <div className={styles.ctas}>
            <Link href="/demo" className="btn btn-primary">Try the demo</Link>
            <Link href="/download" className="btn btn-secondary">Get the Mac app</Link>
          </div>
          <p className={styles.small}>No account needed for the demo. Not a medical device.</p>
        </div>
        <HeroArt className={styles.heroArt} />
      </section>

      <section className={`container ${styles.section}`} aria-labelledby="science-title">
        <p className="eyebrow">The science behind it</p>
        <h2 id="science-title">Why blinking is worth watching</h2>
        <div className="three-col">
          {SCIENCE_HIGHLIGHTS.map((h) => (
            <div key={h.title}>
              <h3>{h.title}</h3>
              <p>{h.text}</p>
            </div>
          ))}
        </div>
        <Link href="/science" className="btn btn-secondary" style={{ alignSelf: "flex-start" }}>Learn more about the science</Link>
      </section>

      <section className={`container ${styles.section}`} aria-labelledby="how-title">
        <p className="eyebrow">How it works</p>
        <h2 id="how-title">Calibrate, study, notice, pause, reflect</h2>
        <ol className={styles.steps}>
          {STEPS.map((s, i) => (
            <li key={s.title} className={styles.step}>
              <StepMark step={s.mark} />
              <span className={`mono ${styles.stepNumber}`}>{String(i + 1).padStart(2, "0")}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
              <p className={styles.status}>{s.status}</p>
            </li>
          ))}
        </ol>
        <Link href="/how-it-works" className="btn btn-secondary" style={{ alignSelf: "flex-start" }}>Read how it works</Link>
      </section>

      <section className={`container ${styles.split}`} aria-labelledby="local-title">
        <LocalArt className={styles.localArt} blinking />
        <div className={styles.splitText}>
          <p className="eyebrow">Calibration and privacy</p>
          <h2 id="local-title">Measured against your eyes, processed on your device.</h2>
          <p>
            Eyes differ, so OcuSense doesn’t use one threshold for everyone. A short calibration records how your
            eyes look comfortably open and gently closed, and checks that your natural blinks can be detected.
          </p>
          <p>
            Camera images are analysed on your computer — in the Mac app, or in your browser for the demo — and are
            never recorded or uploaded. The site only downloads the face model from this website.
          </p>
          <Link href="/privacy">How we handle data</Link>
        </div>
      </section>

      <section className={`container ${styles.section}`} aria-labelledby="where-title">
        <p className="eyebrow">Desktop and browser</p>
        <h2 id="where-title">Two ways to try OcuSense</h2>
        <div className={styles.compare}>
          <div>
            <h3>Mac app</h3>
            <ul>
              <li>Built for long study sessions, with the window in the background.</li>
              <li>Live eye openness, blink rate, closure and closed time.</li>
              <li>Session statistics for today, the week and the month (kept until you quit, for now).</li>
              <li><Link href="/download">Download status</Link></li>
            </ul>
          </div>
          <div>
            <h3>Browser demo</h3>
            <ul>
              <li>No installation: a sample session, or your camera in this tab.</li>
              <li>Same measurement rules, ported from the app and tested against it.</li>
              <li>Browsers slow down hidden tabs, so the demo pauses when you switch away.</li>
              <li><Link href="/demo">Open the demo</Link></li>
            </ul>
          </div>
        </div>
      </section>

      <section className={`container ${styles.section}`} aria-labelledby="prompts-title">
        <p className="eyebrow">Gentle prompts</p>
        <h2 id="prompts-title">Reminders that ask, not alarms that judge</h2>
        <p className="lead">No sound, no flashing, one at a time, and always easy to dismiss.</p>
        <AlertGallery />
      </section>

      <section className={`container ${styles.split}`} aria-labelledby="team-title">
        <div className={styles.splitText}>
          <p className="eyebrow">Who we are</p>
          <h2 id="team-title">Built by engineering students, for students</h2>
          <p>{team.intro}</p>
          <Link href="/about" className="btn btn-secondary">About us</Link>
        </div>
        <QuietArt className={styles.quietArt} />
      </section>
    </>
  );
}
