import type { UseQueryResult } from "@tanstack/react-query";

import { isUnauthenticated, type ApiProblem } from "@/lib/api/problem";

/**
 * What the UI knows about a login. Derived from the API's /me answer only: the
 * presence of a session cookie proves nothing (it may be expired or revoked).
 */
export type Session<TAccount> =
  | { status: "loading" }
  | { status: "authenticated"; account: TAccount }
  | { status: "anonymous" }
  | { status: "error"; error: ApiProblem };

export function sessionFromQuery<TAccount>(
  query: UseQueryResult<TAccount, ApiProblem>,
): Session<TAccount> {
  // Checked first: a 401 on refetch means the session has ended, even if the
  // cache still holds the account from before.
  if (isUnauthenticated(query.error)) {
    return { status: "anonymous" };
  }
  if (query.data !== undefined) {
    return { status: "authenticated", account: query.data };
  }
  if (query.error) {
    return { status: "error", error: query.error };
  }
  return { status: "loading" };
}
