import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";

import { createAuthClient } from "@/lib/auth/server";
import { safeNext } from "@/lib/auth/validation";

/**
 * Where links in Supabase emails land (confirm email, reset password).
 * Supports both link styles: `?code=` (PKCE, the default) and `?token_hash=&type=`.
 */
export async function GET(request: NextRequest) {
  const url = request.nextUrl;
  const next = safeNext(url.searchParams.get("next"));
  const fail = (reason: string) => NextResponse.redirect(new URL(`/login?error=${reason}`, url.origin));

  const supabase = await createAuthClient();
  if (!supabase) return fail("not-configured");

  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");
  const type = url.searchParams.get("type") as EmailOtpType | null;
  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) return fail("link");
  } else if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    if (error) return fail("link");
  } else {
    return fail("link");
  }
  return NextResponse.redirect(new URL(next, url.origin));
}
