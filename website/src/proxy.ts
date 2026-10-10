import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { authConfig } from "@/lib/auth/config";

/**
 * Keeps a logged-in session fresh on the pages that need it (Next.js 16 "proxy",
 * formerly middleware). Only runs on account pages, so the public site stays static.
 */
export async function proxy(request: NextRequest) {
  const config = authConfig();
  let response = NextResponse.next({ request });
  if (!config) return response;
  const supabase = createServerClient(config.url, config.key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (toSet, headers) => {
        toSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        toSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        Object.entries(headers ?? {}).forEach(([key, value]) => response.headers.set(key, value));
      },
    },
  });
  await supabase.auth.getUser(); // validates the session with Supabase and refreshes cookies if needed
  return response;
}

export const config = {
  matcher: ["/account/:path*", "/update-password"],
};
