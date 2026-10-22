"use client";

import { useQuery } from "@tanstack/react-query";

import { getStaffAccount } from "@/lib/api/generated/admin-auth/admin-auth";
import type { StaffOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";

import {
  accountOrNull,
  SESSION_QUERY_ROOT,
  sessionFromQuery,
  useSessionCache,
  type Session,
  type SessionCache,
} from "./session";

export const staffSessionQueryKey = [...SESSION_QUERY_ROOT, "staff"] as const;

/** The logged-in staff member, as far as the API confirms it. */
export function useStaffSession(): Session<StaffOut> {
  const query = useQuery<StaffOut | null, ApiProblem>({
    queryKey: staffSessionQueryKey,
    queryFn: ({ signal }) => accountOrNull(getStaffAccount({ signal })),
    staleTime: 60_000,
  });
  return sessionFromQuery(query);
}

export function useStaffSessionCache(): SessionCache<StaffOut> {
  return useSessionCache<StaffOut>(staffSessionQueryKey);
}
