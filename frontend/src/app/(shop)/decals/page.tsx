import { redirect } from "next/navigation";

import { DECALS_SLUG, decalsPath } from "@/lib/catalog/decals";
import { busiestScale } from "@/lib/catalog/scales";
import { loadNavigation } from "@/lib/catalog/store-data";

/** /decals opens the decals in the scale that has the most of them. */
export default async function DecalsPage() {
  const navigation = await loadNavigation();
  const root = navigation?.categories.find((category) => category.slug === DECALS_SLUG);
  const scale =
    navigation && root
      ? (busiestScale(navigation.scales, navigation.categories, root.id) ?? navigation.scales[0])
      : navigation?.scales[0];
  redirect(scale ? decalsPath(scale.code) : "/katalog");
}
