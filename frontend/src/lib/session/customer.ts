"use client";

import { useQueryClient } from "@tanstack/react-query";

import {
  getGetCustomerAccountQueryKey,
  useGetCustomerAccount,
} from "@/lib/api/generated/store-account/store-account";
import type { AccountOut } from "@/lib/api/generated/model";

import { sessionFromQuery, type Session } from "./session";

export const customerAccountQueryKey = getGetCustomerAccountQueryKey();

/** The logged-in customer, as far as the API confirms it. */
export function useCustomerSession(): Session<AccountOut> {
  return sessionFromQuery(useGetCustomerAccount({ query: { staleTime: 60_000 } }));
}

/** Keeps the cached customer in step with logins, logouts and changes. */
export function useCustomerSessionCache() {
  const queryClient = useQueryClient();
  return {
    /** After login, verification or a change: the API's answer is the new state. */
    store(account: AccountOut) {
      queryClient.setQueryData(customerAccountQueryKey, account);
    },
    /** After logout or deletion: forget the account and ask the API again. */
    async reset() {
      await queryClient.resetQueries({ queryKey: customerAccountQueryKey });
    },
  };
}
