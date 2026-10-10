import Link from "next/link";
import type { ReactNode } from "react";

import { QuietArt } from "@/components/art/Art";
import { isAuthConfigured } from "@/lib/auth/config";

import styles from "./Auth.module.css";

/** Shared layout for the account pages, including the honest "not set up yet" notice. */
export function AuthPage({ eyebrow, title, intro, children }: { eyebrow: string; title: string; intro: ReactNode; children: ReactNode }) {
  const configured = isAuthConfigured();
  return (
    <div className={`container ${styles.layout}`}>
      <div className={styles.intro}>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <div className="lead">{intro}</div>
        {!configured ? (
          <div className="notice notice-attention" role="note">
            <b>Accounts aren’t set up on this copy of the website yet.</b> The forms are shown so you can see the flow, but
            nothing can be submitted until the sign-in service is configured (see the website README). Everything else —
            including the <Link href="/demo">demo</Link> — works without an account.
          </div>
        ) : null}
        <QuietArt />
      </div>
      <div>{children}</div>
    </div>
  );
}

export const authConfigured = isAuthConfigured;
