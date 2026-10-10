import type { Metadata } from "next";

import { AuthPage, authConfigured } from "@/components/auth/AuthPage";
import { UpdatePasswordForm } from "@/components/auth/AuthForms";

export const metadata: Metadata = { title: "Choose a new password" };

export default function UpdatePasswordPage() {
  return (
    <AuthPage eyebrow="Account" title="Choose a new password" intro={<p>You opened a password-reset link. Pick a new password for your account.</p>}>
      <UpdatePasswordForm configured={authConfigured()} />
    </AuthPage>
  );
}
