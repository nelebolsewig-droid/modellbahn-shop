"use client";

import { useMutation } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";

import { Panel } from "@/components/admin/panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { Select } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { TextLink } from "@/components/ui/text-link";
import {
  cancelEbayTestSale,
  createEbayTestSale,
  fetchEbayOrders,
  reportEbayShipment,
  syncEbayListing,
} from "@/lib/api/generated/admin-marketplace/admin-marketplace";
import type { EbayStatusOut, FetchOut, ListingOut, MarketplaceOrderOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { formatEventTime, formatLongDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import {
  EBAY_SETUP_HREF,
  isReady,
  listingState,
  ORDER_STATUS_LABELS,
  ORDER_STATUS_TONES,
  READINESS_STEPS,
} from "@/lib/marketplace/labels";
import { cn } from "@/lib/utils";

import { useEbayListings, useEbayOrders, useEbayRefresh, useEbayStatus } from "./use-ebay";

/**
 * eBay's daily work in the Stellwerk: the offers with what eBay said about them, and
 * the orders from there. On the test marketplace the owner can also buy as an eBay
 * buyer would. Setting eBay up is under Einstellungen (see EbaySetupDesk).
 */
export function EbayDesk() {
  const status = useEbayStatus();
  if (status.isPending) {
    return <PendingNotice>eBay wird geladen …</PendingNotice>;
  }
  if (status.isError) {
    return (
      <Alert tone="danger" title="eBay konnte nicht geladen werden">
        <p>{errorMessage(status.error)}</p>
      </Alert>
    );
  }
  const account = status.data;
  if (account.mode === "off") {
    return (
      <Alert tone="info" title="eBay ist ausgeschaltet">
        <p>
          Angebote und Bestellungen von eBay stehen hier, sobald eBay eingeschaltet ist. Wie, steht unter{" "}
          <TextLink href={EBAY_SETUP_HREF}>Einrichtung</TextLink>.
        </p>
      </Alert>
    );
  }
  const open = READINESS_STEPS.filter((step) => account.blockers.includes(step.blocker)).length;
  return (
    <div className="space-y-6">
      {!isReady(account) ? (
        <Alert tone="info" title="Angebote gehen noch nicht online">
          <p>
            In der <TextLink href={EBAY_SETUP_HREF}>Einrichtung</TextLink> {open === 1 ? "steht" : "stehen"} noch{" "}
            {open} von {READINESS_STEPS.length} Signalen auf Rot.
          </p>
        </Alert>
      ) : null}
      <ListingsPanel account={account} />
      {account.mode === "test" ? (
        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
          <OrdersPanel account={account} />
          <TestMarketPanel />
        </div>
      ) : (
        <OrdersPanel account={account} />
      )}
    </div>
  );
}

// --- Listings -------------------------------------------------------------------------

function ListingsPanel({ account }: { account: EbayStatusOut }) {
  const listings = useEbayListings(true);
  const online = listings.data?.filter((listing) => listing.status === "active").length ?? 0;
  return (
    <Panel
      title="Angebote"
      code="EBY 04"
      actions={
        listings.data ? (
          <span className="text-hint text-ink-tertiary">{`${online} online von ${listings.data.length}`}</span>
        ) : null
      }
    >
      {listings.isPending ? (
        <PendingNotice>Angebote werden geladen …</PendingNotice>
      ) : listings.isError ? (
        <p role="alert" className="text-small text-danger">
          {errorMessage(listings.error)}
        </p>
      ) : listings.data.length === 0 ? (
        <p className="text-small text-ink-secondary">
          Noch nichts auf eBay. Im Katalog wählst du bei jedem Modell unter „eBay“, welche Maßstäbe dort angeboten
          werden.
        </p>
      ) : (
        <ul className="divide-y divide-line">
          {listings.data.map((listing) => (
            <ListingRow key={listing.id} listing={listing} canSync={isReady(account)} />
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function ListingRow({
  listing,
  canSync,
  compact = false,
}: {
  listing: ListingOut;
  canSync: boolean;
  compact?: boolean;
}) {
  const refresh = useEbayRefresh();
  const sync = useMutation<ListingOut, ApiProblem>({
    mutationFn: () => syncEbayListing(listing.id),
    onSettled: refresh,
  });
  const state = listingState(listing);
  const prices = listing.items.map((item) => item.price_cents);
  const quantity = listing.items.reduce((sum, item) => sum + item.quantity, 0);

  return (
    // Compact (the editor's narrow column): everything stacked, the actions below.
    <li className={cn("grid gap-x-4 gap-y-2 py-3", !compact && "sm:grid-cols-[minmax(0,1fr)_auto]")}>
      <div className="min-w-0">
        {!compact ? (
          <p className="text-small font-medium break-words">
            {listing.product ? (
              <Link href={`/admin/katalog/${listing.product.product_id}` as Route} className="hover:underline">
                {listing.product.name}
              </Link>
            ) : (
              "Gelöschtes Modell"
            )}{" "}
            <span className="text-ink-tertiary">· {listing.scale_code}</span>
          </p>
        ) : null}
        <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1">
          <StatusBadge tone={state.tone} busy={state.busy}>
            {state.label}
          </StatusBadge>
          <span className="font-mono text-hint whitespace-nowrap text-ink-tertiary">{listing.group_key}</span>
          {listing.items.length > 0 ? (
            <span className="text-hint whitespace-nowrap text-ink-secondary tabular-nums">
              {listing.items.length === 1 ? "1 Ausführung" : `${listing.items.length} Ausführungen`} · {quantity} Stück ·{" "}
              {Math.min(...prices) === Math.max(...prices)
                ? formatPrice(prices[0] ?? 0)
                : `${formatPrice(Math.min(...prices))} – ${formatPrice(Math.max(...prices))}`}
            </span>
          ) : null}
        </p>
        {state.detail ? <p className="mt-1 text-hint text-ink-secondary">{state.detail}</p> : null}
        {sync.isError ? (
          <p role="alert" className="mt-1 text-hint text-danger">
            {errorMessage(sync.error)}
          </p>
        ) : null}
      </div>
      <div className={cn("flex flex-wrap items-center gap-2", !compact && "sm:justify-end")}>
        {listing.url ? (
          <Button asChild variant="ghost" size="sm">
            <a href={listing.url} target="_blank" rel="noreferrer">
              Auf eBay ansehen
            </a>
          </Button>
        ) : listing.external_id && listing.status !== "ended" ? (
          <span
            className="font-mono text-hint whitespace-nowrap text-ink-tertiary"
            title="Nummer auf dem Testmarktplatz"
          >
            {`Nr. ${listing.external_id}`}
          </span>
        ) : null}
        {canSync ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={sync.isPending}
            aria-busy={sync.isPending || undefined}
            onClick={() => sync.mutate()}
          >
            {sync.isPending ? "Gleicht ab …" : "Jetzt abgleichen"}
          </Button>
        ) : null}
      </div>
    </li>
  );
}

// --- Orders ---------------------------------------------------------------------------

function OrdersPanel({ account }: { account: EbayStatusOut }) {
  const refresh = useEbayRefresh();
  const orders = useEbayOrders(true);
  const fetchNow = useMutation<FetchOut, ApiProblem>({ mutationFn: () => fetchEbayOrders(), onSettled: refresh });
  const connected = account.status === "connected";
  return (
    <Panel
      title="Bestellungen von eBay"
      code="EBY 05"
      actions={
        connected ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={fetchNow.isPending}
            aria-busy={fetchNow.isPending || undefined}
            onClick={() => fetchNow.mutate()}
          >
            {fetchNow.isPending ? "Fragt eBay …" : "Jetzt abholen"}
          </Button>
        ) : null
      }
    >
      <p className="mb-4 text-hint text-ink-tertiary">
        {account.orders_checked_until
          ? `Zuletzt bei eBay nachgesehen: ${formatEventTime(new Date(account.orders_checked_until))}. `
          : null}
        Bezahlte Bestellungen erscheinen automatisch unter „Bestellungen“ und werden wie Shop-Bestellungen gepackt. Die
        Sendungsnummer geht beim Versand an eBay.
      </p>
      {fetchNow.isError ? (
        <p role="alert" className="mb-3 text-small text-danger">
          {errorMessage(fetchNow.error)}
        </p>
      ) : null}
      {orders.isPending ? (
        <PendingNotice>Bestellungen werden geladen …</PendingNotice>
      ) : orders.isError ? (
        <p role="alert" className="text-small text-danger">
          {errorMessage(orders.error)}
        </p>
      ) : orders.data.length === 0 ? (
        <p className="text-small text-ink-secondary">Noch keine Bestellung von eBay.</p>
      ) : (
        <ul className="divide-y divide-line">
          {orders.data.map((order) => (
            <OrderRow key={order.id} order={order} testMarket={account.mode === "test"} />
          ))}
        </ul>
      )}
    </Panel>
  );
}

function OrderRow({ order, testMarket }: { order: MarketplaceOrderOut; testMarket: boolean }) {
  const refresh = useEbayRefresh();
  const report = useMutation<MarketplaceOrderOut, ApiProblem>({
    mutationFn: () => reportEbayShipment(order.id),
    onSettled: refresh,
  });
  const cancel = useMutation<void, ApiProblem>({
    mutationFn: () => cancelEbayTestSale(order.external_id),
    onSettled: refresh,
  });
  const pieces = order.lines.reduce((sum, line) => sum + line.quantity, 0);
  const failure = report.error ?? cancel.error;
  return (
    <li className="grid gap-x-4 gap-y-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto]">
      <div className="min-w-0">
        <p className="flex flex-wrap items-baseline gap-x-3 text-small">
          <span className="font-mono">{order.external_id}</span>
          {order.order_number ? (
            <Link href={`/admin/bestellungen/${order.order_id}` as Route} className="text-accent hover:underline">
              {order.order_number}
            </Link>
          ) : null}
          {order.buyer_erased_at ? (
            <span className="text-ink-tertiary italic">
              Käuferdaten gelöscht am {formatLongDate(new Date(order.buyer_erased_at))}
            </span>
          ) : (
            <span className="text-ink-secondary">
              {order.recipient}, {order.city}
            </span>
          )}
        </p>
        <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1">
          <StatusBadge tone={ORDER_STATUS_TONES[order.status]}>{ORDER_STATUS_LABELS[order.status]}</StatusBadge>
          <span className="text-hint text-ink-secondary tabular-nums">
            {pieces === 1 ? "1 Stück" : `${pieces} Stück`} · {formatPrice(order.total_cents)} ·{" "}
            {formatEventTime(new Date(order.paid_at))}
          </span>
        </p>
        <p className="mt-1 truncate text-hint text-ink-tertiary">{order.lines.map((line) => line.title).join(", ")}</p>
        {order.problem ? <p className="mt-1 text-hint text-danger">{order.problem}</p> : null}
        {failure ? (
          <p role="alert" className="mt-1 text-hint text-danger">
            {errorMessage(failure)}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-2 sm:justify-end">
        {order.status === "received" && order.problem ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={report.isPending}
            onClick={() => report.mutate()}
          >
            Versand erneut melden
          </Button>
        ) : null}
        {testMarket && order.status === "received" ? (
          <Button type="button" variant="ghost" size="sm" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            Als Käufer stornieren
          </Button>
        ) : null}
      </div>
    </li>
  );
}

// --- Test marketplace -----------------------------------------------------------------

function TestMarketPanel() {
  const refresh = useEbayRefresh();
  const listings = useEbayListings(true);
  const offered = (listings.data ?? [])
    .filter((listing) => listing.status === "active")
    .flatMap((listing) =>
      listing.items.map((item) => ({
        sku: item.sku,
        label: `${listing.product?.name ?? listing.group_key} · ${item.sku} · ${formatPrice(item.price_cents)}`,
      })),
    );
  const [sku, setSku] = useState("");
  const [quantity, setQuantity] = useState("1");
  const chosen = sku || offered[0]?.sku || "";
  const sell = useMutation<string, ApiProblem>({
    mutationFn: async () => (await createEbayTestSale({ sku: chosen, quantity: Number(quantity) })).external_id,
    onSettled: refresh,
  });

  return (
    <Panel title="Testmarktplatz" code="EBY 06">
      <p className="mb-4 text-hint text-ink-tertiary">
        Kauf ein Angebot, wie es ein Käufer auf eBay täte: Die Bestellung kommt sofort herein und läuft durch Lager,
        Packen und Versand. Es fließt kein Geld, nichts verlässt den Server.
      </p>
      {offered.length === 0 ? (
        <p className="text-small text-ink-secondary">Sobald ein Angebot online ist, lässt es sich hier kaufen.</p>
      ) : (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            sell.mutate();
          }}
          noValidate
        >
          <FormField label="Angebot">
            {(control) => (
              <Select {...control} value={chosen} onChange={(event) => setSku(event.target.value)}>
                {offered.map((option) => (
                  <option key={option.sku} value={option.sku}>
                    {option.label}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
          <FormField label="Stück">
            {(control) => (
              <Input
                {...control}
                type="number"
                inputMode="numeric"
                min={1}
                max={99}
                className="w-24"
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
              />
            )}
          </FormField>
          {sell.isError ? (
            <p role="alert" className="text-small text-danger">
              {errorMessage(sell.error)}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" size="sm" disabled={sell.isPending} aria-busy={sell.isPending || undefined}>
              {sell.isPending ? "Kauft …" : "Als Käufer kaufen"}
            </Button>
            {sell.isSuccess ? <span className="text-hint text-success">{`Gekauft: ${sell.data}`}</span> : null}
          </div>
        </form>
      )}
    </Panel>
  );
}
