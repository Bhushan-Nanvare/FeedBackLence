import "server-only";

import { cookies } from "next/headers";

import * as api from "./api";
import { TOKEN_COOKIE } from "./session";

/** The token of whoever is signed in on this request, if anyone is. */
export async function sessionToken(): Promise<string | null> {
  return (await cookies()).get(TOKEN_COOKIE)?.value ?? null;
}

/** Null when nobody is signed in, the token has expired, or the API cannot be reached. */
export async function currentUser(): Promise<api.AuthUser | null> {
  const token = await sessionToken();
  if (!token) {
    return null;
  }
  try {
    return await api.getMe(token);
  } catch {
    return null;
  }
}

export async function getItems(slug: string, filters: URLSearchParams) {
  return api.getItems(slug, filters, await sessionToken());
}

export async function getProductAreas(slug: string) {
  return api.getProductAreas(slug, await sessionToken());
}

export async function getThemes(slug: string, params: URLSearchParams) {
  return api.getThemes(slug, params, await sessionToken());
}

export async function getTheme(slug: string, themeId: number) {
  return api.getTheme(slug, themeId, await sessionToken());
}

export async function getAlerts(slug: string, limit = 5) {
  return api.getAlerts(slug, limit, await sessionToken());
}

export async function getMembers(slug: string) {
  return api.getMembers(slug, await sessionToken());
}

/** Server-side wrapper: reads the cookie and fetches AI usage for the workspace. */
export async function getUsage(slug: string, days = 30) {
  return api.getUsage(slug, days, await sessionToken());
}
