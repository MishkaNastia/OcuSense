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
  const mac = releases[0];
  return (
    <div className="container page">
      <header className="prose">
        <p className="eyebrow">Download</p>
        <h1>OcuSense for your computer</h1>
        <p className="lead">
          The desktop app is made for real study sessions. Until a public build is available, you can try everything in
          the browser demo.
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
              <p className="muted">{r.status === "planned" ? "Not built yet. We started with macOS." : r.notes}</p>
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
          <dt>Desktop app (macOS)</dt>
          <dd>Runs during your study session, with its own calibration, live measurements and session statistics. Camera images stay on your Mac.</dd>
          <dt>Browser demo</dt>
          <dd>No installation. A sample session with synthetic data, or a short live test with your camera in this tab. It pauses when the tab is hidden.</dd>
        </dl>
        <Link href="/demo" className="btn btn-secondary" style={{ alignSelf: "flex-start" }}>Try the demo</Link>
      </section>

      <section className="section-rule prose" aria-labelledby="install">
        <h2 id="install">Installing on a Mac (once a download is available)</h2>
        <ol>
          <li>Open the downloaded file and drag <b>OcuSense</b> to your Applications folder or Desktop.</li>
          <li>
            The current builds are <b>not notarised by Apple</b>, so the first time, right-click (or Control-click)
            OcuSense and choose <b>Open</b>, then <b>Open</b> again.
          </li>
          <li>Press <b>Start</b>. macOS asks whether OcuSense may use the camera — choose <b>Allow</b>.</li>
          <li>
            If you clicked “Don’t Allow”: open <b>System Settings › Privacy &amp; Security › Camera</b>, switch on
            OcuSense, quit it (⌘Q) and open it again.
          </li>
        </ol>
        <p className="muted">
          Developers can build the app today from the <a href={site.repositoryUrl}>source code</a> (see the README there).
          {mac.status !== "available" ? " There is no prebuilt download yet." : ""}
        </p>
      </section>
    </div>
  );
}
