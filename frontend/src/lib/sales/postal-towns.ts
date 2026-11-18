"use client";

import { useEffect, useState } from "react";

/*
 * Postal code → town for German addresses, from the GeoNames data in public/plz
 * (scripts/plz_orte.py). One small file per first two digits, loaded when a full code
 * is typed; a code the data doesn't know just suggests nothing.
 */

type Chunk = Readonly<Record<string, readonly string[]>>;

const chunks = new Map<string, Promise<Chunk>>();

function loadChunk(prefix: string, load: typeof fetch): Promise<Chunk> {
  let chunk = chunks.get(prefix);
  if (!chunk) {
    chunk = load(`/plz/${prefix}.json`)
      .then((response) => (response.ok ? (response.json() as Promise<Chunk>) : {}))
      .catch(() => {
        // Offline for a moment: try again with the next code typed.
        chunks.delete(prefix);
        return {};
      });
    chunks.set(prefix, chunk);
  }
  return chunk;
}

/** The towns of a German postal code; empty for anything that isn't five digits. */
export async function townsFor(postalCode: string, load: typeof fetch = fetch): Promise<readonly string[]> {
  const code = postalCode.trim();
  if (!/^\d{5}$/.test(code)) return [];
  return (await loadChunk(code.slice(0, 2), load))[code] ?? [];
}

/** Forget what was loaded (for tests). */
export function clearPostalTowns(): void {
  chunks.clear();
}

/** The towns of the code as it is typed, for Germany only. */
export function usePostalTowns(postalCode: string, countryCode: string): readonly string[] {
  const [found, setFound] = useState<{
    code: string;
    towns: readonly string[];
  }>({ code: "", towns: [] });
  const code = countryCode === "DE" ? postalCode.trim() : "";

  useEffect(() => {
    if (!/^\d{5}$/.test(code)) return;
    let current = true;
    void townsFor(code).then((towns) => {
      if (current) setFound({ code, towns });
    });
    return () => {
      current = false;
    };
  }, [code]);

  return found.code === code ? found.towns : [];
}
