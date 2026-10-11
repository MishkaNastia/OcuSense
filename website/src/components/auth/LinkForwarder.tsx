"use client";

import { useEffect } from "react";

/**
 * Links in Supabase emails land on the website's main address with the details after
 * the "#". This sends them to the right page: a password reset to /update-password,
 * a confirmed sign-up to /email-confirmed. Everything else is left alone.
 */
export function LinkForwarder() {
  useEffect(() => {
    const hash = window.location.hash;
    if (!hash || window.location.pathname === "/update-password") return;
    const params = new URLSearchParams(hash.slice(1));
    const type = params.get("type");
    if (type === "recovery" || (params.get("error_code") && window.location.pathname === "/")) {
      window.location.replace(`/update-password${hash}`);
    } else if (type === "signup" || type === "email_change" || type === "invite" || type === "magiclink") {
      window.history.replaceState(null, "", window.location.pathname);  // no sign-in tokens left in the address bar
      window.location.replace("/email-confirmed");
    }
  }, []);
  return null;
}
