"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { PickList, PickProgress } from "@/components/admin/inventory/pick-list";
import { Panel } from "@/components/admin/panel";
import { ChannelBadge } from "@/components/admin/sales/channel-badge";
import { RefundPanel } from "@/components/admin/sales/refund-panel";
import { RefundRefusal, refusalOf } from "@/components/admin/sales/refund-refusal";
import { LabelReprint, ShippingLabelDesk, useActiveLabel } from "@/components/admin/sales/shipping-label";
import { TransferBooking, awaitedTransfer, paidByTransfer } from "@/components/admin/sales/transfer-booking";
import { OrderWithdrawals } from "@/components/admin/sales/withdrawals";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { InvoiceDocuments } from "@/components/shop/invoice-documents";
import { OrderLines, OrderTimeline } from "@/components/shop/order-parts";
import { OrderTotals } from "@/components/shop/order-totals";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { StatusBadge } from "@/components/ui/status-badge";
import { Textarea } from "@/components/ui/textarea";
import {
  allocateOrder,
  getGetPickListQueryKey,
  useGetPickList,
} from "@/lib/api/generated/admin-inventory/admin-inventory";
import {
  cancelOrder,
  getGetOrderQueryKey,
  getListOrdersQueryKey,
  getListWithdrawalsQueryKey,
  shipOrder,
  getGetInvoiceDocumentUrl,
  useGetShippingSetup,
  useGetOrder,
} from "@/lib/api/generated/admin-sales/admin-sales";
import type { AdminOrderOut, PickListOut, ShippingLabelOut, StaffRole } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import { SHOP_NAME } from "@/lib/config";
import { useApiForm } from "@/lib/forms/use-api-form";
import { formatLongDate, formatClock } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import {
  ADMIN_EVENTS_URL,
  INVENTORY_EVENT_TYPES,
  ORDER_EVENT_TYPES,
  orderEventOf,
  stockEventOf,
  withdrawalEventOf,
} from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";
import {
  CANCEL_REASON_LABELS,
  CARRIERS,
  ORDER_STATUS_LABELS,
  ORDER_STATUS_TONES,
  paymentLabel,
} from "@/lib/sales/labels";
import { ACTION_ANCHORS, type NextAction, nextAction } from "@/lib/sales/next-action";
import { cn } from "@/lib/utils";
import { cancelSchema, shipSchema } from "@/lib/validation/orders";

/** Packers ship, but cancelling (and with it refunding) is for owner and staff. */
const MAY_CANCEL: ReadonlySet<StaffRole> = new Set(["owner", "staff"]);

/** The orders whose pieces come off the shelves: paid ones, and shipped ones for the record. */
function hasPickList(order: AdminOrderOut | undefined): boolean {
  return order?.status === "paid" || order?.status === "shipped";
}

type OrderDeskProps = {
  orderId: string;
  staffRole: StaffRole;
  onStreamClosed: () => void;
};

/** One order in the Stellwerk: what to pack, where to send it, and what happened so far. */
export function OrderDesk({ orderId, staffRole, onStreamClosed }: OrderDeskProps) {
  const queryClient = useQueryClient();
  const order = useGetOrder(orderId);
  const pickList = useGetPickList(orderId, { query: { enabled: hasPickList(order.data) } });
  // A payment, a colleague's dispatch or a piece picked on the phone shows up without reloading.
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: [...ORDER_EVENT_TYPES, ...INVENTORY_EVENT_TYPES],
    onMessage(data) {
      if (withdrawalEventOf(data)?.orderId === orderId) {
        void queryClient.invalidateQueries({ queryKey: getListWithdrawalsQueryKey({ order_id: orderId }) });
      }
      if (orderEventOf(data)?.orderId === orderId) {
        void queryClient.invalidateQueries({ queryKey: getGetOrderQueryKey(orderId) });
        void queryClient.invalidateQueries({ queryKey: getGetPickListQueryKey(orderId) });
      }
      if (stockEventOf(data)?.orderId === orderId) {
        void queryClient.invalidateQueries({ queryKey: getGetPickListQueryKey(orderId) });
      }
    },
    onClosed: onStreamClosed,
  });

  if (order.isPending) {
    return <PendingNotice>Die Bestellung wird geladen …</PendingNotice>;
  }
  if (order.isError) {
    return (
      <div className="space-y-4">
        <Alert tone="danger" title="Die Bestellung konnte nicht geladen werden">
          <p>{errorMessage(order.error)}</p>
        </Alert>
        <Button asChild variant="secondary">
          <Link href="/admin/bestellungen">Zurück zu den Bestellungen</Link>
        </Button>
      </div>
    );
  }
  const data = order.data;
  const store = (updated: AdminOrderOut) => {
    queryClient.setQueryData(getGetOrderQueryKey(orderId), updated);
    void queryClient.invalidateQueries({ queryKey: getListOrdersQueryKey() });
  };
  const fromEbay = data.channel === "ebay";
  // An order from eBay is cancelled on eBay (which refunds the buyer); the shop follows.
  const cancellable =
    !fromEbay && MAY_CANCEL.has(staffRole) && (data.status === "pending_payment" || data.status === "paid");

  return (
    <>
      <Link href="/admin/bestellungen" className="inline-flex items-center gap-2 text-small font-medium text-ink-secondary hover:text-ink">
        <span aria-hidden="true">←</span> Alle Bestellungen
      </Link>
      <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="label-caps text-ink-tertiary">Bestellung</span>
            <StatusBadge tone={ORDER_STATUS_TONES[data.status]}>{ORDER_STATUS_LABELS[data.status]}</StatusBadge>
            {fromEbay ? <ChannelBadge /> : null}
          </p>
          <h1 className="mt-3 font-mono text-heading sm:text-title">{data.number}</h1>
          <p className="mt-2 text-small text-ink-secondary">
            Eingegangen am {formatLongDate(new Date(data.placed_at))}, {formatClock(new Date(data.placed_at))} Uhr ·{" "}
            {fromEbay
              ? `über eBay, Bestellnummer ${data.external_ref ?? ""}`
              : data.customer_account_id
                ? "Kundenkonto"
                : "Gastbestellung"}
          </p>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>

      <NextActionBar
        action={nextAction({
          order: data,
          pickList: hasPickList(data) ? pickList.data : undefined,
          awaitingTransfer: awaitedTransfer(data) !== undefined,
          mayManage: MAY_CANCEL.has(staffRole),
        })}
      />

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        {/* In one column (the phone, where the packer works) the pick list comes first; with
            two columns it goes below history and items. */}
        <div className="flex min-w-0 flex-col gap-6">
          <OrderWithdrawals orderId={orderId} />
          {hasPickList(data) ? (
            <Panel title="Packen" id={ACTION_ANCHORS.picking} className="lg:order-last">
              <Picking order={data} list={pickList.data} error={pickList.error} mayAllocate={MAY_CANCEL.has(staffRole)} />
            </Panel>
          ) : null}
          <Panel title="Verlauf">
            <OrderTimeline order={data} />
            <StateNote order={data} />
            {data.payments.length > 0 ? <Payments order={data} /> : null}
          </Panel>
          <Panel title="Modelle">
            <OrderLines lines={data.lines} linkToProducts={false} />
            <OrderTotals totals={data.totals} countryName={data.shipping_address.country_name} className="mt-5 sm:ml-auto sm:max-w-sm" />
          </Panel>
        </div>

        <div className="space-y-6">
          {awaitedTransfer(data) && MAY_CANCEL.has(staffRole) ? (
            <Panel title="Überweisung" id={ACTION_ANCHORS.transfer}>
              <TransferBooking order={data} onBooked={store} />
            </Panel>
          ) : null}
          <Panel title="Versand" id={ACTION_ANCHORS.dispatch}>
            <ParcelLabel order={data} />
            <div className="mt-5">
              <Dispatch order={data} pickList={pickList.data} onShipped={store} />
            </div>
          </Panel>
          {data.status === "shipped" || data.invoices.length > 0 ? (
            <Panel title="Rechnungen">
              <Invoices order={data} />
            </Panel>
          ) : null}
          <Panel title="Kunde">
            <dl className="space-y-4 text-small">
              <div>
                <dt className="label-caps text-ink-tertiary">E-Mail-Adresse</dt>
                <dd className="mt-1 break-all">
                  <a href={`mailto:${data.email}?subject=${encodeURIComponent(`Bestellung ${data.number}`)}`} className="text-accent hover:underline hover:underline-offset-4">
                    {data.email}
                  </a>
                </dd>
              </div>
              <div>
                <dt className="label-caps text-ink-tertiary">Bestellt</dt>
                <dd className="mt-1">
                  {fromEbay
                    ? "auf eBay; Nachrichten an den Käufer laufen über eBay"
                    : data.customer_account_id
                    ? "mit Kundenkonto"
                    : "als Gast; bestätigt ein Konto diese Adresse, wandert die Bestellung dorthin"}
                </dd>
              </div>
            </dl>
          </Panel>
          {cancellable ? (
            <Panel title="Stornieren">
              <CancelOrder order={data} onCancelled={store} />
            </Panel>
          ) : fromEbay && data.status === "paid" ? (
            <Panel title="Stornieren">
              <p className="text-small text-ink-secondary">
                Bestellungen von eBay storniert der Käufer oder du auf eBay; eBay erstattet den Betrag. Der Shop
                übernimmt die Stornierung beim nächsten Abgleich, die Ware geht zurück ins Lager.
              </p>
            </Panel>
          ) : null}
          {!fromEbay && MAY_CANCEL.has(staffRole) && (data.status === "shipped" || data.status === "paid") ? (
            <Panel title="Erstattung">
              <RefundPanel order={data} onRefunded={store} />
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}

const ACTION_TONES = {
  act: { frame: "border-accent bg-accent-subtle", lamp: "bg-accent animate-lamp-pulse", caps: "Als Nächstes" },
  wait: { frame: "border-line-strong bg-surface", lamp: "bg-ink-tertiary", caps: "Wartet" },
  done: { frame: "border-success bg-success-subtle", lamp: "bg-success", caps: "Fertig" },
} as const;

/** The order's one main action, above everything else (ADR 0033). */
function NextActionBar({ action }: { action: NextAction }) {
  const tone = ACTION_TONES[action.tone];
  const target = action.action;
  return (
    <section aria-label="Als Nächstes" className={cn("mt-6 flex flex-wrap items-center gap-x-6 gap-y-4 border-l-4 px-5 py-4", tone.frame)}>
      <div className="min-w-0 flex-1 basis-72">
        <p className="flex items-center gap-2 label-caps text-ink-secondary">
          <span aria-hidden="true" className={cn("size-2 rounded-full", tone.lamp)} />
          {tone.caps}
        </p>
        <p className="mt-1 font-display text-heading">{action.title}</p>
        {action.text ? <p className="mt-1 text-small text-ink-secondary">{action.text}</p> : null}
      </div>
      {target ? (
        <Button asChild variant={action.tone === "act" ? "primary" : "secondary"} className="max-sm:w-full">
          {target.href.startsWith("#") ? <a href={target.href}>{target.label}</a> : <Link href={target.href as Route}>{target.label}</Link>}
        </Button>
      ) : null}
    </section>
  );
}

function StateNote({ order }: { order: AdminOrderOut }) {
  if (order.status === "pending_payment" && order.payment_due_at) {
    const due = new Date(order.payment_due_at);
    return (
      <p className="mt-6 text-small text-ink-secondary">
        Wartet auf die Zahlung bis {formatLongDate(due)}, {formatClock(due)} Uhr; danach storniert das System sie.
      </p>
    );
  }
  if (order.status === "cancelled") {
    return (
      <div className="mt-6 space-y-1 text-small text-ink-secondary">
        <p>{order.cancel_reason ? CANCEL_REASON_LABELS[order.cancel_reason] : "Storniert."}</p>
        {order.cancel_note ? <p className="text-ink">„{order.cancel_note}“</p> : null}
      </div>
    );
  }
  return null;
}

function Payments({ order }: { order: AdminOrderOut }) {
  return (
    <table className="mt-6 w-full text-left text-small">
      <caption className="mb-2 text-left label-caps text-ink-tertiary">Zahlungen</caption>
      <tbody className="divide-y divide-line border-y border-line">
        {order.payments.map((payment) => (
          <tr key={payment.created_at}>
            <td className="py-2 pr-4 text-ink-secondary tabular-nums">
              <time dateTime={payment.created_at}>
                {formatLongDate(new Date(payment.created_at))}, {formatClock(new Date(payment.created_at))}
              </time>
            </td>
            <td className="py-2 pr-4">
              {paymentLabel(payment)}
              <span className="ml-2 font-mono text-hint text-ink-tertiary">
                {payment.provider}
                {payment.failure_code ? ` · ${payment.failure_code}` : ""}
              </span>
            </td>
            <td className="py-2 text-right tabular-nums">{formatPrice(payment.amount_cents)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * The address as it goes on the parcel, framed like a shipping label: what the packer
 * copies, at a glance. The bars are decoration drawn from the order number.
 */
function ParcelLabel({ order }: { order: AdminOrderOut }) {
  const address = order.shipping_address;
  const pieces = order.lines.reduce((sum, line) => sum + line.quantity, 0);
  return (
    <figure className="rounded-md border border-dashed border-line-control bg-canvas p-4">
      <figcaption className="flex items-baseline justify-between gap-3 font-mono text-hint text-ink-tertiary">
        <span>{order.number}</span>
        <span>{pieces} Stück</span>
      </figcaption>
      <p className="mt-3 text-hint text-ink-tertiary">Absender: {SHOP_NAME}</p>
      <address className="mt-3 text-body not-italic leading-snug">
        <span className="block font-medium">{address.recipient}</span>
        {address.street}
        <br />
        {address.postal_code} {address.city}
        <br />
        <span className="label-caps">{address.country_name}</span>
      </address>
      <Barcode value={order.number} className="mt-4" />
    </figure>
  );
}

function Barcode({ value, className }: { value: string; className?: string }) {
  // Guard bars, then five bars per character: narrow or wide by the bits of its code.
  // Stable for the same number, and dense enough to read as a label at a glance.
  const widths = [1, 1, ...[...value].flatMap((char) => {
    const code = char.charCodeAt(0);
    return [0, 1, 2, 3, 4].map((bit) => 1 + ((code >> bit) & 1) * 2);
  }), 1, 1];
  let x = 0;
  const bars = widths.map((width, index) => {
    const bar = <rect key={index} x={x} y={0} width={width} height={28} />;
    x += width + (index % 3 === 2 ? 2 : 1);
    return bar;
  });
  return (
    <svg aria-hidden="true" viewBox={`0 0 ${x} 28`} preserveAspectRatio="none" className={className} width="100%" height="28" fill="currentColor">
      {bars}
    </svg>
  );
}

function Dispatch({
  order,
  pickList,
  onShipped,
}: {
  order: AdminOrderOut;
  pickList: PickListOut | undefined;
  onShipped: (order: AdminOrderOut) => void;
}) {
  if (order.status === "shipped" && order.shipped_at) {
    return <Shipped order={order} />;
  }
  if (order.status === "pending_payment") {
    return <p className="text-small text-ink-secondary">Verschickt wird erst, wenn die Zahlung eingegangen ist.</p>;
  }
  if (order.status === "cancelled") {
    return <p className="text-small text-ink-secondary">Storniert – nicht verschicken.</p>;
  }
  if (pickList === undefined) {
    return <p className="text-small text-ink-secondary">Die Pickliste wird geladen …</p>;
  }
  if (!pickList.allocated) {
    return <p className="text-small text-ink-secondary">Verschickt wird, sobald das Lager die Stücke zugeteilt hat.</p>;
  }
  // Scanning is optional: every piece with a place goes out with the parcel (ADR 0028).
  const waiting = [...new Set(pickList.items.filter((item) => item.state === "backordered").map((item) => item.title))];
  if (waiting.length > 0) {
    return (
      <p className="text-small text-ink-secondary">
        Noch nicht alles da, es wartet auf die Fertigung: {waiting.join(", ")}.
      </p>
    );
  }
  return <ReadyToShip order={order} onShipped={onShipped} />;
}

/** Packed: book the label (when a carrier is connected), then report the dispatch. */
function ReadyToShip({ order, onShipped }: { order: AdminOrderOut; onShipped: (order: AdminOrderOut) => void }) {
  const setup = useGetShippingSetup();
  const booksLabels = setup.data?.books_labels === true;
  const label = useActiveLabel(order.id, booksLabels);
  if (setup.isPending || (booksLabels && label.isPending)) {
    return <PendingNotice>Versand wird vorbereitet …</PendingNotice>;
  }
  const active = label.data ?? null;
  return (
    <div className="space-y-6">
      {booksLabels && setup.data ? (
        label.isError ? (
          <p className="text-small text-danger">{errorMessage(label.error)}</p>
        ) : (
          <ShippingLabelDesk order={order} setup={setup.data} label={active} onShipped={onShipped} />
        )
      ) : null}
      <div className={booksLabels ? "border-t border-line pt-6" : undefined}>
        {/* Keyed by the label: a new or cancelled label fills the form anew. */}
        <ShipForm key={active?.shipment_number ?? "ohne-label"} order={order} label={active} onShipped={onShipped} />
      </div>
    </div>
  );
}

function Shipped({ order }: { order: AdminOrderOut }) {
  const setup = useGetShippingSetup();
  const label = useActiveLabel(order.id, setup.data?.books_labels === true);
  const shippedAt = new Date(order.shipped_at ?? order.placed_at);
  return (
    <>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-small">
        <dt className="text-ink-secondary">Versendet</dt>
        <dd>
          {formatLongDate(shippedAt)}, {formatClock(shippedAt)} Uhr
        </dd>
        <dt className="text-ink-secondary">Versand mit</dt>
        <dd>{order.carrier || "keine Angabe"}</dd>
        <dt className="text-ink-secondary">Sendung</dt>
        <dd className={order.tracking_number ? "font-mono break-all" : undefined}>{order.tracking_number || "keine Nummer"}</dd>
      </dl>
      {label.data ? (
        <div className="mt-4">
          <LabelReprint order={order} label={label.data} />
        </div>
      ) : null}
    </>
  );
}

/**
 * The invoice the worker issued at dispatch and the corrections of later refunds (ADR
 * 0038). Without a tax number in the settings none is written: the desk says so.
 */
function Invoices({ order }: { order: AdminOrderOut }) {
  const setup = useGetShippingSetup();
  if (order.invoices.length > 0) {
    return (
      <>
        <InvoiceDocuments invoices={order.invoices} urlOf={(invoice) => getGetInvoiceDocumentUrl(order.id, invoice.id)} />
        <p className="mt-3 text-hint text-ink-tertiary">Die Rechnung ging mit der Versandmail an den Kunden.</p>
      </>
    );
  }
  if (setup.data && !setup.data.issues_invoices) {
    return (
      <p className="text-small text-ink-secondary">
        Der Shop schreibt noch keine Rechnungen: In der Einrichtung (<span className="font-mono">.env</span>) fehlt die
        Steuernummer (<span className="font-mono">MB_IMPRINT_TAX_NUMBER</span>) oder die USt-IdNr.
      </p>
    );
  }
  return <p className="text-small text-ink-secondary">Die Rechnung wird gerade geschrieben und erscheint gleich hier.</p>;
}

/** The pieces of a paid order: where they lie, what is picked, what is still being made. */
function Picking({
  order,
  list,
  error,
  mayAllocate,
}: {
  order: AdminOrderOut;
  list: PickListOut | undefined;
  error: unknown;
  mayAllocate: boolean;
}) {
  const queryClient = useQueryClient();
  const [allocating, setAllocating] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function allocate() {
    setAllocating(true);
    setProblem(null);
    try {
      queryClient.setQueryData(getGetPickListQueryKey(order.id), await allocateOrder(order.id));
    } catch (failure) {
      setProblem(errorMessage(failure));
    } finally {
      setAllocating(false);
    }
  }

  if (error) {
    return <p className="text-small text-danger">{errorMessage(error)}</p>;
  }
  if (list === undefined) {
    return <PendingNotice>Die Pickliste wird geladen …</PendingNotice>;
  }
  if (!list.allocated) {
    return (
      <div className="space-y-3">
        <p className="text-small text-ink-secondary">
          Bezahlt, aber noch ohne Stücke aus dem Lager. Das System teilt gleich nach der Zahlung zu; hängt es, hilft der Knopf.
        </p>
        {mayAllocate ? (
          <Button type="button" size="sm" onClick={() => void allocate()} disabled={allocating} aria-busy={allocating || undefined}>
            {allocating ? "Wird zugeteilt …" : "Jetzt zuteilen"}
          </Button>
        ) : null}
        <p role="alert" className="text-small font-medium text-danger">
          {problem}
        </p>
      </div>
    );
  }
  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PickProgress list={list} className="min-w-56 flex-1" />
        {order.status === "paid" && !list.complete ? (
          <Button asChild size="sm" variant="ghost">
            <Link href={`/admin/scanner?bestellung=${order.id}` as Route}>Mit dem Scanner abhaken (optional)</Link>
          </Button>
        ) : null}
      </div>
      <PickList list={list} className="mt-5" />
    </>
  );
}

function ShipForm({
  order,
  label,
  onShipped,
}: {
  order: AdminOrderOut;
  label: ShippingLabelOut | null;
  onShipped: (order: AdminOrderOut) => void;
}) {
  const { form, onSubmit, formError } = useApiForm({
    schema: shipSchema,
    defaultValues: { carrier: label?.carrier ?? "DHL", tracking_number: label?.shipment_number ?? "" },
    async submit(values) {
      onShipped(await shipOrder(order.id, values));
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  return (
    <form noValidate onSubmit={onSubmit} aria-label="Versand melden">
      <FormError message={formError?.message} className="mb-4" />
      <div className="space-y-4">
        <FormField label="Versanddienst" error={errors.carrier?.message}>
          {(control) => <Input {...control} {...register("carrier")} list="carriers" maxLength={40} />}
        </FormField>
        <datalist id="carriers">
          {CARRIERS.map((carrier) => (
            <option key={carrier} value={carrier} />
          ))}
        </datalist>
        <FormField
          label="Sendungsnummer"
          hint={label ? "Vom Label übernommen; steht mit Verfolgungslink in der Versandmail." : "Optional; steht dann in der Versandmail."}
          error={errors.tracking_number?.message}
        >
          {(control) => <Input {...control} {...register("tracking_number")} maxLength={40} className="font-mono" />}
        </FormField>
      </div>
      <SubmitButton pending={isSubmitting} pendingLabel="Wird gemeldet …" className="mt-5 w-full">
        Als versendet melden
      </SubmitButton>
      <p className="mt-3 text-hint text-ink-tertiary">Der Kunde bekommt eine E-Mail, dass sein Paket unterwegs ist.</p>
    </form>
  );
}

function CancelOrder({ order, onCancelled }: { order: AdminOrderOut; onCancelled: (order: AdminOrderOut) => void }) {
  const [open, setOpen] = useState(false);
  // SumUp's answer when it refused the refund; then the staff may refund in SumUp by hand.
  const [refusal, setRefusal] = useState<string | null>(null);
  const paid = order.status === "paid";
  const byTransfer = paidByTransfer(order);
  const { form, onSubmit, formError } = useApiForm({
    schema: cancelSchema,
    defaultValues: { note: "", refunded_by_hand: false },
    async submit(values) {
      try {
        const cancelled = await cancelOrder(order.id, values);
        setOpen(false);
        onCancelled(cancelled);
      } catch (error) {
        const reason = refusalOf(error);
        if (reason) {
          setRefusal(reason);
        }
        throw error;
      }
    },
  });
  const {
    register,
    watch,
    formState: { errors, isSubmitting },
  } = form;
  const byHand = watch("refunded_by_hand");

  return (
    <>
      <p className="text-small text-ink-secondary">
        {paid && byTransfer
          ? `Die ${formatPrice(order.totals.total_cents)} kamen per Überweisung: Ihr überweist sie zurück, eine Erinnerung kommt per E-Mail.`
          : paid
            ? `Die Zahlung über ${formatPrice(order.totals.total_cents)} wird dabei erstattet.`
            : "Die Bestellung ist noch nicht bezahlt; es wird nichts erstattet."}{" "}
        Der Kunde bekommt eine E-Mail.
      </p>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            form.reset();
            setRefusal(null);
          }
        }}
      >
        <DialogTrigger asChild>
          <Button type="button" variant="secondary" size="sm" className="mt-4 border-danger text-danger hover:border-danger hover:bg-danger-subtle">
            Bestellung stornieren …
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>{order.number} stornieren?</DialogTitle>
          <DialogDescription>
            {paid ? `${formatPrice(order.totals.total_cents)} gehen an den Kunden zurück. ` : ""}Das lässt sich nicht rückgängig
            machen.
          </DialogDescription>
          <form noValidate onSubmit={onSubmit} className="mt-6">
            <FormError message={formError?.message} />
            {refusal ? <RefundRefusal reason={refusal} /> : null}
            <FormField label="Hinweis an den Kunden" hint="Optional; steht in der Stornomail, z. B. der Grund." error={errors.note?.message}>
              {(control) => <Textarea {...control} {...register("note")} maxLength={300} className="min-h-24" />}
            </FormField>
            {paid && refusal ? (
              <label className="mt-4 flex items-start gap-3 text-small">
                <input
                  type="checkbox"
                  {...register("refunded_by_hand")}
                  className="mt-1 size-4 shrink-0 accent-[var(--selected)]"
                />
                <span>
                  Ich habe {formatPrice(order.totals.total_cents)} im SumUp-Konto selbst erstattet. Der Shop vermerkt
                  die Erstattung nur und fragt SumUp nicht noch einmal.
                </span>
              </label>
            ) : null}
            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Behalten
                </Button>
              </DialogClose>
              <SubmitButton variant="danger" pending={isSubmitting} pendingLabel="Wird storniert …">
                {byHand ? "Stornieren (schon erstattet)" : "Stornieren"}
              </SubmitButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
