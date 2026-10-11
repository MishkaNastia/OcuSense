import { describe, expect, it } from "vitest";

import { friendlyAuthError, safeNext, validateConfirm, validateEmail, validatePassword } from "../validation";

describe("account form checks", () => {
  it("validates email addresses", () => {
    expect(validateEmail("")).toBeDefined();
    expect(validateEmail("not-an-email")).toBeDefined();
    expect(validateEmail("student@example.com")).toBeUndefined();
  });

  it("validates passwords and confirmation", () => {
    expect(validatePassword("short")).toBeDefined();
    expect(validatePassword("long enough")).toBeUndefined();
    expect(validatePassword("x".repeat(73))).toBeDefined();
    expect(validateConfirm("abcdefgh", "abcdefgx")).toBeDefined();
    expect(validateConfirm("abcdefgh", "abcdefgh")).toBeUndefined();
  });

  it("only redirects within this site", () => {
    expect(safeNext("/update-password")).toBe("/update-password");
    expect(safeNext("/update-password")).toBe("/update-password");
    expect(safeNext("https://evil.example")).toBe("/email-confirmed");
    expect(safeNext("//evil.example")).toBe("/email-confirmed");
    expect(safeNext("/\\evil.example")).toBe("/email-confirmed");
    expect(safeNext(null)).toBe("/email-confirmed");
  });

  it("explains provider errors without leaking details", () => {
    expect(friendlyAuthError("Invalid login credentials")).toMatch(/incorrect/);
    expect(friendlyAuthError("Email not confirmed")).toMatch(/confirm/);
    expect(friendlyAuthError("weird internal error 500")).toBe("Something went wrong. Please try again.");
  });
});
