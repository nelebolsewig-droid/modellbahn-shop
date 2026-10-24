import type {
  AssetStatus,
  FailureCode,
  MediaRole,
  ProductStatus,
  PublishBlocker,
} from "@/lib/api/generated/model";

/** German names of the states and codes the catalogue and media APIs use. */

export const PRODUCT_STATUS_LABELS = {
  draft: "Entwurf",
  active: "Im Shop",
  archived: "Archiviert",
} as const satisfies Record<ProductStatus, string>;

export const ASSET_STATUS_LABELS = {
  pending_upload: "Wird hochgeladen",
  uploaded: "Wird verarbeitet",
  ready: "Bereit",
  failed: "Fehlgeschlagen",
} as const satisfies Record<AssetStatus, string>;

export const FAILURE_LABELS = {
  unsupported_format: "Kein Bildformat, das wir lesen können (JPEG, PNG, WebP, AVIF, HEIC).",
  too_many_pixels: "Das Bild hat zu viele Pixel (höchstens 100 Megapixel).",
  too_small: "Das Bild ist zu klein (mindestens 256 Pixel an der kürzeren Seite).",
  unreadable: "Die Datei ist beschädigt oder unvollständig.",
  processing_error: "Die Verarbeitung ist mehrmals fehlgeschlagen.",
} as const satisfies Record<FailureCode, string>;

export const PUBLISH_BLOCKER_LABELS = {
  no_category: "Eine Kategorie ist gewählt",
  no_active_variant: "Mindestens eine Variante ist aktiv",
  no_main_image: "Ein Hauptbild ist in der Galerie",
  main_image_not_ready: "Das Hauptbild ist fertig verarbeitet",
} as const satisfies Record<PublishBlocker, string>;

/** Every rule a product in the shop satisfies, in the order of the checklist. */
export const PUBLISH_RULES = Object.keys(PUBLISH_BLOCKER_LABELS) as PublishBlocker[];

export const MEDIA_ROLE_LABELS = {
  gallery: "Ansicht",
  detail: "Detail",
  scale_comparison: "Größenvergleich",
} as const satisfies Record<MediaRole, string>;

/** The text of a failure code, which the API sends as a plain string. */
export function failureLabel(code: string | null): string {
  return code !== null && Object.hasOwn(FAILURE_LABELS, code)
    ? FAILURE_LABELS[code as FailureCode]
    : "Die Verarbeitung ist fehlgeschlagen.";
}
