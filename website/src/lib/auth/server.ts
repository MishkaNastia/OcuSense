import "server-only";

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { authConfig } from "./config";

/** A Supabase client for Server Components, Server Actions and Route Handlers (null when not configured). */
export async function createAuthClient() {
  const config = authConfig();
  if (!config) return null;
  const cookieStore = await cookies();
  return createServerClient(config.url, config.key, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (toSet) => {
        try {
          toSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
        } catch {
          // Called from a Server Component, where cookies are read-only. The proxy refreshes sessions instead.
        }
      },
    },
  });
}
