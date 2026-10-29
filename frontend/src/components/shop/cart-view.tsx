"use client";

import type { Route } from "next";
import Link from "next/link";

import { FreeShippingMeter, OrderTotals } from "@/components/shop/order-totals";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ColorDot } from "@/components/ui/color-dot";
import { PendingNotice } from "@/components/ui/pending-notice";
import { QuantityStepper } from "@/components/ui/quantity-stepper";
import { ResponsivePicture } from "@/components/ui/responsive-picture";
import { StatusBadge } from "@/components/ui/status-badge";
import type { CartLineOut, CartOut } from "@/lib/api/generated/model";
import { finishLabel, formatPrice } from "@/lib/catalog/format";
import { errorMessage } from "@/lib/i18n/problems";
import { availabilityNote, cartLeadTime, leadTimeText } from "@/lib/sales/availability";
import { shippingGroups } from "@/lib/sales/countries";
import { useCart, useCartChange } from "@/lib/sales/cart";
import { cn } from "@/lib/utils";

/** The cart page: lines with quantities, the totals and the way to the checkout. */
export function CartView() {
  const cart = useCart();
  const change = useCartChange();

  if (cart.isPending) {
    return <PendingNotice className="mt-10">Der Warenkorb wird geladen …</PendingNotice>;
  }
  if (cart.isError) {
    return (
      <Alert tone="danger" title="Der Warenkorb konnte nicht geladen werden" className="mt-10 max-w-xl">
        <p>{errorMessage(cart.error)}</p>
      </Alert>
    );
  }
  const data = cart.data;
  if (data.lines.length === 0) {
    return <EmptyCart />;
  }
  const unavailable = data.lines.filter((line) => !line.available);

  return (
    <div className="mt-10 grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-14">
      <section aria-label="Artikel">
        {unavailable.length > 0 ? (
          <Alert tone="danger" title="Nicht alles ist so lieferbar" className="mb-6">
            <p>
              {unavailable.length === 1 ? "Ein Artikel ist" : `${unavailable.length} Artikel sind`} nicht mehr
              erhältlich oder nicht in dieser Menge vorrätig. Passe die Menge an oder entferne{" "}
              {unavailable.length === 1 ? "ihn" : "sie"}, dann geht es weiter zur Kasse.
            </p>
          </Alert>
        ) : null}
        <ul className="divide-y divide-line border-y border-line">
          {data.lines.map((line) => (
            <CartLine
              key={line.variant_id}
              line={line}
              busy={change.isPending && change.variables.variantId === line.variant_id}
              onQuantity={(quantity) => change.mutate({ variantId: line.variant_id, quantity })}
            />
          ))}
        </ul>
        <div role="alert" className="not-empty:mt-4">
          {change.isError ? <p className="text-small text-danger">{errorMessage(change.error)}</p> : null}
        </div>
        <p className="mt-6">
          <Link href="/katalog" className="text-small font-medium text-accent underline-offset-4 hover:underline">
            ← Weiter einkaufen
          </Link>
        </p>
      </section>
      <CartSummary cart={data} />
    </div>
  );
}

function CartLine({
  line,
  busy,
  onQuantity,
}: {
  line: CartLineOut;
  busy: boolean;
  onQuantity: (quantity: number) => void;
}) {
  const productHref = `/produkte/${line.product_slug}` as Route;
  const variantLabel = finishLabel(line.finish_name, line.color);
  // Still for sale, just not that many: the customer can bring the quantity down.
  const short = !line.available && line.free_units > 0;
  return (
    <li className={cn("grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-5 gap-y-4 py-6 sm:grid-cols-[7rem_minmax(0,1fr)_auto]", busy && "opacity-70")}>
      <Link
        href={productHref}
        tabIndex={-1}
        aria-hidden="true"
        className={cn("relative aspect-square rounded-md bg-stage p-2", !line.available && "opacity-50 grayscale")}
      >
        {line.image ? <ResponsivePicture image={line.image} alt="" sizes="112px" variant="thumb" /> : null}
      </Link>
      <div className="min-w-0">
        <h3 className="text-body font-medium">
          <Link href={productHref} className="hover:underline hover:underline-offset-4">
            {line.product_name}
          </Link>
        </h3>
        <p className="mt-1 flex items-center gap-2 text-small text-ink-secondary">
          {line.color !== "" ? <ColorDot color={line.color} size="sm" /> : null}
          <span>
            {line.scale_name} · {variantLabel}
          </span>
        </p>
        <p className="mt-1 font-mono text-hint text-ink-tertiary">{line.sku}</p>
        {line.available ? (
          <p className="mt-2 text-hint text-ink-tertiary tabular-nums">je {formatPrice(line.unit_price_cents)}</p>
        ) : null}
        <LineAvailability line={line} />
      </div>
      <div className="col-span-2 flex items-center justify-between gap-4 sm:col-span-1 sm:flex-col sm:items-end sm:justify-start">
        <p className={cn("text-body font-medium tabular-nums sm:order-last sm:mt-auto", !line.available && "text-ink-tertiary line-through")}>
          {formatPrice(line.line_total_cents)}
        </p>
        <div className="flex items-center gap-2">
          {line.available || short ? (
            <QuantityStepper
              value={line.quantity}
              onChange={onQuantity}
              label={`Menge ${line.product_name}, ${line.scale_name}, ${variantLabel}`}
              disabled={busy}
            />
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => onQuantity(0)}
            aria-label={`${line.product_name}, ${line.scale_name}, ${variantLabel} entfernen`}
          >
            Entfernen
          </Button>
        </div>
      </div>
    </li>
  );
}

/** "Sofort lieferbar", "Wird für dich gefertigt · 4–6 Wochen", or what keeps it from the checkout. */
function LineAvailability({ line }: { line: CartLineOut }) {
  if (!line.available) {
    return (
      <p className="mt-2 text-hint font-medium text-danger">
        {line.free_units > 0
          ? `Nur noch ${line.free_units} Stück vorrätig`
          : "Derzeit nicht lieferbar"}
      </p>
    );
  }
  const note = availabilityNote(line.availability, line.free_units, line);
  return (
    <p className="mt-2 flex flex-wrap items-baseline gap-x-2">
      <StatusBadge tone={note.tone}>{note.label}</StatusBadge>
      {line.availability === "made_to_order" && note.detail ? <span className="text-hint text-ink-tertiary">{note.detail}</span> : null}
    </p>
  );
}

/** When the parcel can leave: at once, or once the last piece built to order is done. */
export function DeliveryNote({ cart, className }: { cart: CartOut; className?: string }) {
  const weeks = cartLeadTime(cart.lines);
  if (weeks === null) {
    return null;
  }
  return (
    <p className={cn("rounded-sm bg-accent-subtle px-4 py-3 text-small text-accent", className)}>
      Mindestens ein Modell wird für dich gefertigt. Wir schicken alles zusammen in voraussichtlich {leadTimeText(weeks)}.
    </p>
  );
}

/** "In die übrigen EU-Länder: 16,90 €." – the terms of the countries not chosen, grouped. */
function otherTerms(cart: CartOut): string {
  const other = cart.countries.filter((country) => country.code !== cart.shipping_country.code);
  return shippingGroups(other)
    .map((group) => {
      const first = group[0];
      if (first === undefined) {
        return "";
      }
      const where = group.length === 1 ? `Nach ${first.name}` : "In die übrigen EU-Länder";
      const free = first.free_from_cents === null ? "" : `, ab ${formatPrice(first.free_from_cents)} kostenlos`;
      return `${where}: ${formatPrice(first.rate_cents)}${free}.`;
    })
    .join(" ");
}

function CartSummary({ cart }: { cart: CartOut }) {
  return (
    <aside aria-label="Summe" className="rounded-lg bg-surface p-6 sm:p-8 lg:sticky lg:top-8">
      <h2 className="text-heading">Übersicht</h2>
      <OrderTotals totals={cart.totals} countryName={cart.shipping_country.name} className="mt-6" />
      <FreeShippingMeter
        country={cart.shipping_country}
        subtotalCents={cart.totals.subtotal_cents}
        className="mt-6"
      />
      <DeliveryNote cart={cart} className="mt-6" />
      {cart.ready_for_checkout ? (
        <Button asChild className="mt-8 w-full">
          <Link href="/kasse">Zur Kasse</Link>
        </Button>
      ) : (
        <Button type="button" className="mt-8 w-full" disabled>
          Zur Kasse
        </Button>
      )}
      <p className="mt-4 text-hint text-ink-tertiary">
        {otherTerms(cart)}{" "}
        <Link href="/versand" className="underline underline-offset-4 hover:text-ink">
          Versand und Lieferung
        </Link>
      </p>
    </aside>
  );
}

function EmptyCart() {
  return (
    <div className="mt-12 flex flex-col items-start gap-6 rounded-lg bg-surface p-8 sm:flex-row sm:items-center sm:p-10">
      {/* An empty goods wagon on a short track. */}
      <svg viewBox="0 0 120 64" className="h-16 w-30 shrink-0 text-drawing-line" fill="none" stroke="currentColor" strokeWidth="1.2" aria-hidden="true">
        <path d="M14 18h92v28H14z" />
        <path d="M14 18l8-8h76l8 8" strokeDasharray="3 3" />
        <circle cx="34" cy="52" r="6" />
        <circle cx="86" cy="52" r="6" />
        <path d="M2 58h116" />
        <path d="M8 58v4M24 58v4M40 58v4M56 58v4M72 58v4M88 58v4M104 58v4" />
      </svg>
      <div>
        <h2 className="text-heading">Dein Warenkorb ist noch leer</h2>
        <p className="mt-2 text-ink-secondary">Im Katalog findest du alle Modelle, in jedem Maßstab und jeder Ausführung.</p>
        <Button asChild className="mt-6">
          <Link href="/katalog">Zum Katalog</Link>
        </Button>
      </div>
    </div>
  );
}
