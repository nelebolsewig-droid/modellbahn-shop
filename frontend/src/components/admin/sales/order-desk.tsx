"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { PickList, PickProgress } from "@/components/admin/inventory/pick-list";
import { Panel } from "@/components/admin/panel";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
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
  shipOrder,
  useGetOrder,
} from "@/lib/api/generated/admin-sales/admin-sales";
import type { AdminOrderOut, PickListOut, StaffRole } from "@/lib/api/generated/model";
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
} from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";
import {
  CANCEL_REASON_LABELS,
  CARRIERS,
  ORDER_STATUS_LABELS,
  ORDER_STATUS_TONES,
  PAYMENT_STATUS_LABELS,
} from "@/lib/sales/labels";
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
  const cancellable = MAY_CANCEL.has(staffRole) && (data.status === "pending_payment" || data.status === "paid");

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
          </p>
          <h1 className="mt-3 font-mono text-heading sm:text-title">{data.number}</h1>
          <p className="mt-2 text-small text-ink-secondary">
            Eingegangen am {formatLongDate(new Date(data.placed_at))}, {formatClock(new Date(data.placed_at))} Uhr ·{" "}
            {data.customer_account_id ? "Kundenkonto" : "Gastbestellung"}
          </p>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="space-y-6">
          <Panel title="Verlauf" code="VK 11">
            <OrderTimeline order={data} />
            <StateNote order={data} />
            {data.payments.length > 0 ? <Payments order={data} /> : null}
          </Panel>
          <Panel title="Artikel" code="VK 12">
            <OrderLines lines={data.lines} linkToProducts={false} />
            <OrderTotals totals={data.totals} countryName={data.shipping_address.country_name} className="mt-5 sm:ml-auto sm:max-w-sm" />
          </Panel>
          {hasPickList(data) ? (
            <Panel title="Kommissionieren" code="VK 16">
              <Picking order={data} list={pickList.data} error={pickList.error} mayAllocate={MAY_CANCEL.has(staffRole)} />
            </Panel>
          ) : null}
        </div>

        <div className="space-y-6">
          <Panel title="Versand" code="VK 13">
            <ParcelLabel order={data} />
            <div className="mt-5">
              <Dispatch order={data} pickList={pickList.data} onShipped={store} />
            </div>
          </Panel>
          <Panel title="Kunde" code="VK 14">
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
                  {data.customer_account_id
                    ? "mit Kundenkonto"
                    : "als Gast; bestätigt ein Konto diese Adresse, wandert die Bestellung dorthin"}
                </dd>
              </div>
            </dl>
          </Panel>
          {cancellable ? (
            <Panel title="Stornieren" code="VK 15">
              <CancelOrder order={data} onCancelled={store} />
            </Panel>
          ) : null}
        </div>
      </div>
    </>
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
              {PAYMENT_STATUS_LABELS[payment.status]}
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
    return (
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-small">
        <dt className="text-ink-secondary">Versendet</dt>
        <dd>
          {formatLongDate(new Date(order.shipped_at))}, {formatClock(new Date(order.shipped_at))} Uhr
        </dd>
        <dt className="text-ink-secondary">Versand mit</dt>
        <dd>{order.carrier || "—"}</dd>
        <dt className="text-ink-secondary">Sendung</dt>
        <dd className="font-mono break-all">{order.tracking_number || "—"}</dd>
      </dl>
    );
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
  if (!pickList.complete) {
    return (
      <p className="text-small text-ink-secondary">
        Verschickt wird, wenn alles kommissioniert ist: noch {pickList.total - pickList.picked} von {pickList.total} Stück.
      </p>
    );
  }
  return <ShipForm order={order} onShipped={onShipped} />;
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
          <Button asChild size="sm">
            <Link href={`/admin/scanner?bestellung=${order.id}` as Route}>Mit dem Scanner kommissionieren</Link>
          </Button>
        ) : null}
      </div>
      <PickList list={list} className="mt-5" />
    </>
  );
}

function ShipForm({ order, onShipped }: { order: AdminOrderOut; onShipped: (order: AdminOrderOut) => void }) {
  const { form, onSubmit, formError } = useApiForm({
    schema: shipSchema,
    defaultValues: { carrier: "DHL", tracking_number: "" },
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
        <FormField label="Sendungsnummer" hint="Optional; steht dann in der Versandmail." error={errors.tracking_number?.message}>
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
  const paid = order.status === "paid";
  const { form, onSubmit, formError } = useApiForm({
    schema: cancelSchema,
    defaultValues: { note: "" },
    async submit(values) {
      const cancelled = await cancelOrder(order.id, values);
      setOpen(false);
      onCancelled(cancelled);
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  return (
    <>
      <p className="text-small text-ink-secondary">
        {paid
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
            <FormField label="Hinweis an den Kunden" hint="Optional; steht in der Stornomail, z. B. der Grund." error={errors.note?.message}>
              {(control) => <Textarea {...control} {...register("note")} maxLength={300} className="min-h-24" />}
            </FormField>
            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Behalten
                </Button>
              </DialogClose>
              <SubmitButton variant="danger" pending={isSubmitting} pendingLabel="Wird storniert …">
                Stornieren
              </SubmitButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
