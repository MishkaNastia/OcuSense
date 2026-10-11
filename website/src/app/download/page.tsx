import type { Metadata } from "next";
import Link from "next/link";

import { releases, type Release } from "@/content/release";
import { site } from "@/content/site";

import styles from "./download.module.css";

export const metadata: Metadata = { title: "Download" };

const STATUS_TEXT: Record<Release["status"], string> = {
  available: "Available",
  "coming-soon": "Download coming soon",
  planned: "Planned",
};

export default function DownloadPage() {
  return (
    <div className="container page">
      <header className="prose">
        <p className="eyebrow">Download</p>
        <h1>OcuSense for your computer</h1>
        <p className="lead">
          The desktop app is made for real study sessions. Download it for free, or try the browser demo first.
        </p>
      </header>

      <section aria-label="Platforms" className={styles.platforms}>
        {releases.map((r) => (
          <div key={r.platform} className={styles.platform}>
            <div className={styles.platformHead}>
              <h2>{r.platform}</h2>
              <span className={r.status === "available" ? "tag tag-solid" : "tag"}>{STATUS_TEXT[r.status]}</span>
            </div>
            {r.status === "available" && r.url ? (
              <>
                <a className="btn btn-primary" href={r.url}>Download {r.fileName ?? `for ${r.platform}`}{r.version ? ` · ${r.version}` : ""}</a>
                {r.sizeLabel ? <p className="muted">{r.sizeLabel}</p> : null}
                {r.sha256 ? <p className="muted mono" style={{ wordBreak: "break-all" }}>SHA-256 {r.sha256}</p> : null}
              </>
            ) : (
              <p className="muted">{r.status === "planned" ? "Not built yet. Mac and Windows come first." : r.notes}</p>
            )}
            {r.verified?.length ? (
              <ul className={styles.facts}>{r.verified.map((fact) => <li key={fact}>{fact}</li>)}</ul>
            ) : null}
          </div>
        ))}
      </section>

      <section className="section-rule" aria-labelledby="which">
        <h2 id="which">Desktop app or browser demo?</h2>
        <dl className="def">
          <dt>Desktop app</dt>
          <dd>Runs during your study session: calibration, live measurements, reminders, Pomodoro, Time log, games, garden and gallery. Camera images stay on your computer.</dd>
          <dt>Browser demo</dt>
          <dd>No installation. A sample session with made up data, or a short live test with your camera in this tab. It pauses when the tab is hidden.</dd>
        </dl>
        <Link href="/demo" className="btn btn-secondary" style={{ alignSelf: "flex-start" }}>Try the demo</Link>
      </section>

      <section className="section-rule prose" aria-labelledby="install">
        <h2 id="install">Installing it</h2>
        <h3>Mac</h3>
        <ol>
          <li>Double click the downloaded zip, then drag <b>OcuSense</b> to your Applications folder.</li>
          <li>
            It isn’t <b>notarised by Apple</b> yet, so the first time, right click (or Control click) OcuSense and
            choose <b>Open</b>, then <b>Open</b> again.
          </li>
          <li>Press <b>Start</b>. macOS asks whether OcuSense may use the camera. Choose <b>Allow</b> and it carries on by itself.</li>
          <li>
            Clicked “Don’t Allow” by accident? Open <b>System Settings › Privacy &amp; Security › Camera</b>, switch on
            OcuSense, quit it (⌘Q) and open it again.
          </li>
        </ol>
        <h3>Windows (beta)</h3>
        <ol>
          <li>Right click the zip, choose <b>Extract All</b>, and open <b>OcuSense\OcuSense.exe</b>. Keep it next to its <b>_internal</b> folder.</li>
          <li>It isn’t signed yet, so SmartScreen may say “Windows protected your PC”: choose <b>More info</b>, then <b>Run anyway</b>.</li>
          <li>If the camera doesn’t start: <b>Settings › Privacy &amp; security › Camera</b>, turn on camera access for desktop apps, and close Teams or Zoom.</li>
        </ol>
        <h3>Linux (beta)</h3>
        <ol>
          <li>Unpack the archive (<span className="mono">tar xzf OcuSense-linux-x64.tar.gz</span>) and run <span className="mono">./OcuSense/OcuSense</span>.</li>
        </ol>
        <p className="muted">
          Developers can also build the app from the <a href={site.repositoryUrl}>source code</a> (see the README there).
        </p>
      </section>
    </div>
  );
}
