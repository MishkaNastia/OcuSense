"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { mainNav } from "@/content/site";

import { LogoMark, Wordmark } from "./Logo";
import styles from "./SiteHeader.module.css";

export function SiteHeader() {
  const pathname = usePathname();
  // The mobile menu remembers which page it was opened on, so it closes by itself after navigating.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;

  const isCurrent = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header className={styles.header}>
      <div className={`container ${styles.bar}`}>
        <Link href="/" className={styles.brand} aria-label="OcuSense home">
          <LogoMark size={40} />
          <Wordmark size={25} />
        </Link>
        <button
          type="button"
          className={`btn btn-secondary btn-small ${styles.menuButton}`}
          aria-expanded={open}
          aria-controls="site-menu"
          onClick={() => setOpenOn(open ? null : pathname)}
        >
          {open ? "Close" : "Menu"}
        </button>
        <nav id="site-menu" aria-label="Main" className={`${styles.nav} ${open ? styles.open : ""}`}>
          <ul className={styles.links}>
            {mainNav.map((item) => (
              <li key={item.href}>
                <Link href={item.href} aria-current={isCurrent(item.href) ? "page" : undefined} className={styles.link}>
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
          <div className={styles.account}>
            <Link href="/login" className="btn btn-quiet btn-small">Log in</Link>
            <Link href="/signup" className="btn btn-secondary btn-small">Create account</Link>
          </div>
        </nav>
      </div>
    </header>
  );
}
