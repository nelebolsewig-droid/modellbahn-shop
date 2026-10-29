import type { StatusTone } from "@/components/ui/status-badge";
import type { Blocker, EbayMode, EbayStatusOut, ListingOut, MarketplaceOrderStatus } from "@/lib/api/generated/model";

/** German names of the states the marketplace API reports. */

export const MODE_LABELS = {
  off: "Ausgeschaltet",
  test: "Testmarktplatz",
  sandbox: "eBay-Sandbox",
  production: "eBay.de",
} as const satisfies Record<EbayMode, string>;

/** What has to be in place before offers go up, in the order the owner sets it up. */
export const READINESS_STEPS = [
  { blocker: "not_connected", label: "Mit eBay verbunden" },
  { blocker: "no_fulfillment_policy", label: "Versandoption gewählt" },
  { blocker: "no_payment_policy", label: "Zahlungsoption gewählt" },
  { blocker: "no_return_policy", label: "Rücknahmeoption gewählt" },
  { blocker: "no_location", label: "Versandort angelegt" },
] as const satisfies readonly { blocker: Blocker; label: string }[];

export const ORDER_STATUS_LABELS = {
  received: "Übernommen",
  rejected: "Nicht übernommen",
  shipped: "Versand gemeldet",
  cancelled: "Storniert",
} as const satisfies Record<MarketplaceOrderStatus, string>;

export const ORDER_STATUS_TONES = {
  received: "accent",
  rejected: "danger",
  shipped: "success",
  cancelled: "neutral",
} as const satisfies Record<MarketplaceOrderStatus, StatusTone>;

/** Why the shop keeps a listing off eBay; eBay's own refusals come with eBay's words. */
const HELD_BACK_LABELS: Readonly<Record<string, string>> = {
  not_in_shop: "Das Produkt ist nicht im Shop veröffentlicht.",
  no_variant: "In diesem Maßstab ist keine Variante im Shop.",
  no_category: "Der Kategorie ist noch keine eBay-Kategorie zugeordnet.",
  no_photo: "In diesem Maßstab gibt es noch kein fertiges Foto.",
  product_missing: "Das Produkt gibt es in diesem Maßstab nicht mehr.",
};

export type ListingState = { label: string; tone: StatusTone; busy: boolean; detail: string | null };

/** A listing as the Stellwerk says it: one line of state, and the reason where one is due. */
export function listingState(listing: ListingOut): ListingState {
  if (listing.status === "failed") {
    const known = listing.error_code ? HELD_BACK_LABELS[listing.error_code] : undefined;
    return {
      label: known ? "Wartet" : "Von eBay abgelehnt",
      tone: known ? "warning" : "danger",
      busy: false,
      detail: known ?? (listing.error_message || `eBay-Fehler ${listing.error_code ?? ""}`.trim()),
    };
  }
  if (listing.needs_sync) {
    const label = listing.wanted
      ? listing.status === "active"
        ? "Wird aktualisiert"
        : "Wird eingestellt"
      : "Wird beendet";
    return { label, tone: "accent", busy: true, detail: null };
  }
  if (listing.status === "active") {
    return { label: "Online", tone: "success", busy: false, detail: null };
  }
  if (listing.status === "ended") {
    return listing.wanted
      ? {
          label: "Pausiert",
          tone: "warning",
          busy: false,
          detail: "Ausverkauft; geht mit neuem Bestand wieder online.",
        }
      : { label: "Beendet", tone: "neutral", busy: false, detail: null };
  }
  return { label: "Wird eingestellt", tone: "accent", busy: true, detail: null };
}

/** True when offers can go up: connected, policies chosen, location there. */
export function isReady(status: EbayStatusOut): boolean {
  return status.mode !== "off" && status.blockers.length === 0;
}

/** The shop's price with the markup, rounded half up to the cent, as the backend does. */
export function priceWithMarkup(cents: number, percent: number): number {
  return Math.floor((cents * (100 + percent) + 50) / 100);
}

/** Where the owner returns from eBay's consent page: ?ebay=verbunden and friends. */
export const CALLBACK_OUTCOMES: Readonly<Record<string, { tone: "info" | "success" | "danger"; text: string }>> = {
  verbunden: { tone: "success", text: "eBay ist verbunden." },
  abgebrochen: { tone: "info", text: "Die Verbindung mit eBay wurde nicht erteilt." },
  ungueltig: { tone: "danger", text: "Der Rücksprung von eBay war abgelaufen. Bitte verbinde dich erneut." },
  fehler: { tone: "danger", text: "eBay hat die Verbindung nicht bestätigt. Bitte versuche es noch einmal." },
};
