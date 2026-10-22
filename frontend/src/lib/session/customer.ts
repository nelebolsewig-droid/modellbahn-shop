"use client";

import { useQuery } from "@tanstack/react-query";

import type { AccountOut } from "@/lib/api/generated/model";
import { getCustomerAccount } from "@/lib/api/generated/store-account/store-account";
import type { ApiProblem } from "@/lib/api/problem";

import {
  accountOrNull,
  SESSION_QUERY_ROOT,
  sessionFromQuery,
  useSessionCache,
  type Session,
  type SessionCache,
} from "./session";

export const customerSessionQueryKey = [...SESSION_QUERY_ROOT, "customer"] as const;

/** The logged-in customer, as far as the API confirms it. */
export function useCustomerSession(): Session<AccountOut> {
  const query = useQuery<AccountOut | null, ApiProblem>({
    queryKey: customerSessionQueryKey,
    queryFn: ({ signal }) => accountOrNull(getCustomerAccount({ signal })),
    staleTime: 60_000,
  });
  return sessionFromQuery(query);
}

/** Keeps the cached customer in step with logins, logouts and changes. */
export function useCustomerSessionCache(): SessionCache<AccountOut> {
  return useSessionCache<AccountOut>(customerSessionQueryKey);
}
