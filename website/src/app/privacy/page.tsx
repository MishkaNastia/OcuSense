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
          <h1>Your face stays on your computer.</h1>
          <p className="lead">
            What OcuSense and this website actually do with your data, in plain words. If something changes, this page
            changes with it.
          </p>
        </div>
        <LocalArt />
      </header>

      <section className="section-rule" aria-labelledby="device">
        <h2 id="device">What runs on your device</h2>
        <dl className="def">
          <dt>Camera demo (this website)</dt>
          <dd>
            The camera starts only after you press “Start camera”. Frames are analysed in your browser by a face tracking model
            and immediately discarded. No image, video or face landmark is uploaded, recorded or stored.
          </dd>
          <dt>Desktop app</dt>
          <dd>
            Frames are analysed in memory on your computer and thrown away; images are never saved or uploaded. The
            app saves numbers only, on your computer: your personal calibration (so you calibrate once), your settings,
            your garden and gallery, your time log, your game scores, and (unless you switch it off) the Eye Aspect
            Ratio of each frame with a time stamp. Session statistics are kept until you quit the app. Posture is shown
            live and never saved.
          </dd>
        </dl>
      </section>

      <section className="section-rule" aria-labelledby="network">
        <h2 id="network">What the website downloads and stores</h2>
        <dl className="def">
          <dt>Network requests</dt>
          <dd>
            Your browser downloads this site’s pages and fonts, and for the camera demo the face tracking program files and
            model, all from this website. Nothing goes the other way: no images are sent back.
          </dd>
          <dt>Demo data</dt>
          <dd>
            The sample session and the camera demo keep everything in this tab’s memory only. It disappears when you press
            “Reset demo”, reload, or close the tab. Nothing is saved to cookies, local storage
            or our servers.
          </dd>
          <dt>Cookies</dt>
          <dd>None for visitors: the website has no login. The only exception is the page a password reset email
            opens, which keeps a sign-in cookie while you choose your new password and removes it straight after.</dd>
          <dt>Analytics and ads</dt>
          <dd>None. We don’t use analytics, advertising trackers or third-party embeds.</dd>
        </dl>
      </section>

      <section className="section-rule" aria-labelledby="accounts">
        <h2 id="accounts">Accounts</h2>
        <p className="prose">
          Accounts are handled by Supabase Auth, a managed sign-in service. It stores your email address, a securely
          hashed password and sign-in times. We don’t see your password. If you use the leaderboards in the app, your account also holds a username, your game scores and your friends
          list. Your username and best scores are public on the <Link href="/leaderboard">leaderboard</Link>; your friends
          list is visible only to you and your friends. Eye measurements are <b>never</b> uploaded, and there is no
          cloud sync. You create and use your account in the app; it’s optional, and the app and the demo work without one.
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
          OcuSense is a student project, not a medical device. Its measurements and reminders don’t diagnose tiredness,
          dry eye or anything else. See <Link href="/how-it-works">how it works</Link>.
        </p>
      </section>
    </div>
  );
}
