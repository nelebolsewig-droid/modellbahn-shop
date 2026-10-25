import type { Metadata } from "next";

import { resolveLocation, ScaleCatalog } from "@/components/shop/scale-catalog";
import { scaleLabel } from "@/lib/catalog/scales";
import { loadNavigation } from "@/lib/catalog/store-data";

export async function generateMetadata({ params }: PageProps<"/katalog/[massstab]">): Promise<Metadata> {
  const navigation = await loadNavigation();
  const resolved = navigation && resolveLocation(navigation, (await params).massstab, undefined);
  if (!resolved) {
    return { title: "Maßstab nicht gefunden" };
  }
  return {
    title: `Modelle in ${scaleLabel(resolved.scale)}`,
    description: `3D-gedruckte Modelle im Maßstab ${resolved.scale.ratio}: Gebäude, Fahrzeuge und Zubehör.`,
  };
}

export default async function ScalePage({ params, searchParams }: PageProps<"/katalog/[massstab]">) {
  return <ScaleCatalog scaleSlug={(await params).massstab} searchParams={await searchParams} />;
}
