import type { Metadata } from "next";

import { AuthPage, authConfigured } from "@/components/auth/AuthPage";
import { SignUpForm } from "@/components/auth/AuthForms";

export const metadata: Metadata = { title: "Create account" };

export default function SignUpPage() {
  return (
    <AuthPage
      eyebrow="Account"
      title="Create an account"
      intro={
        <p>
          An account holds only your email address and sign-in details. Eye measurements and check-ins are never
          uploaded to it.
        </p>
      }
    >
      <SignUpForm configured={authConfigured()} />
    </AuthPage>
  );
}
