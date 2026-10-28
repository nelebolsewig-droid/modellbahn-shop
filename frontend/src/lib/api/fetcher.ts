import { ApiProblem } from "./problem";

/**
 * Every state-changing request must carry this header; the API rejects it otherwise
 * (403 `csrf_header_missing`, see docs/adr/0004). Browsers send custom headers
 * cross-site only after a CORS preflight, which the API never approves.
 */
export const CLIENT_HEADER = "X-Modellbahn-Client";
const CLIENT_HEADER_VALUE = "web";

const UNSAFE_METHODS: ReadonlySet<string> = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const ACCEPT = "application/json, application/problem+json";

/**
 * Error type of the generated hooks: whatever the OpenAPI document declares as the
 * error body, the fetcher throws an {@link ApiProblem}. Orval picks this export up
 * from the mutator file.
 */
export type ErrorType<_DeclaredBody> = ApiProblem;

/**
 * Fetch function behind every generated API call (the Orval "mutator").
 *
 * - URLs stay relative: the browser talks to its own origin (Caddy in production,
 *   the `next dev` rewrite in development), so the session cookies are first-party.
 * - Cookies are always sent; unsafe methods get the CSRF header.
 * - Non-2xx answers are thrown as {@link ApiProblem}; aborts are rethrown unchanged
 *   so that TanStack Query can tell a cancelled query from a failed one.
 */
export async function apiFetch<T>(url: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", ACCEPT);
  }
  if (UNSAFE_METHODS.has(method)) {
    headers.set(CLIENT_HEADER, CLIENT_HEADER_VALUE);
  }

  let response: Response;
  try {
    response = await fetch(url, { ...init, method, headers, credentials: "include" });
  } catch (error) {
    if (isAbort(error, init.signal)) {
      throw error;
    }
    throw ApiProblem.network(error);
  }

  if (!response.ok) {
    throw await ApiProblem.fromResponse(response);
  }
  return readBody<T>(response);
}

async function readBody<T>(response: Response): Promise<T> {
  // Labels come as PDF, the article list as CSV: those are handed over as they are.
  const type = response.headers.get("Content-Type") ?? "";
  if (type.startsWith("application/pdf")) {
    return (await response.blob()) as T;
  }
  if (type.startsWith("text/csv")) {
    return (await response.text()) as T;
  }
  // 202 and 200 carry JSON; 204 (logout, password change, ...) carries nothing.
  const text = await response.text();
  if (text === "") {
    return undefined as T;
  }
  try {
    return JSON.parse(text) as T;
  } catch (error) {
    throw ApiProblem.malformed(response, error);
  }
}

function isAbort(error: unknown, signal: AbortSignal | null | undefined): boolean {
  return signal?.aborted === true || (error instanceof DOMException && error.name === "AbortError");
}
