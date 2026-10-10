/**
 * Supabase Auth configuration, read from environment variables (see .env.example).
 * Only public values are used: the project URL and the publishable (anon) key.
 * The service-role / secret key is never needed by this website.
 */

export interface AuthConfig {
  url: string;
  key: string;
}

export function authConfig(): AuthConfig | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = (process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)?.trim();
  if (!url || !key || !/^https:\/\//.test(url)) return null;
  return { url, key };
}

export const isAuthConfigured = () => authConfig() !== null;
