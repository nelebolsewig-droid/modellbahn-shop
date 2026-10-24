"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getCatalogReferences, getProduct, listCategories } from "@/lib/api/generated/admin-catalog/admin-catalog";
import type { CategoryOut, ProductOut, ReferencesOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";

/** Root of the admin catalogue queries; invalidating it refreshes every list. */
export const ADMIN_PRODUCTS_KEY = ["admin", "products"] as const;

export function productQueryKey(productId: string) {
  return ["admin", "product", productId] as const;
}

export function useProduct(productId: string) {
  return useQuery<ProductOut, ApiProblem>({
    queryKey: productQueryKey(productId),
    queryFn: ({ signal }) => getProduct(productId, { signal }),
  });
}

/** Gauges, finishes and epochs: rows of a migration, they do not change while a page is open. */
export function useReferences() {
  return useQuery<ReferencesOut, ApiProblem>({
    queryKey: ["admin", "catalog-references"],
    queryFn: ({ signal }) => getCatalogReferences({ signal }),
    staleTime: Number.POSITIVE_INFINITY,
  });
}

export const CATEGORIES_KEY = ["admin", "categories"] as const;

export function useCategories() {
  return useQuery<CategoryOut[], ApiProblem>({
    queryKey: CATEGORIES_KEY,
    queryFn: ({ signal }) => listCategories({ signal }),
  });
}

/**
 * Runs a command on a product (every catalogue command answers with the whole
 * product) and makes its answer the cached state. Each part of the editor uses its
 * own instance, so it shows its own progress and error.
 */
export function useProductCommand(productId: string) {
  const queryClient = useQueryClient();
  return useMutation<ProductOut, ApiProblem, () => Promise<ProductOut>>({
    mutationFn: (command) => command(),
    onSuccess(product) {
      queryClient.setQueryData(productQueryKey(productId), product);
      void queryClient.invalidateQueries({ queryKey: ADMIN_PRODUCTS_KEY });
    },
  });
}

/** True when a command failed because someone else changed the product first. */
export function isVersionConflict(error: ApiProblem | null): boolean {
  return error?.code === "precondition_failed";
}
