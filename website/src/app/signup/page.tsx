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
          An account holds your email address and sign-in details, plus a username and game scores if you use the
          leaderboards in the app. Eye measurements are never uploaded to it.
        </p>
      }
    >
      <SignUpForm configured={authConfigured()} />
    </AuthPage>
  );
}
