"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { CartOut } from "@/lib/api/generated/model";
import {
  getCart,
  getGetCartQueryKey,
  removeCartLine,
  setCartLine,
} from "@/lib/api/generated/store-sales/store-sales";
import type { ApiProblem } from "@/lib/api/problem";

export const cartQueryKey = getGetCartQueryKey();

/** The visitor's cart at today's prices (the cookie names it; no cookie, empty cart). */
export function useCart() {
  return useQuery<CartOut, ApiProblem>({
    queryKey: cartQueryKey,
    queryFn: ({ signal }) => getCart({ signal }),
    staleTime: 30_000,
  });
}

export type CartChange = { variantId: string; quantity: number };

/** Sets a line's quantity (0 removes it); the answer replaces the cached cart. */
export function useCartChange() {
  const queryClient = useQueryClient();
  return useMutation<CartOut, ApiProblem, CartChange>({
    mutationFn: ({ variantId, quantity }) =>
      quantity === 0 ? removeCartLine(variantId) : setCartLine(variantId, { quantity }),
    onSuccess(cart) {
      queryClient.setQueryData(cartQueryKey, cart);
    },
  });
}
