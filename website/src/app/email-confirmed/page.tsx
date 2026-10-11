import type { Metadata } from "next";
import Link from "next/link";

import { AuthPage } from "@/components/auth/AuthPage";

export const metadata: Metadata = { title: "Email confirmed", robots: { index: false } };

export default function EmailConfirmedPage() {
  return (
    <AuthPage eyebrow="Your OcuSense account" title="You’re in!"
      intro={<p>Your email address is confirmed. Go back to OcuSense and log in. Your username is waiting for you.</p>}>
      <p className="muted">
        Accounts live in the app: that’s where you log in, choose a username and climb the{" "}
        <Link href="/leaderboard">leaderboard</Link>.
      </p>
    </AuthPage>
  );
}
