import Link from "next/link";

import { HeroArt, LocalArt, QuietArt } from "@/components/art/Art";
import { SCIENCE_HIGHLIGHTS } from "@/content/science";
import { team } from "@/content/team";

import styles from "./home.module.css";

/** What the desktop app does today. Keep this list true to the app. */
const FEATURES = [
  {
    title: "Watches your blinks",
    text: "A 25 second calibration teaches OcuSense what your eyes look like open and closed. Then it counts your blinks, times them and shows your blink rate while you study.",
  },
  {
    title: "Taps you on the shoulder",
    text: "Leaning in too close, blinking slower than usual, studying in the dark, slumping like a croissant: you get a friendly nudge, also when OcuSense is in the background.",
  },
  {
    title: "Keeps time for you",
    text: "A Pomodoro timer that starts and pauses eye monitoring for you, and a Time log that remembers whether you spent the afternoon on statistics or on “statistics”.",
  },
  {
    title: "Makes breaks fun",
    text: "Learn Morse code by blinking, jump over toilets in EyeGame, or water a little garden with an eye exercise. Your eyes rest, your brain gets a treat.",
  },
  {
    title: "Pays you in paintings",
    text: "Harvest your garden for coins and spend them on a gallery: Van Gogh, Vermeer, Rosa Bonheur and friends. Hang your favourites in the sidebar. Compare scores with friends.",
  },
  {
    title: "Dresses up",
    text: "Pick the calm Miró look with a little painter at his easel, or the loud Keith Haring look with two dancers. It switches instantly, no restart.",
  },
] as const;

/** Real messages the app sends (ocusense/ui/main_window.py and friends). */
const MESSAGES = [
  { title: "Trying to lick the screen?", body: "Go easy on your eyes and move back a little." },
  { title: "Time for a break", body: "Hey, you should take a break, else your eyes will become drier than the Sahara desert." },
  { title: "Focus round done, nice work!", body: "Short break time. Look out of a window: your eyes have been staring at pixels for a while." },
  { title: "Your garden needs a little water", body: "Some plants are thirsty. Time for a quick eye break in the garden?" },
] as const;

export default function Home() {
  return (
    <>
      <section className={`container ${styles.hero}`}>
        <div className={styles.heroText}>
          <h1>Big Brother watches you. OcuSense looks out for you.</h1>
          <p className="lead">
            OcuSense is a study app for long days at your laptop. It uses your webcam to count your blinks and
            reminds you to rest your eyes before they feel dry and tired. It also looks after your setup: it tells you when you lean in too close, slump in your chair or study in a
            room that’s too dark. On top of that you get a Pomodoro
            timer, a time log, small games for your breaks and a little garden to look after.
          </p>
          <div className={styles.ctas}>
            <Link href="/demo" className="btn btn-primary">Try the demo</Link>
            <Link href="/download" className="btn btn-secondary">Get the app</Link>
          </div>
          <p className={styles.small}>The demo needs no account. Your camera pictures never leave your computer.</p>
        </div>
        <HeroArt className={styles.heroArt} />
      </section>

      <section className={`container ${styles.section}`} aria-labelledby="features-title">
        <p className="eyebrow">What the app does</p>
        <h2 id="features-title">Your study buddy, with a webcam and opinions</h2>
        <ul className={styles.features}>
          {FEATURES.map((f) => (
            <li key={f.title} className={styles.feature}>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </li>
          ))}
        </ul>
        <Link href="/how-it-works" className="btn btn-secondary" style={{ alignSelf: "flex-start" }}>How it works</Link>
      </section>

      <section className={`container ${styles.section}`} aria-labelledby="messages-title">
        <p className="eyebrow">Straight from the app</p>
        <h2 id="messages-title">The kind of messages you’ll get</h2>
        <p className="lead">One at a time, easy to dismiss, and you can switch each kind off in Settings.</p>
        <ul className={styles.messages}>
          {MESSAGES.map((m) => (
            <li key={m.title} className={styles.message}>
              <b>{m.title}</b>
              <span>{m.body}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className={`container ${styles.section}`} aria-labelledby="science-title">
        <p className="eyebrow">The science behind it</p>
        <h2 id="science-title">Why we care about your blinks</h2>
        <div className="three-col">
          {SCIENCE_HIGHLIGHTS.map((h) => (
            <div key={h.title}>
              <h3>{h.title}</h3>
              <p>{h.text}</p>
            </div>
          ))}
        </div>
        <Link href="/science" className="btn btn-secondary" style={{ alignSelf: "flex-start" }}>Read the science</Link>
      </section>

      <section className={`container ${styles.split}`} aria-labelledby="local-title">
        <LocalArt className={styles.localArt} />
        <div className={styles.splitText}>
          <p className="eyebrow">Privacy</p>
          <h2 id="local-title">Your face stays on your computer.</h2>
          <p>
            OcuSense looks at each camera picture, measures your eyes and throws the picture away. Nothing is
            recorded or uploaded. What it keeps is numbers: your calibration, your settings, your garden, your time
            log and, if you switch it on, a recording of eye measurements.
          </p>
          <p>
            You only need an account for the online leaderboards, and then the only things shared are your username
            and your game scores. Nobody sees your blinks. Not us, not your flatmates.
          </p>
          <Link href="/privacy">The full privacy page</Link>
        </div>
      </section>

      <section className={`container ${styles.section}`} aria-labelledby="where-title">
        <p className="eyebrow">App and browser</p>
        <h2 id="where-title">Two ways to try it</h2>
        <div className={styles.compare}>
          <div>
            <h3>Desktop app</h3>
            <ul>
              <li>Made for long study sessions, running quietly behind your notes.</li>
              <li>Everything above: blinks, reminders, Pomodoro, Time log, games, garden and gallery.</li>
              <li>Mac first. A Windows version is being tested.</li>
              <li><Link href="/download">Download status</Link></li>
            </ul>
          </div>
          <div>
            <h3>Browser demo</h3>
            <ul>
              <li>Nothing to install: a sample session, or your own camera in this tab.</li>
              <li>The same blink rules as the app, tested against it.</li>
              <li>A taste of the measuring part. The games and garden live in the app.</li>
              <li><Link href="/demo">Open the demo</Link></li>
            </ul>
          </div>
        </div>
      </section>

      <section className={`container ${styles.split}`} aria-labelledby="team-title">
        <div className={styles.splitText}>
          <p className="eyebrow">Who we are</p>
          <h2 id="team-title">Made by students who also stare at screens too long</h2>
          <p>{team.intro}</p>
          <Link href="/about" className="btn btn-secondary">About us</Link>
        </div>
        <QuietArt className={styles.quietArt} />
      </section>
    </>
  );
}
