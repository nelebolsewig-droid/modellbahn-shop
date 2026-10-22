import { MutationCache, QueryClient } from "@tanstack/react-query";

import { isApiProblem, isSessionMissing } from "@/lib/api/problem";
import { SESSION_QUERY_ROOT } from "@/lib/session/session";

const MAX_RETRIES = 2;

/** Only failures that may go away by themselves are worth another attempt. */
function isTransient(error: unknown): boolean {
  return !isApiProblem(error) || error.status === 0 || error.status >= 500;
}

export function createQueryClient(): QueryClient {
  const queryClient: QueryClient = new QueryClient({
    // A change that fails with "not logged in" means the session ended in the
    // meantime (expired, or revoked from another device). Re-checking the sessions
    // lets the protected pages notice it and send the visitor to the login page.
    mutationCache: new MutationCache({
      onError(error) {
        if (isSessionMissing(error)) {
          void queryClient.invalidateQueries({ queryKey: SESSION_QUERY_ROOT });
        }
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount, error) => failureCount < MAX_RETRIES && isTransient(error),
      },
      mutations: {
        // Mutations change state; repeating one is the user's decision.
        retry: false,
      },
    },
  });
  return queryClient;
}
