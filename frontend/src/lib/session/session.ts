import { useQueryClient, type QueryKey, type UseQueryResult } from "@tanstack/react-query";
import { useMemo } from "react";

import { isSessionMissing, type ApiProblem } from "@/lib/api/problem";

/** Prefix of the session queries; invalidating it re-checks every login. */
export const SESSION_QUERY_ROOT = ["session"] as const;

/**
 * What the UI knows about a login. Derived from the API's /me answer only: the
 * presence of a session cookie proves nothing (it may be expired or revoked).
 */
export type Session<TAccount> =
  | { status: "loading" }
  | { status: "authenticated"; account: TAccount }
  | { status: "anonymous" }
  | { status: "error"; error: ApiProblem };

/**
 * Resolves the /me request to the account, or to null when there is no valid
 * session. Not being logged in is an expected answer, not a failure: it must not
 * be retried, and it lets a logout set the state directly (see useSessionCache).
 */
export async function accountOrNull<TAccount>(request: Promise<TAccount>): Promise<TAccount | null> {
  try {
    return await request;
  } catch (error) {
    if (isSessionMissing(error)) {
      return null;
    }
    throw error;
  }
}

export function sessionFromQuery<TAccount>(
  query: UseQueryResult<TAccount | null, ApiProblem>,
): Session<TAccount> {
  // Data wins over a failed refetch: a network hiccup does not log anybody out.
  if (query.data === null) {
    return { status: "anonymous" };
  }
  if (query.data !== undefined) {
    return { status: "authenticated", account: query.data };
  }
  if (query.isError) {
    return { status: "error", error: query.error };
  }
  return { status: "loading" };
}

export type SessionCache<TAccount> = {
  /** After login, verification or a change: the API's answer is the new state. */
  store(account: TAccount): void;
  /** After logout or deletion: the visitor is anonymous, no need to ask the API. */
  clear(): void;
  /** Asks the API again, e.g. when the live feed was refused. */
  revalidate(): Promise<void>;
};

export function useSessionCache<TAccount>(queryKey: QueryKey): SessionCache<TAccount> {
  const queryClient = useQueryClient();
  return useMemo(
    () => ({
      store(account) {
        queryClient.setQueryData<TAccount | null>(queryKey, account);
      },
      clear() {
        queryClient.setQueryData<TAccount | null>(queryKey, null);
      },
      revalidate() {
        return queryClient.invalidateQueries({ queryKey });
      },
    }),
    [queryClient, queryKey],
  );
}
