import { QueryClient } from "@tanstack/react-query";

import { isApiProblem } from "./problem";

const MAX_RETRIES = 2;

/** Only failures that may go away by themselves are worth another attempt. */
function isTransient(error: unknown): boolean {
  return !isApiProblem(error) || error.status === 0 || error.status >= 500;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
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
}
