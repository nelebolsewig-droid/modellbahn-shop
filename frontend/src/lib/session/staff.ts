"use client";

import { useQueryClient } from "@tanstack/react-query";

import {
  getGetStaffAccountQueryKey,
  useGetStaffAccount,
} from "@/lib/api/generated/admin-auth/admin-auth";
import type { StaffOut } from "@/lib/api/generated/model";

import { sessionFromQuery, type Session } from "./session";

export const staffAccountQueryKey = getGetStaffAccountQueryKey();

/** The logged-in staff member, as far as the API confirms it. */
export function useStaffSession(): Session<StaffOut> {
  return sessionFromQuery(useGetStaffAccount({ query: { staleTime: 60_000 } }));
}

export function useStaffSessionCache() {
  const queryClient = useQueryClient();
  return {
    store(account: StaffOut) {
      queryClient.setQueryData(staffAccountQueryKey, account);
    },
    async reset() {
      await queryClient.resetQueries({ queryKey: staffAccountQueryKey });
    },
    /** Asks the API again, e.g. when the live feed was refused. */
    async revalidate() {
      await queryClient.invalidateQueries({ queryKey: staffAccountQueryKey });
    },
  };
}
