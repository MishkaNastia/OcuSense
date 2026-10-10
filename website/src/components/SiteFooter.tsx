import Link from "next/link";

import { footerNav, mainNav, site } from "@/content/site";

import { LogoMark, Wordmark } from "./Logo";
import styles from "./SiteFooter.module.css";

export function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <div className={`container ${styles.grid}`}>
        <div className={styles.about}>
          <div className={styles.brand}>
            <LogoMark size={34} />
            <Wordmark size={22} />
          </div>
          <p className="muted">
            A hackathon project by computer science engineering, life sciences engineering and data science students. OcuSense is not a medical device
            and does not diagnose tiredness, dry eye or any other condition.
          </p>
        </div>
        <nav aria-label="Footer">
          <h2 className={styles.heading}>Explore</h2>
          <ul className={styles.list}>
            {mainNav.map((item) => <li key={item.href}><Link href={item.href}>{item.label}</Link></li>)}
          </ul>
        </nav>
        <nav aria-label="Policies">
          <h2 className={styles.heading}>Information</h2>
          <ul className={styles.list}>
            {footerNav.map((item) => <li key={item.href}><Link href={item.href}>{item.label}</Link></li>)}
            <li><a href={site.repositoryUrl} rel="noopener">Source code on GitHub</a></li>
            {site.contactEmail ? <li><a href={`mailto:${site.contactEmail}`}>Contact the team</a></li> : null}
          </ul>
        </nav>
      </div>
      <div className={`container ${styles.base}`}>
        <span>No analytics, no advertising trackers.</span>
        <span>Camera images in the demo are processed in your browser and never uploaded.</span>
      </div>
    </footer>
  );
}
