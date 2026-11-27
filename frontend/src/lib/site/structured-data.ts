import type { ImageOut, ImprintOut, StoreProductOut, VariantAvailabilityOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { catalogPath, scaleLabel } from "@/lib/catalog/scales";

/*
 * Search engine data (ADR 0051): schema.org JSON-LD for product pages and the shop,
 * and the rows of the Google Merchant Center feed. Pure functions; the pages fetch.
 */

type Json = Record<string, unknown>;

/** An absolute URL for a path of this site ("/medien/…" → "https://www…/medien/…"). */
export function absoluteUrl(base: string, path: string): string {
  return /^https?:\/\//.test(path) ? path : `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}

/** The best large picture of an image for search engines: lg, else og, else md (webp). */
export function largeImageUrl(image: ImageOut): string | null {
  for (const name of ["lg", "og", "md"]) {
    const rendition = image.renditions.find((r) => r.name === name && r.format === "webp");
    if (rendition) {
      return rendition.url;
    }
  }
  return null;
}

export function productImages(product: StoreProductOut, base: string): string[] {
  return product.gallery
    .map((item) => largeImageUrl(item.image))
    .filter((url): url is string => url !== null)
    .map((url) => absoluteUrl(base, url));
}

/** schema.org availability for one variant; made to order still sells (with handling time). */
export function schemaAvailability(info: VariantAvailabilityOut | undefined): string {
  if (!info) {
    return "https://schema.org/InStock";
  }
  if (info.free_units > 0) {
    return "https://schema.org/InStock";
  }
  return info.lead_time_min_weeks !== null ? "https://schema.org/MadeToOrder" : "https://schema.org/OutOfStock";
}

const euro = (cents: number) => (cents / 100).toFixed(2);

/** Product + offers, one offer per variant (scale × finish × colour). */
export function productJsonLd(
  product: StoreProductOut,
  availability: readonly VariantAvailabilityOut[],
  base: string,
  brand: string,
): Json {
  const url = absoluteUrl(base, `/produkte/${encodeURIComponent(product.slug)}`);
  const offers = product.scales.flatMap((scale) =>
    scale.variants.map((variant) => ({
      "@type": "Offer",
      sku: variant.sku,
      url,
      price: euro(variant.price_cents),
      priceCurrency: "EUR",
      availability: schemaAvailability(availability.find((a) => a.variant_id === variant.id)),
      itemCondition: "https://schema.org/NewCondition",
    })),
  );
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    description: product.summary || product.description.slice(0, 500) || undefined,
    image: productImages(product, base),
    sku: String(product.number),
    brand: { "@type": "Brand", name: brand },
    category: product.category_path.map((c) => c.name).join(" > ") || undefined,
    url,
    offers,
  };
}

/** Breadcrumbs as on the page: Modelle / scale / categories / product. */
export function breadcrumbJsonLd(product: StoreProductOut, base: string): Json {
  const scale = product.scales[0];
  const crumbs: { name: string; path: string }[] = [{ name: "Modelle", path: "/katalog" }];
  if (scale) {
    crumbs.push({ name: scaleLabel(scale), path: catalogPath({ scale: scale.code }) });
    for (const category of product.category_path) {
      crumbs.push({ name: category.name, path: catalogPath({ scale: scale.code, category: category.slug }) });
    }
  }
  crumbs.push({ name: product.name, path: `/produkte/${encodeURIComponent(product.slug)}` });
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: crumbs.map((crumb, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: crumb.name,
      item: absoluteUrl(base, crumb.path),
    })),
  };
}

/** The shop as an online store with its postal address (from the imprint). */
export function storeJsonLd(imprint: ImprintOut | null, base: string, name: string): Json {
  const data: Json = {
    "@context": "https://schema.org",
    "@type": "OnlineStore",
    name,
    url: `${base}/`,
    logo: `${base}/icon.svg`,
  };
  if (imprint) {
    if (imprint.email) data.email = imprint.email;
    if (imprint.phone) data.telephone = imprint.phone;
    if (imprint.vat_id) data.vatID = imprint.vat_id;
    if (imprint.street || imprint.city) {
      data.address = {
        "@type": "PostalAddress",
        streetAddress: imprint.street || undefined,
        postalCode: imprint.postal_code || undefined,
        addressLocality: imprint.city || undefined,
        addressCountry: "DE",
      };
    }
  }
  return data;
}

/** JSON for a <script type="application/ld+json">, safe against "</script>" in texts. */
export function serializeJsonLd(data: Json): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

/* ---------- Google Merchant Center feed ---------- */

export type FeedItem = {
  id: string;
  groupId: string;
  title: string;
  description: string;
  link: string;
  imageLink: string;
  additionalImages: string[];
  price: string;
  salePrice: string | null;
  availability: "in_stock" | "out_of_stock";
  minHandlingDays: number | null;
  maxHandlingDays: number | null;
  productType: string;
};

/** One feed row per variant; without a picture Google refuses the item, so it is left out. */
export function feedItems(
  product: StoreProductOut,
  availability: readonly VariantAvailabilityOut[],
  base: string,
): FeedItem[] {
  const [imageLink, ...moreImages] = productImages(product, base);
  if (imageLink === undefined) {
    return [];
  }
  const finishName = (code: string) => product.finishes.find((f) => f.code === code)?.name ?? code;
  const description = (product.summary || product.description || product.name).slice(0, 5000);
  return product.scales.flatMap((scale) =>
    scale.variants.map((variant) => {
      const info = availability.find((a) => a.variant_id === variant.id);
      const madeToOrder = !!info && info.free_units === 0 && info.lead_time_min_weeks !== null;
      const soldOut = !!info && info.free_units === 0 && info.lead_time_min_weeks === null;
      const label = [scaleLabel(scale), finishName(variant.finish_code), variant.color].filter(Boolean).join(", ");
      const onSale = variant.compare_at_price_cents !== null && variant.compare_at_price_cents > variant.price_cents;
      return {
        id: variant.sku,
        groupId: String(product.number),
        title: `${product.name} (${label})`.slice(0, 150),
        description,
        link: absoluteUrl(base, `/produkte/${encodeURIComponent(product.slug)}?massstab=${encodeURIComponent(scale.code)}`),
        imageLink,
        additionalImages: moreImages.slice(0, 9),
        price: `${euro(onSale ? variant.compare_at_price_cents! : variant.price_cents)} EUR`,
        salePrice: onSale ? `${euro(variant.price_cents)} EUR` : null,
        availability: soldOut ? "out_of_stock" : "in_stock",
        // Made to order: in stock with Google's handling time, in working days.
        minHandlingDays: madeToOrder ? info.lead_time_min_weeks! * 5 : null,
        maxHandlingDays: madeToOrder && info.lead_time_max_weeks !== null ? info.lead_time_max_weeks * 5 : null,
        productType: ["Modelle", scaleLabel(scale), ...product.category_path.map((c) => c.name)].join(" > "),
      };
    }),
  );
}

const escapeXml = (text: string) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** The feed as RSS 2.0 with the g: namespace, as Merchant Center reads it. */
export function feedXml(items: readonly FeedItem[], base: string, shopName: string, brand: string): string {
  const tag = (name: string, value: string | number | null) =>
    value === null || value === "" ? "" : `<g:${name}>${escapeXml(String(value))}</g:${name}>`;
  const rows = items.map((item) =>
    [
      "<item>",
      tag("id", item.id),
      tag("item_group_id", item.groupId),
      tag("title", item.title),
      tag("description", item.description),
      tag("link", item.link),
      tag("image_link", item.imageLink),
      ...item.additionalImages.map((url) => tag("additional_image_link", url)),
      tag("availability", item.availability),
      tag("price", item.price),
      tag("sale_price", item.salePrice),
      tag("brand", brand),
      tag("condition", "new"),
      tag("identifier_exists", "no"),
      tag("product_type", item.productType),
      tag("min_handling_time", item.minHandlingDays),
      tag("max_handling_time", item.maxHandlingDays),
      "</item>",
    ].join(""),
  );
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0"><channel>',
    `<title>${escapeXml(shopName)}</title><link>${escapeXml(base)}/</link>`,
    `<description>${escapeXml(`Modelle von ${shopName}`)}</description>`,
    ...rows,
    "</channel></rss>",
  ].join("\n");
}

/** Live availability of a product's variants; empty while the API cannot say. Server only. */
export async function loadAvailability(slug: string): Promise<VariantAvailabilityOut[]> {
  try {
    const result = await fetchStore<{ items: VariantAvailabilityOut[] }>(`/products/${encodeURIComponent(slug)}/availability`);
    return result?.items ?? [];
  } catch {
    return [];
  }
}
