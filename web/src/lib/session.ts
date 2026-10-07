/**
 * Where the sign-in token is kept.
 *
 * It lives in a normal cookie rather than an http-only one because both halves of the app need
 * it: pages read it on the server, and the forms call the API straight from the browser.
 */
export const TOKEN_COOKIE = "feedbacklens_token";

/** Matches the API's default token lifetime (AUTH_TOKEN_DAYS), so both expire together. */
const COOKIE_DAYS = 7;

export function readTokenInBrowser(): string | null {
  if (typeof document === "undefined") {
    return null;
  }
  const found = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${TOKEN_COOKIE}=`));
  return found ? decodeURIComponent(found.slice(TOKEN_COOKIE.length + 1)) : null;
}

export function storeToken(token: string): void {
  const maxAge = COOKIE_DAYS * 24 * 60 * 60;
  document.cookie = `${TOKEN_COOKIE}=${encodeURIComponent(token)}; path=/; max-age=${maxAge}; samesite=lax`;
}

export function clearToken(): void {
  document.cookie = `${TOKEN_COOKIE}=; path=/; max-age=0; samesite=lax`;
}
