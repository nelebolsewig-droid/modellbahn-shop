"use client";

import { Indicator, Item } from "@radix-ui/react-radio-group";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { Alert, Callout } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { RadioGroup } from "@/components/ui/radio-group";
import type { OrderOut, PaymentInMethod } from "@/lib/api/generated/model";
import {
  getGetOrderByTokenQueryKey,
  payOrder,
  syncOrderPayment,
  useGetOrderByToken,
  useGetPaymentProvider,
} from "@/lib/api/generated/store-sales/store-sales";
import { isApiProblem, type ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { formatLongDate, formatClock } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { IDEMPOTENCY_HEADER, useIdempotencyKeys } from "@/lib/sales/idempotency";
import { TEST_PAYMENT_METHODS } from "@/lib/sales/labels";
import { openPaymentPage } from "@/lib/sales/payment-page";
import { cn } from "@/lib/utils";

/** How often the page asks SumUp after the customer came back, and how far apart. */
export const RETURN_CHECKS = 3;
export const RETURN_CHECK_INTERVAL_MS = 3000;

/**
 * The payment step (ADR 0019). With SumUp the customer pays on SumUp's page and comes
 * back here; the shop then asks SumUp itself how it went. Without a provider in
 * development it is a test payment: the customer picks what the provider answers.
 */
export function PaymentView({ token }: { token: string }) {
  const order = useGetOrderByToken(token);
  const provider = useGetPaymentProvider();
  const statusHref = `/bestellung/${token}` as Route;

  if (order.isPending || provider.isPending) {
    return <PendingNotice>Die Zahlung wird vorbereitet …</PendingNotice>;
  }
  if (order.isError || provider.isError) {
    return (
      <Alert tone="danger" title="Die Bestellung konnte nicht geladen werden">
        <p>{errorMessage(order.error ?? provider.error)}</p>
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
  switch (provider.data.provider) {
    case "sumup":
      return <SumUpSheet order={order.data} token={token} statusHref={statusHref} />;
    case "mock":
      return <TestPaymentSheet order={order.data} token={token} statusHref={statusHref} />;
    case "off":
      return (
        <PaymentFrame order={order.data} statusHref={statusHref}>
          <Alert tone="info" title="Bezahlen ist gerade nicht möglich">
            <p>Im Moment nehmen wir keine Zahlungen an. Wir melden uns per E-Mail bei dir.</p>
          </Alert>
        </PaymentFrame>
      );
  }
}

type SheetProps = { order: OrderOut; token: string; statusHref: Route };

/** Show the order the server answered with; a paid one continues on its status page. */
function useShowOrder(token: string, statusHref: Route) {
  const router = useRouter();
  const queryClient = useQueryClient();
  return useCallback(
    (updated: OrderOut) => {
      queryClient.setQueryData(getGetOrderByTokenQueryKey(token), updated);
      if (updated.status === "paid") {
        router.push(statusHref);
      }
    },
    [queryClient, router, statusHref, token],
  );
}

function usePayment(token: string, onAnswer: (updated: OrderOut) => void) {
  const queryClient = useQueryClient();
  const { keyFor, settle } = useIdempotencyKeys();
  return useMutation<OrderOut, ApiProblem, PaymentInMethod>({
    mutationFn: (chosen) => {
      const request = { method: chosen };
      return payOrder(token, request, { headers: { [IDEMPOTENCY_HEADER]: keyFor({ token, ...request }) } });
    },
    onSuccess(updated) {
      // A declined payment is done too: the next attempt is a new request.
      settle();
      onAnswer(updated);
    },
    onError(error) {
      if (isApiProblem(error) && error.code === "order_not_payable") {
        void queryClient.invalidateQueries({ queryKey: getGetOrderByTokenQueryKey(token) });
      }
    },
  });
}

function SumUpSheet({ order, token, statusHref }: SheetProps) {
  const show = useShowOrder(token, statusHref);
  const pay = usePayment(token, (updated) => {
    if (updated.payment_url) {
      openPaymentPage(updated.payment_url);
    } else {
      show(updated);
    }
  });
  const pageUrl = order.payment_url;
  // Back from SumUp (or the page opened again while a payment is open): ask SumUp, and a
  // few times more, since its answer may come a moment after the customer.
  const check = useQuery<OrderOut, ApiProblem>({
    queryKey: ["payment-check", token],
    queryFn: () => syncOrderPayment(token),
    enabled: pageUrl !== null,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchInterval: (query) =>
      query.state.data?.payment_url && query.state.dataUpdateCount < RETURN_CHECKS ? RETURN_CHECK_INTERVAL_MS : false,
  });
  useEffect(() => {
    if (check.data !== undefined) {
      show(check.data);
    }
  }, [check.data, show]);

  const lastPayment = order.payments.at(-1);
  const expired = lastPayment?.status === "failed" && lastPayment.failure_code === "expired";

  if (pageUrl !== null) {
    return (
      <PaymentFrame order={order} statusHref={statusHref} badge={<SumUpBadge />}>
        {check.isPending ? (
          <PendingNotice>Wir fragen bei SumUp nach, wie die Zahlung ausging …</PendingNotice>
        ) : (
          <div className="space-y-6">
            {check.isError ? (
              <Alert tone="danger" title="SumUp antwortet gerade nicht">
                <p>{errorMessage(check.error)}</p>
              </Alert>
            ) : (
              <Callout tone="info" title="Die Zahlung ist noch nicht abgeschlossen">
                <p>
                  Hast du gerade bezahlt? Dann kann die Bestätigung einen Moment dauern. Sobald das Geld da ist, schicken
                  wir dir eine E-Mail.
                </p>
              </Callout>
            )}
            <div className="flex flex-wrap gap-3">
              <Button asChild>
                <a href={pageUrl}>Weiter zu SumUp</a>
              </Button>
              <Button
                variant="secondary"
                onClick={() => void check.refetch()}
                disabled={check.isFetching}
                aria-busy={check.isFetching || undefined}
              >
                {check.isFetching ? "Wird geprüft …" : "Erneut prüfen"}
              </Button>
            </div>
          </div>
        )}
      </PaymentFrame>
    );
  }

  return (
    <PaymentFrame
      order={order}
      statusHref={statusHref}
      badge={<SumUpBadge />}
      onSubmit={() => pay.mutate("sumup")}
    >
      <p className="text-small text-ink-secondary">
        Du bezahlst auf der sicheren Seite von SumUp, unserem Zahlungsdienst: mit Kredit- oder Debitkarte, je nach Gerät
        auch mit Apple Pay oder Google Pay. Danach kommst du hierher zurück.
      </p>
      <div role="alert" className="not-empty:mt-6">
        {expired && !pay.isError ? (
          <p className="text-small text-ink-secondary">
            Die letzte Bezahlseite ist abgelaufen, es wurde nichts abgebucht. Starte die Zahlung einfach neu.
          </p>
        ) : null}
        {pay.isError ? <p className="text-small font-medium text-danger">{errorMessage(pay.error)}</p> : null}
      </div>
      <Button
        type="submit"
        className="mt-6 w-full sm:w-auto"
        disabled={pay.isPending || pay.isSuccess}
        aria-busy={pay.isPending || pay.isSuccess || undefined}
      >
        {pay.isPending || pay.isSuccess ? "SumUp wird geöffnet …" : `${formatPrice(order.totals.total_cents)} bezahlen`}
      </Button>
    </PaymentFrame>
  );
}

function SumUpBadge() {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-line px-3 py-1 text-hint font-medium text-ink-secondary">
      <svg aria-hidden viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="3" y="7" width="10" height="7" rx="1.5" />
        <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
      </svg>
      Sicher bezahlen mit SumUp
    </span>
  );
}

function TestPaymentSheet({ order, token, statusHref }: SheetProps) {
  const show = useShowOrder(token, statusHref);
  const [method, setMethod] = useState<PaymentInMethod>("succeeds");
  const pay = usePayment(token, show);
  const lastPayment = order.payments.at(-1);
  const declined = pay.isSuccess && pay.data.status === "pending_payment" && lastPayment?.status === "failed";

  return (
    <PaymentFrame
      order={order}
      statusHref={statusHref}
      onSubmit={() => pay.mutate(method)}
      badge={
        <span className="rounded-full border border-dashed border-warning px-3 py-1 text-hint font-medium text-warning">
          Testzahlung · kein echtes Geld
        </span>
      }
    >
      <fieldset>
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
    </PaymentFrame>
  );
}

/** The sheet around every way to pay: the amount, the provider's badge, the due time. */
function PaymentFrame({
  order,
  statusHref,
  badge,
  onSubmit,
  children,
}: {
  order: OrderOut;
  statusHref: Route;
  badge?: ReactNode;
  onSubmit?: () => void;
  children: ReactNode;
}) {
  const body = <div className="px-6 py-6 sm:px-8">{children}</div>;
  const sheet = (
    <>
      <div className="flex flex-wrap items-baseline justify-between gap-4 border-b border-line px-6 py-6 sm:px-8">
        <div>
          <p className="label-caps text-ink-tertiary">Zu zahlen</p>
          <p className="mt-2 text-display tabular-nums">{formatPrice(order.totals.total_cents)}</p>
        </div>
        {badge}
      </div>
      {body}
    </>
  );
  const frame = "mt-10 overflow-hidden rounded-lg border border-line bg-surface";
  return (
    <div>
      <p className="font-mono text-hint text-ink-tertiary">Bestellung {order.number}</p>
      <h1 className="mt-4 text-title">Bezahlen</h1>
      {onSubmit ? (
        <form
          className={frame}
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          {sheet}
        </form>
      ) : (
        <div className={frame}>{sheet}</div>
      )}
      <p className="mt-6 text-hint text-ink-tertiary">
        Du kannst auch später bezahlen
        {order.payment_due_at
          ? `, bis ${formatLongDate(new Date(order.payment_due_at))}, ${formatClock(new Date(order.payment_due_at))} Uhr`
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
