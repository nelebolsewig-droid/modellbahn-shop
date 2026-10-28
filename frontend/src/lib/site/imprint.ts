import type { ImprintOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";

/** The provider details from the API (MB_IMPRINT_*); null while it is unreachable. Server only. */
export async function loadImprint(): Promise<ImprintOut | null> {
  try {
    return await fetchStore<ImprintOut>("/imprint");
  } catch {
    return null;
  }
}

/** A tel: link; the number as written ("0160 91515272") keeps only digits and "+". */
export function phoneHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, "")}`;
}

/** "adp-Modelle, Inhaber Johann-Leon Diesterhaupt", or just the owner's name. */
export function providerName(imprint: Pick<ImprintOut, "company" | "owner">): string {
  if (!imprint.company || imprint.company === imprint.owner) {
    return imprint.owner;
  }
  return imprint.owner ? `${imprint.company}, Inhaber ${imprint.owner}` : imprint.company;
}
