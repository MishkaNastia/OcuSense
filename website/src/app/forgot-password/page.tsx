import type { Metadata } from "next";

import { AuthPage, authConfigured } from "@/components/auth/AuthPage";
import { ResetRequestForm } from "@/components/auth/AuthForms";

export const metadata: Metadata = { title: "Reset password" };

export default function ForgotPasswordPage() {
  return (
    <AuthPage eyebrow="Account" title="Reset your password" intro={<p>We’ll email you a link to choose a new password.</p>}>
      <ResetRequestForm configured={authConfigured()} />
    </AuthPage>
  );
}
