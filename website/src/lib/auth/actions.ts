"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { createAuthClient } from "./server";
import {
  friendlyAuthError, safeNext, validateConfirm, validateEmail, validatePassword, type FormState,
} from "./validation";

const NOT_CONFIGURED: FormState = {
  status: "error",
  message: "Accounts aren’t set up on this copy of the website yet. The demo works without an account.",
};

async function siteOrigin(): Promise<string> {
  const configured = process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "");
  if (configured) return configured;
  const h = await headers();
  const origin = h.get("origin");
  if (origin) return origin;
  const host = h.get("x-forwarded-host") ?? h.get("host");
  const proto = h.get("x-forwarded-proto") ?? "http";
  return `${proto}://${host}`;
}

const text = (form: FormData, name: string) => String(form.get(name) ?? "").trim();

export async function signUpAction(_prev: FormState, form: FormData): Promise<FormState> {
  const email = text(form, "email").toLowerCase();
  const password = String(form.get("password") ?? "");
  const confirm = String(form.get("confirm") ?? "");
  const fieldErrors = { email: validateEmail(email), password: validatePassword(password), confirm: validateConfirm(password, confirm) };
  if (fieldErrors.email || fieldErrors.password || fieldErrors.confirm) {
    return { status: "error", message: "Please check the highlighted fields.", fieldErrors, email };
  }
  const supabase = await createAuthClient();
  if (!supabase) return { ...NOT_CONFIGURED, email };
  const { data, error } = await supabase.auth.signUp({
    email, password, options: { emailRedirectTo: `${await siteOrigin()}/auth/callback?next=/account` },
  });
  if (error) return { status: "error", message: friendlyAuthError(error.message), email };
  if (data.session) redirect("/account"); // email confirmation is switched off in this Supabase project
  return {
    status: "success",
    message: "Almost there — we’ve sent a confirmation link to that address. Open it to activate your account, then log in.",
    email,
  };
}

export async function signInAction(_prev: FormState, form: FormData): Promise<FormState> {
  const email = text(form, "email").toLowerCase();
  const password = String(form.get("password") ?? "");
  const emailError = validateEmail(email);
  if (emailError || !password) {
    return { status: "error", message: "Please check the highlighted fields.", fieldErrors: { email: emailError, password: password ? undefined : "Enter your password." }, email };
  }
  const supabase = await createAuthClient();
  if (!supabase) return { ...NOT_CONFIGURED, email };
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) return { status: "error", message: friendlyAuthError(error.message), email };
  redirect(safeNext(text(form, "next")));
}

export async function signOutAction(): Promise<void> {
  const supabase = await createAuthClient();
  if (supabase) await supabase.auth.signOut();
  redirect("/");
}

export async function requestResetAction(_prev: FormState, form: FormData): Promise<FormState> {
  const email = text(form, "email").toLowerCase();
  const emailError = validateEmail(email);
  if (emailError) return { status: "error", message: "Please check the highlighted field.", fieldErrors: { email: emailError }, email };
  const supabase = await createAuthClient();
  if (!supabase) return { ...NOT_CONFIGURED, email };
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${await siteOrigin()}/auth/callback?next=/update-password`,
  });
  if (error && /rate limit|too many/i.test(error.message)) return { status: "error", message: friendlyAuthError(error.message), email };
  // Same message whether or not an account exists, so nobody can probe which emails are registered.
  return { status: "success", message: "If an account exists for that address, we’ve sent a link to choose a new password.", email };
}

export async function updatePasswordAction(_prev: FormState, form: FormData): Promise<FormState> {
  const password = String(form.get("password") ?? "");
  const confirm = String(form.get("confirm") ?? "");
  const fieldErrors = { password: validatePassword(password), confirm: validateConfirm(password, confirm) };
  if (fieldErrors.password || fieldErrors.confirm) return { status: "error", message: "Please check the highlighted fields.", fieldErrors };
  const supabase = await createAuthClient();
  if (!supabase) return NOT_CONFIGURED;
  const { data } = await supabase.auth.getUser();
  if (!data.user) return { status: "error", message: "Your reset link has expired or was already used. Request a new one." };
  const { error } = await supabase.auth.updateUser({ password });
  if (error) return { status: "error", message: friendlyAuthError(error.message) };
  redirect("/account?updated=1");
}
