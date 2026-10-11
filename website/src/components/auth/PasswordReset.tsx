"use client";

import { createBrowserClient } from "@supabase/ssr";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { MIN_PASSWORD_LENGTH, friendlyAuthError, validateConfirm, validatePassword } from "@/lib/auth/validation";

import styles from "./Auth.module.css";

type Stage = "checking" | "ready" | "saving" | "done" | "expired" | "not-set-up";

/**
 * Where a "reset your password" email from the app lands.
 *
 * The app asks Supabase for the email; its link comes back here with the sign-in
 * tokens after the "#" (only the browser can read that part), or as a session the
 * /auth/callback route already set. The new password goes straight to Supabase;
 * this site never sees or stores it.
 */
export function PasswordReset({ url, publishableKey }: { url: string | null; publishableKey: string | null }) {
  const supabase = useMemo(() => (url && publishableKey ? createBrowserClient(url, publishableKey) : null), [url, publishableKey]);
  const [stage, setStage] = useState<Stage>(supabase ? "checking" : "not-set-up");
  const [message, setMessage] = useState("");
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>({});

  useEffect(() => {
    if (!supabase) return;
    let cancelled = false;
    (async () => {
      const hash = new URLSearchParams(window.location.hash.slice(1));
      const access_token = hash.get("access_token");
      const refresh_token = hash.get("refresh_token");
      const linkError = hash.get("error_description") || new URLSearchParams(window.location.search).get("error");
      if (hash.size) window.history.replaceState(null, "", window.location.pathname);  // keep tokens out of the address bar
      if (access_token && refresh_token) {
        const { error } = await supabase.auth.setSession({ access_token, refresh_token });
        if (!cancelled) setStage(error ? "expired" : "ready");
        return;
      }
      const { data } = await supabase.auth.getSession();
      if (!cancelled) setStage(data.session && !linkError ? "ready" : "expired");
    })();
    return () => { cancelled = true; };
  }, [supabase]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) return;
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const confirm = String(form.get("confirm") ?? "");
    const found = { password: validatePassword(password), confirm: validateConfirm(password, confirm) };
    setErrors(found);
    if (found.password || found.confirm) return;
    setStage("saving");
    const { error } = await supabase.auth.updateUser({ password });
    if (error) {
      setMessage(friendlyAuthError(error.message));
      setStage("ready");
      return;
    }
    await supabase.auth.signOut();  // nothing stays signed in on this website
    setStage("done");
  }

  if (stage === "not-set-up") {
    return <p className="notice">Accounts aren’t set up on this copy of the website yet.</p>;
  }
  if (stage === "checking") return <p role="status">Checking your link…</p>;
  if (stage === "expired") {
    return (
      <div className="notice notice-attention" role="alert">
        <b>This link has expired or was already used.</b> Ask for a new one in OcuSense: Log in › Forgot password?
      </div>
    );
  }
  if (stage === "done") {
    return (
      <div className={styles.success} role="status">
        Password changed. Go back to OcuSense and log in with your new password.
      </div>
    );
  }
  return (
    <form onSubmit={save} className={styles.form} noValidate>
      <div className="field">
        <label htmlFor="password">New password</label>
        <input id="password" name="password" type="password" autoComplete="new-password" required
          aria-invalid={errors.password ? true : undefined} aria-describedby="password-hint" />
        <span id="password-hint" className="hint">At least {MIN_PASSWORD_LENGTH} characters.</span>
        {errors.password ? <span className="field-error">{errors.password}</span> : null}
      </div>
      <div className="field">
        <label htmlFor="confirm">Repeat new password</label>
        <input id="confirm" name="confirm" type="password" autoComplete="new-password" required
          aria-invalid={errors.confirm ? true : undefined} />
        {errors.confirm ? <span className="field-error">{errors.confirm}</span> : null}
      </div>
      {message ? <div className={styles.error} role="alert">{message}</div> : null}
      <button type="submit" className="btn btn-primary" disabled={stage === "saving"}>
        {stage === "saving" ? "Saving…" : "Save new password"}
      </button>
    </form>
  );
}
