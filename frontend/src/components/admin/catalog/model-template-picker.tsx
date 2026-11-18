"use client";

import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";

import { Input } from "@/components/ui/input";
import { ResponsivePicture } from "@/components/ui/responsive-picture";
import { getProduct, listProducts } from "@/lib/api/generated/admin-catalog/admin-catalog";
import type { ProductListItemOut, ProductOut } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import { readyPicture } from "@/lib/catalog/images";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";

import { ADMIN_PRODUCTS_KEY } from "./use-product";

const SHOWN = 6;
/** Fetched, of which only those with Ausführungen are offered: an imported model without them has nothing to copy. */
const LOOKED_AT = 100;

type ModelTemplatePickerProps = {
  /** The model taken over, or null for an empty start. */
  chosenId: string | null;
  onChoose: (product: ProductOut | null) => void;
};

/**
 * „Wie ein vorhandenes Modell“: the newest models side by side; one tap takes over its
 * scale, finishes, colours, prices and category (ADR 0033). Name and photos stay new.
 */
export function ModelTemplatePicker({ chosenId, onChoose }: ModelTemplatePickerProps) {
  const [search, setSearch] = useState("");
  const typed = useDeferredValue(search.trim());
  const query = typed.length >= 2 ? typed : null;
  const recent = useQuery({
    queryKey: [...ADMIN_PRODUCTS_KEY, "templates", query, LOOKED_AT],
    queryFn: ({ signal }) => listProducts({ limit: LOOKED_AT, ...(query !== null && { q: query }) }, { signal }),
    placeholderData: (before) => before,
  });
  const [loading, setLoading] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const items = (recent.data?.items ?? []).filter((item) => item.variant_count > 0).slice(0, SHOWN);
  if (recent.isError) {
    return null; // nothing to copy; the wizard works without it
  }

  async function take(item: ProductListItemOut) {
    if (item.id === chosenId) {
      onChoose(null);
      return;
    }
    setLoading(item.id);
    setProblem(null);
    try {
      onChoose(await getProduct(item.id));
    } catch (error) {
      setProblem(errorMessage(error));
    } finally {
      setLoading(null);
    }
  }

  return (
    <section aria-labelledby="template-title" className="border border-line bg-surface p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="template-title" className="label-caps text-ink-tertiary">
          Wie ein vorhandenes Modell
        </h2>
        <p className="text-hint text-ink-tertiary">Übernimmt Maßstab, Ausführungen, Farben und Preise.</p>
      </div>
      <label htmlFor="template-search" className="sr-only">
        Vorlage suchen
      </label>
      <Input
        id="template-search"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Modell suchen, z. B. ADK 70"
        className="mt-3"
        autoComplete="off"
      />
      {recent.isSuccess && items.length === 0 ? (
        <p className="mt-3 text-hint text-ink-tertiary">
          {query === null ? "Unter den neuesten Modellen hat noch keines Ausführungen. Einfach suchen." : `Kein Modell mit Ausführungen passt zu „${query}“.`}
        </p>
      ) : null}
      <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {recent.isPending
          ? Array.from({ length: 3 }, (_, index) => <li key={index} className="h-16 animate-pulse bg-sunken" />)
          : items.map((item) => {
              const picture = readyPicture(item.main_image);
              const chosen = item.id === chosenId;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    aria-pressed={chosen}
                    disabled={loading !== null}
                    onClick={() => void take(item)}
                    className={cn(
                      "flex w-full cursor-pointer items-center gap-3 border p-2 text-left transition-colors disabled:cursor-wait",
                      chosen ? "border-selected bg-selected text-on-selected" : "border-line bg-canvas hover:border-ink",
                    )}
                  >
                    <span className="relative size-12 shrink-0 overflow-hidden bg-stage">
                      {picture ? <ResponsivePicture image={picture} alt="" sizes="48px" fit="cover" /> : null}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-small font-medium">{item.name}</span>
                      <span className={cn("block text-hint", chosen ? "text-on-selected/80" : "text-ink-tertiary")}>
                        {loading === item.id
                          ? "wird übernommen …"
                          : chosen
                            ? "übernommen · nochmal tippen: leer"
                            : [item.scale_codes.join(", "), item.price_from_cents !== null ? `ab ${formatPrice(item.price_from_cents)}` : null]
                                .filter(Boolean)
                                .join(" · ")}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
      </ul>
      {problem ? (
        <p role="alert" className="mt-2 text-small text-danger">
          {problem}
        </p>
      ) : null}
    </section>
  );
}
