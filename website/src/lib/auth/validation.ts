/** Form checks shared by the account pages (pure functions, unit-tested). */

export interface FormState {
  status: "idle" | "error" | "success";
  message: string;
  fieldErrors?: Partial<Record<"email" | "password" | "confirm", string>>;
  email?: string;
}

export const IDLE: FormState = { status: "idle", message: "" };

export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_LENGTH = 72; // bcrypt limit used by Supabase Auth

export function validateEmail(email: string): string | undefined {
  if (!email) return "Enter your email address.";
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return "Enter a valid email address, like name@example.com.";
  return undefined;
}

export function validatePassword(password: string): string | undefined {
  if (password.length < MIN_PASSWORD_LENGTH) return `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (password.length > MAX_PASSWORD_LENGTH) return `Use at most ${MAX_PASSWORD_LENGTH} characters.`;
  return undefined;
}

export function validateConfirm(password: string, confirm: string): string | undefined {
  return password === confirm ? undefined : "The two passwords don’t match.";
}

/** Only allow redirects to paths on this site (never to another website). */
export function safeNext(next: string | null | undefined, fallback = "/email-confirmed"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  return next;
}

/** Friendly wording for errors returned by the sign-in provider. */
export function friendlyAuthError(message: string | undefined): string {
  const m = (message ?? "").toLowerCase();
  if (m.includes("invalid login credentials")) return "Email or password is incorrect.";
  if (m.includes("email not confirmed")) return "Please confirm your email first — check your inbox for the link we sent.";
  if (m.includes("rate limit") || m.includes("too many")) return "Too many attempts. Please wait a few minutes and try again.";
  if (m.includes("password") && m.includes("weak")) return "That password is too easy to guess. Try a longer one.";
  if (m.includes("same") && m.includes("password")) return "Choose a password different from your current one.";
  if (m.includes("fetch") || m.includes("network")) return "We couldn’t reach the sign-in service. Check your connection and try again.";
  return "Something went wrong. Please try again.";
}
