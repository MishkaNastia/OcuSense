import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthPage, authConfigured } from "@/components/auth/AuthPage";
import { SignInForm } from "@/components/auth/AuthForms";
import { safeNext } from "@/lib/auth/validation";

export const metadata: Metadata = { title: "Log in" };

const LINK_ERRORS: Record<string, string> = {
  link: "That link has expired or was already used. Please log in, or request a new link.",
  "not-configured": "Accounts aren’t set up on this copy of the website yet.",
};

/** Reads ?next= and ?error= at request time; everything around it is prerendered. */
async function LoginContent({ searchParams }: Pick<PageProps<"/login">, "searchParams">) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : undefined);
  const error = typeof params.error === "string" ? LINK_ERRORS[params.error] : undefined;
  return (
    <>
      {error ? <p className="notice notice-attention" role="alert" style={{ marginBottom: 16 }}>{error}</p> : null}
      <SignInForm next={next} configured={authConfigured()} />
    </>
  );
}

export default function LoginPage(props: PageProps<"/login">) {
  return (
    <AuthPage eyebrow="Account" title="Log in" intro={<p>Your OcuSense account. The demo and downloads don’t need one.</p>}>
      <Suspense fallback={<SignInForm configured={authConfigured()} />}>
        <LoginContent searchParams={props.searchParams} />
      </Suspense>
    </AuthPage>
  );
}
