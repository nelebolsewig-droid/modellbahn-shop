import { ApiProblem } from "./problem";

/*
 * The shop's catalogue pages render on the server and ask the API directly, inside
 * the stack (API_INTERNAL_URL, http://api:8000 in docker-compose.yml), instead of
 * going out through Caddy. Only for Server Components: the browser cannot reach it.
 */

const API_ORIGIN = process.env.API_INTERNAL_URL || "http://localhost:8000";
const STORE_PREFIX = "/api/v1/store";

type Params = Readonly<Record<string, string | undefined>>;

/** The URL of a store route with the given (non-empty) query parameters. */
export function storeUrl(path: string, params: Params = {}): URL {
  const url = new URL(`${STORE_PREFIX}${path}`, API_ORIGIN);
  for (const [name, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      url.searchParams.set(name, value);
    }
  }
  return url;
}

/**
 * GET a store route; null when the API answers 404 (unknown product or category).
 * Other failures are thrown as ApiProblem, for the page's error boundary.
 */
export async function fetchStore<T>(path: string, params: Params = {}): Promise<T | null> {
  let response: Response;
  try {
    // Prices and the gallery change in the admin area at any time; the API sends
    // Cache-Control for intermediaries, the page itself is rendered per request.
    response = await fetch(storeUrl(path, params), {
      headers: { Accept: "application/json, application/problem+json" },
      cache: "no-store",
    });
  } catch (error) {
    throw ApiProblem.network(error);
  }
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw await ApiProblem.fromResponse(response);
  }
  return (await response.json()) as T;
}
