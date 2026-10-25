"use client";

import type { Route } from "next";
import Link from "next/link";

import { OrderLines, OrderTimeline, PostalAddress } from "@/components/shop/order-parts";
import { OrderTotals } from "@/components/shop/order-totals";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { StatusBadge } from "@/components/ui/status-badge";
import type { OrderOut } from "@/lib/api/generated/model";
import { useGetOrderByToken } from "@/lib/api/generated/store-sales/store-sales";
import { isApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { formatLongDate, formatTime } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import {
  CANCEL_REASON_LABELS,
  ORDER_STATUS_LABELS,
  ORDER_STATUS_TONES,
  PAYMENT_STATUS_LABELS,
} from "@/lib/sales/labels";

/** The status page behind the link in the order e-mails: works without an account. */
export function OrderStatusView({ token }: { token: string }) {
  const order = useGetOrderByToken(token);

  if (order.isPending) {
    return <PendingNotice>Deine Bestellung wird geladen …</PendingNotice>;
  }
  if (order.isError) {
    const missing = isApiProblem(order.error) && order.error.status === 404;
    return (
      <div className="max-w-xl space-y-6">
        <Alert tone="danger" title={missing ? "Diese Bestellung gibt es nicht" : "Die Bestellung konnte nicht geladen werden"}>
          <p>
            {missing
              ? "Prüfe bitte den Link aus deiner E-Mail; er muss vollständig sein."
              : errorMessage(order.error)}
          </p>
        </Alert>
        <Button asChild variant="secondary">
          <Link href="/">Zur Startseite</Link>
        </Button>
      </div>
    );
  }
  return <OrderDetails order={order.data} payHref={`/bestellung/${token}/bezahlen` as Route} />;
}

type OrderDetailsProps = {
  order: OrderOut;
  /** Where to pay an open order; absent where paying is not offered. */
  payHref?: Route;
};

/** Headline, timeline, lines, totals and address of an order, for the customer. */
export function OrderDetails({ order, payHref }: OrderDetailsProps) {
  const headline = HEADLINES[order.status];
  return (
    <div>
      <p className="flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-hint text-ink-tertiary">
        <span>Bestellung {order.number}</span>
        <StatusBadge tone={ORDER_STATUS_TONES[order.status]}>{ORDER_STATUS_LABELS[order.status]}</StatusBadge>
      </p>
      <h1 className="mt-4 text-title sm:text-display">{headline}</h1>
      <div className="mt-5 max-w-2xl space-y-3 text-body-lg text-ink-secondary">
        <StatusText order={order} />
      </div>
      {order.status === "pending_payment" && payHref ? (
        <Button asChild className="mt-8">
          <Link href={payHref}>Jetzt {formatPrice(order.totals.total_cents)} bezahlen</Link>
        </Button>
      ) : null}

      <OrderTimeline order={order} className="mt-12 max-w-2xl" />

      <div className="mt-14 grid items-start gap-12 lg:grid-cols-[minmax(0,1fr)_20rem] lg:gap-16">
        <section aria-labelledby="artikel">
          <h2 id="artikel" className="label-caps text-ink-tertiary">
            Artikel
          </h2>
          <div className="mt-4">
            <OrderLines lines={order.lines} />
          </div>
          <OrderTotals totals={order.totals} countryName={order.shipping_address.country_name} className="mt-6 sm:ml-auto sm:max-w-sm" />
        </section>
        <aside className="space-y-8">
          <section aria-labelledby="lieferadresse">
            <h2 id="lieferadresse" className="label-caps text-ink-tertiary">
              Lieferadresse
            </h2>
            <PostalAddress address={order.shipping_address} className="mt-3" />
          </section>
          <section aria-labelledby="kontakt">
            <h2 id="kontakt" className="label-caps text-ink-tertiary">
              E-Mail-Adresse
            </h2>
            <p className="mt-3 text-small break-all">{order.email}</p>
          </section>
          {order.payments.length > 0 ? (
            <section aria-labelledby="zahlungen">
              <h2 id="zahlungen" className="label-caps text-ink-tertiary">
                Zahlungen
              </h2>
              <ul className="mt-3 space-y-1 text-small">
                {order.payments.map((payment) => (
                  <li key={payment.created_at} className="flex justify-between gap-4">
                    <span>
                      {PAYMENT_STATUS_LABELS[payment.status]}
                      <span className="text-ink-tertiary"> · {formatTime(new Date(payment.created_at))}</span>
                    </span>
                    <span className="tabular-nums">{formatPrice(payment.amount_cents)}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

const HEADLINES = {
  pending_payment: "Fast geschafft",
  paid: "Danke für deine Bestellung!",
  shipped: "Dein Paket ist unterwegs",
  cancelled: "Bestellung storniert",
} as const satisfies Record<OrderOut["status"], string>;

function StatusText({ order }: { order: OrderOut }) {
  switch (order.status) {
    case "pending_payment":
      return (
        <p>
          Deine Bestellung ist angelegt und wartet auf die Zahlung.
          {order.payment_due_at ? (
            <>
              {" "}
              Bitte bezahle bis {formatLongDate(new Date(order.payment_due_at))},{" "}
              {formatTime(new Date(order.payment_due_at))} Uhr; danach stornieren wir sie automatisch.
            </>
          ) : null}
        </p>
      );
    case "paid":
      return (
        <p>
          Die Zahlung ist eingegangen, die Bestellung ist verbindlich. Wir bereiten alles vor und schreiben
          dir an <span className="text-ink">{order.email}</span>, sobald das Paket unterwegs ist.
        </p>
      );
    case "shipped":
      return (
        <p>
          Wir haben deine Bestellung verschickt.
          {order.tracking_number ? (
            <>
              {" "}
              Die Sendungsnummer{order.carrier ? ` bei ${order.carrier}` : ""} ist{" "}
              <span className="font-mono text-ink">{order.tracking_number}</span>.
            </>
          ) : null}{" "}
          Viel Freude beim Bauen!
        </p>
      );
    case "cancelled":
      return (
        <>
          <p>{order.cancel_reason ? CANCEL_REASON_LABELS[order.cancel_reason] : "Die Bestellung ist storniert."}</p>
          {order.payments.some((payment) => payment.status === "refunded") ? (
            <p>Den bezahlten Betrag erstatten wir auf dem Weg, auf dem du bezahlt hast.</p>
          ) : null}
        </>
      );
  }
}
