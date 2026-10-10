import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { AuthPage } from "@/components/auth/AuthPage";
import { signOutAction } from "@/lib/auth/actions";
import { createAuthClient } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Your account" };

const when = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }) + " UTC" : "—";

export default function AccountPage(props: PageProps<"/account">) {
  return (
    <Suspense fallback={<div className="container page"><p role="status">Checking your session…</p></div>}>
      <AccountContent searchParams={props.searchParams} />
    </Suspense>
  );
}

/** Protected content: the session is checked with Supabase on the server for every request. */
async function AccountContent({ searchParams }: Pick<PageProps<"/account">, "searchParams">) {
  const supabase = await createAuthClient();
  if (!supabase) {
    return (
      <AuthPage eyebrow="Account" title="Your account" intro={<p>Accounts aren’t available yet.</p>}>
        <p>Nothing to show — please use the <Link href="/demo">demo</Link>, which needs no account.</p>
      </AuthPage>
    );
  }
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) redirect("/login?next=/account");
  const user = data.user;
  const params = await searchParams;

  return (
    <div className="container page">
      <header className="prose">
        <p className="eyebrow">Account</p>
        <h1>Your account</h1>
        {params.updated ? <p className="notice" role="status">Your password was changed.</p> : null}
      </header>
      <section className="section-rule" aria-labelledby="details">
        <h2 id="details">Account details</h2>
        <dl className="def">
          <dt>Email</dt><dd>{user.email}</dd>
          <dt>Email confirmed</dt><dd>{user.email_confirmed_at ? when(user.email_confirmed_at) : "Not yet — check your inbox"}</dd>
          <dt>Account created</dt><dd>{when(user.created_at)}</dd>
          <dt>Last sign-in</dt><dd>{when(user.last_sign_in_at)}</dd>
        </dl>
        <p className="muted">
          That’s everything stored for this account. Eye measurements, check-ins and break history are not uploaded —
          there is no cloud sync.
        </p>
        <form action={signOutAction}>
          <button type="submit" className="btn btn-secondary">Log out</button>
        </form>
      </section>
      <section className="section-rule" aria-labelledby="next">
        <h2 id="next">Where next</h2>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          <Link href="/demo" className="btn btn-primary">Open the demo</Link>
          <Link href="/download" className="btn btn-secondary">Get the Mac app</Link>
          <Link href="/forgot-password" className="btn btn-quiet">Change password</Link>
        </div>
      </section>
    </div>
  );
}
