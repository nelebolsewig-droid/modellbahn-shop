import type { StatusTone } from "@/components/ui/status-badge";
import type {
  CancelReason,
  OrderStatus,
  PaymentInMethod,
  PaymentStatus,
} from "@/lib/api/generated/model";

export const ORDER_STATUS_LABELS = {
  pending_payment: "Zahlung offen",
  paid: "Bezahlt",
  shipped: "Versendet",
  cancelled: "Storniert",
} as const satisfies Record<OrderStatus, string>;

export const ORDER_STATUS_TONES = {
  pending_payment: "warning",
  paid: "accent",
  shipped: "success",
  cancelled: "neutral",
} as const satisfies Record<OrderStatus, StatusTone>;

export const CANCEL_REASON_LABELS = {
  payment_timeout: "Die Zahlung ist nicht innerhalb von 24 Stunden eingegangen.",
  by_shop: "Wir haben die Bestellung storniert.",
  by_marketplace: "Die Bestellung wurde auf eBay storniert; eBay erstattet den Betrag.",
} as const satisfies Record<CancelReason, string>;

export const PAYMENT_STATUS_LABELS = {
  captured: "Bezahlt",
  failed: "Abgelehnt",
  refunded: "Erstattet",
} as const satisfies Record<PaymentStatus, string>;

/** The outcomes of the test payment, as the payment page offers them. */
export const TEST_PAYMENT_METHODS: readonly {
  value: PaymentInMethod;
  label: string;
  description: string;
}[] = [
  {
    value: "succeeds",
    label: "Zahlung gelingt",
    description: "Die Testkarte wird belastet, die Bestellung ist bezahlt.",
  },
  {
    value: "declined",
    label: "Zahlung wird abgelehnt",
    description: "Die Bank lehnt ab. Die Bestellung bleibt offen, du kannst es erneut versuchen.",
  },
  {
    value: "fails",
    label: "Zahlungsdienst gestört",
    description: "Der Dienst antwortet nicht. Es wird nichts abgebucht.",
  },
];

/** Carriers the admin area offers when shipping (free text is allowed too). */
export const CARRIERS = ["DHL", "Deutsche Post", "DPD", "GLS", "Hermes", "Österreichische Post"];
