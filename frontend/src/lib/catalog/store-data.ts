import { connection } from "next/server";
import { cache } from "react";

import type { NavigationOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";

/**
 * The shop's navigation (scales, categories, counts) for Server Components. Metadata
 * and page of one request ask for it once; every request reads it fresh, because a
 * product published a minute ago must show up in the counts.
 */
export const loadNavigation = cache(async (): Promise<NavigationOut | null> => {
  await connection();
  return fetchStore<NavigationOut>("/navigation");
});
