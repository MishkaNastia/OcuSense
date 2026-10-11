import type { Metadata } from "next";

import { AuthPage } from "@/components/auth/AuthPage";
import { PasswordReset } from "@/components/auth/PasswordReset";
import { authConfig } from "@/lib/auth/config";

export const metadata: Metadata = { title: "Choose a new password", robots: { index: false } };

export default function UpdatePasswordPage() {
  const config = authConfig();
  return (
    <AuthPage eyebrow="Your OcuSense account" title="Choose a new password"
      intro={<p>You opened a password reset link from OcuSense. Pick a new password, then log in again in the app.</p>}>
      <PasswordReset url={config?.url ?? null} publishableKey={config?.key ?? null} />
    </AuthPage>
  );
}
