"use client";

import { Indicator, Item } from "@radix-ui/react-radio-group";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { BankTransferDetails } from "@/components/shop/bank-transfer-details";
import { Alert, Callout } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { RadioGroup } from "@/components/ui/radio-group";
import type { BankTransferOut, OrderOut, PaymentInMethod } from "@/lib/api/generated/model";
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
import { openPaymentPage, reloadPaymentPage } from "@/lib/sales/payment-page";
import { cn } from "@/lib/utils";

/** How often the page asks SumUp after the customer came back, and how far apart. */
export const RETURN_CHECKS = 3;
export const RETURN_CHECK_INTERVAL_MS = 3000;

/**
 * The payment step (ADR 0019). With SumUp the customer pays on SumUp's page and comes
 * back here; the shop then asks SumUp itself how it went. Without a provider in
 * development it is a test payment: the customer picks what the provider answers.
 * Where the shop offers it, the customer may pay in advance by bank transfer instead
 * (ADR 0022); the page then shows what to transfer.
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
  if (order.data.bank_transfer) {
    return (
      <BankTransferSheet order={order.data} token={token} statusHref={statusHref} transfer={order.data.bank_transfer} />
    );
  }
  const offersTransfer = provider.data.bank_transfer ?? false;
  switch (provider.data.provider) {
    case "sumup":
      return <SumUpSheet order={order.data} token={token} statusHref={statusHref} offersTransfer={offersTransfer} />;
    case "mock":
      return <TestPaymentSheet order={order.data} token={token} statusHref={statusHref} offersTransfer={offersTransfer} />;
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
type ChoiceProps = SheetProps & { offersTransfer: boolean };

/** The two ways to pay: on the provider's page, or in advance by bank transfer. */
type Way = "provider" | "bank_transfer";

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

function SumUpSheet({ order, token, statusHref, offersTransfer }: ChoiceProps) {
  const show = useShowOrder(token, statusHref);
  const [way, setWay] = useState<Way>("provider");
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
  // Back from SumUp with the browser's back button, the page may come from the browser's
  // cache as it was left ("SumUp wird geöffnet …"): load it afresh, which asks SumUp.
  useEffect(() => {
    const reloadIfCached = (event: PageTransitionEvent) => {
      if (event.persisted) {
        reloadPaymentPage();
      }
    };
    window.addEventListener("pageshow", reloadIfCached);
    return () => window.removeEventListener("pageshow", reloadIfCached);
  }, []);

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
            {offersTransfer ? (
              <p className="text-small text-ink-secondary">
                Lieber per Überweisung?{" "}
                <button
                  type="button"
                  onClick={() => pay.mutate("bank_transfer")}
                  disabled={pay.isPending}
                  className="font-medium text-ink underline underline-offset-4 hover:text-accent"
                >
                  Vorkasse wählen
                </button>
                ; die Seite bei SumUp schließen wir dann.
              </p>
            ) : null}
            {pay.isError ? <p className="text-small font-medium text-danger">{errorMessage(pay.error)}</p> : null}
          </div>
        )}
      </PaymentFrame>
    );
  }

  return (
    <PaymentFrame
      order={order}
      statusHref={statusHref}
      badge={way === "bank_transfer" ? <TransferBadge /> : <SumUpBadge />}
      onSubmit={() => pay.mutate(way === "bank_transfer" ? "bank_transfer" : "sumup")}
    >
      {offersTransfer ? (
        <RadioGroup
          aria-label="Wie möchtest du bezahlen?"
          value={way}
          onValueChange={(value) => setWay(value as Way)}
          className="mb-6 space-y-3"
        >
          <ChoiceItem
            value="provider"
            label="Karte, Apple Pay oder Google Pay"
            description="Sofort bezahlt, auf der sicheren Seite von SumUp."
          />
          <ChoiceItem
            value="bank_transfer"
            label="Vorkasse per Überweisung"
            description="Du überweist innerhalb von zehn Tagen; wir verschicken, sobald das Geld da ist."
          />
        </RadioGroup>
      ) : null}
      <p className="text-small text-ink-secondary">
        {way === "bank_transfer"
          ? "Du bekommst gleich unsere Bankverbindung, die Bestellnummer als Verwendungszweck und einen GiroCode für deine Banking-App, auch per E-Mail."
          : "Du bezahlst auf der sicheren Seite von SumUp, unserem Zahlungsdienst: mit Kredit- oder Debitkarte, je nach Gerät auch mit Apple Pay oder Google Pay. Danach kommst du hierher zurück."}
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
        {way === "bank_transfer"
          ? pay.isPending
            ? "Wird vorbereitet …"
            : "Per Überweisung bezahlen"
          : pay.isPending || pay.isSuccess
            ? "SumUp wird geöffnet …"
            : `${formatPrice(order.totals.total_cents)} bezahlen`}
      </Button>
    </PaymentFrame>
  );
}

/** Payment in advance: what to transfer, until when, and the GiroCode (ADR 0022). */
function BankTransferSheet({ order, token, statusHref, transfer }: SheetProps & { transfer: BankTransferOut }) {
  return (
    <PaymentFrame order={order} statusHref={statusHref} badge={<TransferBadge />} byTransfer>
      <p className="text-small text-ink-secondary">
        Bitte überweise den Betrag auf unser Konto und gib als Verwendungszweck nur die Bestellnummer an; so ordnen wir
        deine Zahlung sicher zu. Sobald das Geld da ist, bekommst du eine E-Mail und wir machen dein Paket fertig.
      </p>
      <BankTransferDetails transfer={transfer} token={token} className="mt-6" />
    </PaymentFrame>
  );
}

function TransferBadge() {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-line px-3 py-1 text-hint font-medium text-ink-secondary">
      <svg aria-hidden viewBox="0 0 16 16" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M2 6.5 8 3l6 3.5M3 6.5V12m3.33-5.5V12m3.34-5.5V12M13 6.5V12M2 13.5h12" />
      </svg>
      Vorkasse · Überweisung
    </span>
  );
}

/** One way to pay in a radio group, with what it means below its name. */
function ChoiceItem({ value, label, description }: { value: string; label: string; description: string }) {
  return (
    <Item
      value={value}
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
        <span className="block font-medium">{label}</span>
        <span className="mt-0.5 block text-hint text-ink-tertiary">{description}</span>
      </span>
    </Item>
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

function TestPaymentSheet({ order, token, statusHref, offersTransfer }: ChoiceProps) {
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
            <ChoiceItem key={option.value} value={option.value} label={option.label} description={option.description} />
          ))}
          {offersTransfer ? (
            <ChoiceItem
              value="bank_transfer"
              label="Vorkasse per Überweisung"
              description="Wartet zehn Tage auf das Geld; im Stellwerk als eingegangen buchen."
            />
          ) : null}
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
  byTransfer = false,
  children,
}: {
  order: OrderOut;
  statusHref: Route;
  badge?: ReactNode;
  onSubmit?: () => void;
  /** Paid in advance: the details are in the e-mail, there is nothing to come back for. */
  byTransfer?: boolean;
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
        {byTransfer ? (
          "Bankverbindung und GiroCode stehen auch in der E-Mail zu deiner Bestellung. "
        ) : (
          <>
            Du kannst auch später bezahlen
            {order.payment_due_at
              ? `, bis ${formatLongDate(new Date(order.payment_due_at))}, ${formatClock(new Date(order.payment_due_at))} Uhr`
              : ""}
            : Die E-Mail zu deiner Bestellung enthält den Link hierher.{" "}
          </>
        )}
        Zur{" "}
        <Link href={statusHref} className="underline underline-offset-4 hover:text-ink">
          Übersicht der Bestellung
        </Link>
        .
      </p>
    </div>
  );
}
