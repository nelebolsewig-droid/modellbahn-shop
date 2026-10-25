"use client";

import { Indicator, Item } from "@radix-ui/react-radio-group";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { RadioGroup } from "@/components/ui/radio-group";
import type { OrderOut, PaymentInMethod } from "@/lib/api/generated/model";
import {
  getGetOrderByTokenQueryKey,
  payOrder,
  useGetOrderByToken,
} from "@/lib/api/generated/store-sales/store-sales";
import { isApiProblem, type ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { formatLongDate, formatTime } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { IDEMPOTENCY_HEADER, useIdempotencyKeys } from "@/lib/sales/idempotency";
import { TEST_PAYMENT_METHODS } from "@/lib/sales/labels";
import { cn } from "@/lib/utils";

/**
 * The payment step. Until a payment provider is connected this is a test payment:
 * the customer picks what the provider answers, nothing is charged.
 */
export function PaymentView({ token }: { token: string }) {
  const order = useGetOrderByToken(token);
  const statusHref = `/bestellung/${token}` as Route;

  if (order.isPending) {
    return <PendingNotice>Die Zahlung wird vorbereitet …</PendingNotice>;
  }
  if (order.isError) {
    return (
      <Alert tone="danger" title="Die Bestellung konnte nicht geladen werden">
        <p>{errorMessage(order.error)}</p>
      </Alert>
    );
  }
  if (order.data.status !== "pending_payment") {
    return (
      <div className="space-y-6">
        <Alert tone="info" title={order.data.status === "cancelled" ? "Diese Bestellung ist storniert" : "Diese Bestellung ist bezahlt"}>
          <p>Hier gibt es nichts mehr zu bezahlen.</p>
        </Alert>
        <Button asChild variant="secondary">
          <Link href={statusHref}>Zur Bestellung</Link>
        </Button>
      </div>
    );
  }
  return <PaymentSheet order={order.data} token={token} statusHref={statusHref} />;
}

function PaymentSheet({ order, token, statusHref }: { order: OrderOut; token: string; statusHref: Route }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [method, setMethod] = useState<PaymentInMethod>("succeeds");
  const { keyFor, settle } = useIdempotencyKeys();
  const pay = useMutation<OrderOut, ApiProblem, PaymentInMethod>({
    mutationFn: (chosen) => {
      const request = { method: chosen };
      return payOrder(token, request, { headers: { [IDEMPOTENCY_HEADER]: keyFor({ token, ...request }) } });
    },
    onSuccess(updated) {
      queryClient.setQueryData(getGetOrderByTokenQueryKey(token), updated);
      // A declined payment is done too: the next attempt is a new request.
      settle();
      if (updated.status === "paid") {
        router.push(statusHref);
      }
    },
    onError(error) {
      if (isApiProblem(error) && error.code === "order_not_payable") {
        void queryClient.invalidateQueries({ queryKey: getGetOrderByTokenQueryKey(token) });
      }
    },
  });
  const lastPayment = order.payments.at(-1);
  const declined = pay.isSuccess && pay.data.status === "pending_payment" && lastPayment?.status === "failed";

  return (
    <div>
      <p className="font-mono text-hint text-ink-tertiary">Bestellung {order.number}</p>
      <h1 className="mt-4 text-title">Bezahlen</h1>

      <form
        className="mt-10 overflow-hidden rounded-lg border border-line bg-surface"
        onSubmit={(event) => {
          event.preventDefault();
          pay.mutate(method);
        }}
      >
        <div className="flex flex-wrap items-baseline justify-between gap-4 border-b border-line px-6 py-6 sm:px-8">
          <div>
            <p className="label-caps text-ink-tertiary">Zu zahlen</p>
            <p className="mt-2 text-display tabular-nums">{formatPrice(order.totals.total_cents)}</p>
          </div>
          <span className="rounded-full border border-dashed border-warning px-3 py-1 text-hint font-medium text-warning">
            Testzahlung · kein echtes Geld
          </span>
        </div>
        <fieldset className="px-6 py-6 sm:px-8">
          <legend className="sr-only">Ergebnis der Testzahlung</legend>
          <p className="text-small text-ink-secondary">
            Noch ist kein Zahlungsdienst angebunden. Wähle, wie die Zahlung ausgehen soll:
          </p>
          <RadioGroup
            aria-label="Ergebnis der Testzahlung"
            value={method}
            onValueChange={(value) => setMethod(value as PaymentInMethod)}
            className="mt-5 space-y-3"
          >
            {TEST_PAYMENT_METHODS.map((option) => (
              <Item
                key={option.value}
                value={option.value}
                className={cn(
                  "flex w-full cursor-pointer items-start gap-4 rounded-md border border-line-strong bg-canvas p-4 text-left",
                  "transition-[border-color,box-shadow] duration-150 hover:border-ink-secondary",
                  "data-[state=checked]:border-selected data-[state=checked]:bg-surface data-[state=checked]:shadow-[inset_0_0_0_1px_var(--selected)]",
                )}
              >
                <span className="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border border-line-control">
                  <Indicator className="size-2 rounded-full bg-selected" />
                </span>
                <span>
                  <span className="block font-medium">{option.label}</span>
                  <span className="mt-0.5 block text-hint text-ink-tertiary">{option.description}</span>
                </span>
              </Item>
            ))}
          </RadioGroup>
          <div role="alert" className="not-empty:mt-6">
            {declined ? (
              <p className="text-small font-medium text-danger">
                Die Zahlung wurde abgelehnt. Es wurde nichts abgebucht; du kannst es gleich noch einmal versuchen.
              </p>
            ) : null}
            {pay.isError ? <p className="text-small font-medium text-danger">{errorMessage(pay.error)}</p> : null}
          </div>
          <Button type="submit" className="mt-6 w-full sm:w-auto" disabled={pay.isPending} aria-busy={pay.isPending || undefined}>
            {pay.isPending ? "Zahlung läuft …" : `${formatPrice(order.totals.total_cents)} bezahlen`}
          </Button>
        </fieldset>
      </form>
      <p className="mt-6 text-hint text-ink-tertiary">
        Du kannst auch später bezahlen
        {order.payment_due_at
          ? `, bis ${formatLongDate(new Date(order.payment_due_at))}, ${formatTime(new Date(order.payment_due_at))} Uhr`
          : ""}
        : Die E-Mail zu deiner Bestellung enthält den Link hierher. Zur{" "}
        <Link href={statusHref} className="underline underline-offset-4 hover:text-ink">
          Übersicht der Bestellung
        </Link>
        .
      </p>
    </div>
  );
}
