"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getEbayAccountDeletionSetup,
  getEbayStatus,
  listEbayCategories,
  listEbayListings,
  listEbayOrders,
  listEbayPolicies,
  listProductEbayListings,
} from "@/lib/api/generated/admin-marketplace/admin-marketplace";
import type {
  AccountDeletionSetupOut,
  CategoryMappingOut,
  EbayStatusOut,
  ListingOut,
  MarketplaceOrderOut,
  PoliciesOut,
} from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { useStaffSession } from "@/lib/session/staff";

export const EBAY_KEY = ["admin", "ebay"] as const;
const STATUS_KEY = [...EBAY_KEY, "status"] as const;
const POLICIES_KEY = [...EBAY_KEY, "policies"] as const;
const CATEGORIES_KEY = [...EBAY_KEY, "categories"] as const;
const LISTINGS_KEY = [...EBAY_KEY, "listings"] as const;
const ORDERS_KEY = [...EBAY_KEY, "orders"] as const;
const ACCOUNT_DELETION_KEY = [...EBAY_KEY, "account-deletion"] as const;

export function productListingsKey(productId: string) {
  return [...EBAY_KEY, "product", productId] as const;
}

// Listings and orders change in the background (the worker syncs every minute).
const LIVE = { refetchInterval: 15_000 } as const;

export function useEbayStatus() {
  return useQuery<EbayStatusOut, ApiProblem>({
    queryKey: STATUS_KEY,
    queryFn: ({ signal }) => getEbayStatus({ signal }),
  });
}

/** What eBay's developer account needs for its notifications of closed accounts. */
export function useAccountDeletionSetup() {
  return useQuery<AccountDeletionSetupOut, ApiProblem>({
    queryKey: ACCOUNT_DELETION_KEY,
    queryFn: ({ signal }) => getEbayAccountDeletionSetup({ signal }),
    staleTime: 5 * 60_000,
  });
}

export function useEbayPolicies(enabled: boolean) {
  return useQuery<PoliciesOut, ApiProblem>({
    queryKey: POLICIES_KEY,
    queryFn: ({ signal }) => listEbayPolicies({ signal }),
    enabled,
    staleTime: 5 * 60_000,
  });
}

export function useEbayCategories(enabled: boolean) {
  return useQuery<CategoryMappingOut[], ApiProblem>({
    queryKey: CATEGORIES_KEY,
    queryFn: async ({ signal }) => (await listEbayCategories({ signal })).items,
    enabled,
  });
}

export function useEbayListings(enabled: boolean) {
  return useQuery<ListingOut[], ApiProblem>({
    queryKey: LISTINGS_KEY,
    queryFn: async ({ signal }) => (await listEbayListings({ limit: 100 }, { signal })).items,
    enabled,
    ...LIVE,
  });
}

export function useEbayOrders(enabled: boolean) {
  return useQuery<MarketplaceOrderOut[], ApiProblem>({
    queryKey: ORDERS_KEY,
    queryFn: async ({ signal }) => (await listEbayOrders({ signal })).items,
    enabled,
    ...LIVE,
  });
}

export function useProductListings(productId: string, enabled: boolean) {
  return useQuery<ListingOut[], ApiProblem>({
    queryKey: productListingsKey(productId),
    queryFn: async ({ signal }) => (await listProductEbayListings(productId, { signal })).items,
    enabled,
    ...LIVE,
  });
}

/** Reload everything eBay shows after a change. */
export function useEbayRefresh() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: EBAY_KEY });
}

/** Only the owner connects and configures eBay; staff may offer products and fetch orders. */
export function useIsOwner(): boolean {
  const session = useStaffSession();
  return session.status === "authenticated" && session.account.role === "owner";
}
