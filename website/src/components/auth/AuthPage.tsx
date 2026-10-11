import Link from "next/link";
import type { ReactNode } from "react";

import { QuietArt } from "@/components/art/Art";
import { isAuthConfigured } from "@/lib/auth/config";

import styles from "./Auth.module.css";

/** Layout for the pages that links in account emails open (new password, email confirmed). */
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
            <b>Accounts aren’t set up on this copy of the website yet.</b> Everything else, including the{" "}
            <Link href="/demo">demo</Link>, works without them.
          </div>
        ) : null}
        <QuietArt />
      </div>
      <div>{children}</div>
    </div>
  );
}

export const authConfigured = isAuthConfigured;
