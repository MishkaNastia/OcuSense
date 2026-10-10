"use client";

import Link from "next/link";
import { useActionState } from "react";

import { requestResetAction, signInAction, signUpAction, updatePasswordAction } from "@/lib/auth/actions";
import { IDLE, MIN_PASSWORD_LENGTH, type FormState } from "@/lib/auth/validation";

import styles from "./Auth.module.css";

function Field({ name, label, type, state, autoComplete, hint, defaultValue }: {
  name: "email" | "password" | "confirm"; label: string; type: string; state: FormState;
  autoComplete: string; hint?: string; defaultValue?: string;
}) {
  const error = state.fieldErrors?.[name];
  const describedBy = [hint ? `${name}-hint` : null, error ? `${name}-error` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label htmlFor={name}>{label}</label>
      <input id={name} name={name} type={type} autoComplete={autoComplete} required defaultValue={defaultValue}
        aria-invalid={error ? true : undefined} aria-describedby={describedBy} />
      {hint ? <span id={`${name}-hint`} className="hint">{hint}</span> : null}
      {error ? <span id={`${name}-error`} className="field-error">{error}</span> : null}
    </div>
  );
}

function Message({ state }: { state: FormState }) {
  if (state.status === "idle") return <div role="status" aria-live="polite" />;
  return (
    <div role={state.status === "error" ? "alert" : "status"} className={state.status === "error" ? styles.error : styles.success}>
      {state.message}
    </div>
  );
}

function Submit({ pending, idle, busy, disabled }: { pending: boolean; idle: string; busy: string; disabled?: boolean }) {
  return (
    <button type="submit" className="btn btn-primary" disabled={pending || disabled} aria-disabled={pending || disabled}>
      {pending ? busy : idle}
    </button>
  );
}

export function SignInForm({ next, configured }: { next?: string; configured: boolean }) {
  const [state, action, pending] = useActionState(signInAction, IDLE);
  return (
    <form action={action} className={styles.form} noValidate>
      <input type="hidden" name="next" value={next ?? "/account"} />
      <Field name="email" label="Email" type="email" autoComplete="email" state={state} defaultValue={state.email} />
      <Field name="password" label="Password" type="password" autoComplete="current-password" state={state} />
      <Message state={state} />
      <Submit pending={pending} idle="Log in" busy="Logging in…" disabled={!configured} />
      <p className={styles.links}><Link href="/forgot-password">Forgot your password?</Link> · <Link href="/signup">Create an account</Link></p>
    </form>
  );
}

export function SignUpForm({ configured }: { configured: boolean }) {
  const [state, action, pending] = useActionState(signUpAction, IDLE);
  if (state.status === "success") return <Message state={state} />;
  return (
    <form action={action} className={styles.form} noValidate>
      <Field name="email" label="Email" type="email" autoComplete="email" state={state} defaultValue={state.email} />
      <Field name="password" label="Password" type="password" autoComplete="new-password" state={state}
        hint={`At least ${MIN_PASSWORD_LENGTH} characters.`} />
      <Field name="confirm" label="Repeat password" type="password" autoComplete="new-password" state={state} />
      <Message state={state} />
      <Submit pending={pending} idle="Create account" busy="Creating account…" disabled={!configured} />
      <p className={styles.links}>Already have an account? <Link href="/login">Log in</Link></p>
    </form>
  );
}

export function ResetRequestForm({ configured }: { configured: boolean }) {
  const [state, action, pending] = useActionState(requestResetAction, IDLE);
  if (state.status === "success") return <Message state={state} />;
  return (
    <form action={action} className={styles.form} noValidate>
      <Field name="email" label="Email" type="email" autoComplete="email" state={state} defaultValue={state.email} />
      <Message state={state} />
      <Submit pending={pending} idle="Send reset link" busy="Sending…" disabled={!configured} />
      <p className={styles.links}><Link href="/login">Back to log in</Link></p>
    </form>
  );
}

export function UpdatePasswordForm({ configured }: { configured: boolean }) {
  const [state, action, pending] = useActionState(updatePasswordAction, IDLE);
  return (
    <form action={action} className={styles.form} noValidate>
      <Field name="password" label="New password" type="password" autoComplete="new-password" state={state}
        hint={`At least ${MIN_PASSWORD_LENGTH} characters.`} />
      <Field name="confirm" label="Repeat new password" type="password" autoComplete="new-password" state={state} />
      <Message state={state} />
      <Submit pending={pending} idle="Save new password" busy="Saving…" disabled={!configured} />
    </form>
  );
}
