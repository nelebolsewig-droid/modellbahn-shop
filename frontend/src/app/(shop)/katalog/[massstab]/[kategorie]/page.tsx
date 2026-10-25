import type { Metadata } from "next";

import { resolveLocation, ScaleCatalog } from "@/components/shop/scale-catalog";
import { loadNavigation } from "@/lib/catalog/store-data";

export async function generateMetadata({
  params,
}: PageProps<"/katalog/[massstab]/[kategorie]">): Promise<Metadata> {
  const { massstab, kategorie } = await params;
  const navigation = await loadNavigation();
  const resolved = navigation && resolveLocation(navigation, massstab, kategorie);
  if (!resolved?.category) {
    return { title: "Kategorie nicht gefunden" };
  }
  return { title: `${resolved.category.name} in ${resolved.scale.name}` };
}

export default async function ScaleCategoryPage({ params, searchParams }: PageProps<"/katalog/[massstab]/[kategorie]">) {
  const { massstab, kategorie } = await params;
  return <ScaleCatalog scaleSlug={massstab} categorySlug={kategorie} searchParams={await searchParams} />;
}
