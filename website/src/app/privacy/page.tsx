import type { Metadata } from "next";
import Link from "next/link";

import { LocalArt } from "@/components/art/Art";

export const metadata: Metadata = { title: "Privacy" };

export default function PrivacyPage() {
  return (
    <div className="container page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Privacy</p>
          <h1>Your camera images stay with you.</h1>
          <p className="lead">
            A plain description of what OcuSense and this website actually do with your data. If something here
            changes, this page changes with it.
          </p>
        </div>
        <LocalArt />
      </header>

      <section className="section-rule" aria-labelledby="device">
        <h2 id="device">What runs on your device</h2>
        <dl className="def">
          <dt>Camera demo (this website)</dt>
          <dd>
            The camera starts only after you press “Start camera”. Frames are analysed in your browser with MediaPipe
            and immediately discarded. No image, video or face landmark is uploaded, recorded or stored.
          </dd>
          <dt>Mac app</dt>
          <dd>
            Frames are analysed in memory on your Mac and thrown away; images are never saved or uploaded. The app
            saves the raw Eye Aspect Ratio of each frame (numbers only, with a time stamp) to files on your Mac, which
            you can switch off in its settings, and your personal calibration (a few numbers) so you only calibrate
            once. Session statistics are kept only until you quit the app.
          </dd>
        </dl>
      </section>

      <section className="section-rule" aria-labelledby="network">
        <h2 id="network">What the website downloads and stores</h2>
        <dl className="def">
          <dt>Network requests</dt>
          <dd>
            Your browser downloads this site’s pages, fonts, and — for the camera demo — the MediaPipe program files and
            the face model, all from this website. Images go the other way never: nothing is sent back.
          </dd>
          <dt>Demo data</dt>
          <dd>
            Sample-session data, break feedback and check-ins you enter in the demo live only in this tab’s memory. They
            disappear when you press “Reset demo”, reload, or close the tab. Nothing is saved to cookies, local storage
            or our servers.
          </dd>
          <dt>Cookies</dt>
          <dd>None for visitors. If you log in, the sign-in provider sets cookies that keep you logged in, and they are removed when you log out.</dd>
          <dt>Analytics and ads</dt>
          <dd>None. We don’t use analytics, advertising trackers or third-party embeds.</dd>
        </dl>
      </section>

      <section className="section-rule" aria-labelledby="accounts">
        <h2 id="accounts">Accounts</h2>
        <p className="prose">
          Accounts are handled by Supabase Auth, a managed sign-in service. It stores your email address, a securely
          hashed password, and sign-in times. We don’t see your password. Your account page shows only this account
          information: eye measurements and check-ins are <b>not</b> uploaded to your account, and there is no cloud sync.
          Accounts are optional — the demo works without one.
        </p>
      </section>

      <section className="section-rule prose" aria-labelledby="control">
        <h2 id="control">Staying in control</h2>
        <ul>
          <li><b>Stop the camera:</b> press “Stop camera” in the demo, or leave the page. The browser’s camera indicator turns off.</li>
          <li><b>Hidden tab:</b> the demo pauses itself when you switch tabs.</li>
          <li><b>Reset demo data:</b> press “Reset demo” in the sample session, or reload the page.</li>
          <li><b>Revoke access:</b> your browser’s site settings let you remove camera permission at any time.</li>
        </ul>
        <p className="muted">
          OcuSense is a student prototype, not a medical device. Measurements and pattern prompts are experimental and
          don’t diagnose tiredness, dry eye or anything else. See <Link href="/how-it-works">how it works</Link>.
        </p>
      </section>
    </div>
  );
}
