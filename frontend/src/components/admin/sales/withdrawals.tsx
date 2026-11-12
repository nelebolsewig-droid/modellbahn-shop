"use client";

import type { Route } from "next";
import Link from "next/link";

import { Panel } from "@/components/admin/panel";
import { Callout } from "@/components/ui/alert";
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge";
import { useListWithdrawals } from "@/lib/api/generated/admin-sales/admin-sales";
import type { WithdrawalOut, WithdrawalState } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import { formatClock, formatLongDate } from "@/lib/format";

const RECENT = 10;

const STATE_TONES: Record<WithdrawalState, StatusTone> = {
  unmatched: "warning",
  cancelled: "neutral",
  awaiting_return: "accent",
  refunded: "success",
  to_check: "warning",
};

function received(withdrawal: WithdrawalOut): string {
  const at = new Date(withdrawal.received_at);
  return `${formatLongDate(at)}, ${formatClock(at)} Uhr`;
}

function due(withdrawal: WithdrawalOut): string {
  return formatLongDate(new Date(withdrawal.refund_due_at));
}

/** Where a withdrawal stands, in a few words. */
export function withdrawalStateLabel(withdrawal: WithdrawalOut): string {
  switch (withdrawal.state) {
    case "unmatched":
      return "Keine passende Bestellung";
    case "cancelled":
      return "Storniert";
    case "awaiting_return":
      return `Wartet auf Rücksendung · erstatten bis ${due(withdrawal)}`;
    case "refunded":
      return `Erstattet: ${formatPrice(withdrawal.refunded_cents)}`;
    case "to_check":
      return `Bitte prüfen · erstatten bis ${due(withdrawal)}`;
  }
}

/** What staff do next; null when nothing is left to do. */
function nextStep(withdrawal: WithdrawalOut): string | null {
  switch (withdrawal.state) {
    case "unmatched":
      return "Zu Nummer und E-Mail-Adresse passt keine Bestellung. Bitte von Hand prüfen, etwa ob es ein eBay-Kauf ist.";
    case "cancelled":
      return null;
    case "awaiting_return":
      return "Ist die Ware zurück, unten unter „Erstattung“ auf „Rücksendung erhalten – erstatten“. Die Mail an den Kunden geht von selbst.";
    case "refunded":
      return null;
    case "to_check":
      return "Nur einzelne Modelle oder eine eBay-Bestellung: Was zurückgeht, entscheidest du unter „Erstattung“ (eBay: auf eBay).";
  }
}

/**
 * Declarations from the withdrawal function (§ 356a BGB), newest first, with where they stand.
 * Shown only when there are any. Before dispatch the shop cancels and refunds by itself; after
 * dispatch one click refunds once the return is there (ADR 0020).
 */
export function WithdrawalsPanel() {
  const withdrawals = useListWithdrawals({ limit: RECENT });
  const items = withdrawals.data?.items ?? [];
  if (items.length === 0) {
    return null;
  }
  return (
    <Panel title="Widerrufe" code="VK 17" className="mb-8">
      <ul className="divide-y divide-line">
        {items.map((withdrawal) => (
          <li key={withdrawal.id} className="grid gap-1 py-3 text-small sm:grid-cols-[12rem_minmax(0,1fr)] sm:gap-6">
            <span className="text-ink-tertiary">{received(withdrawal)}</span>
            <span>
              {withdrawal.order_id ? (
                <Link
                  href={`/admin/bestellungen/${withdrawal.order_id}` as Route}
                  className="font-mono font-medium underline underline-offset-4 hover:text-accent"
                >
                  {withdrawal.order_number}
                </Link>
              ) : (
                <span className="font-mono">{withdrawal.order_number}</span>
              )}{" "}
              · {withdrawal.name} · <span className="break-all">{withdrawal.email}</span>
              <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                <StatusBadge tone={STATE_TONES[withdrawal.state]}>{withdrawalStateLabel(withdrawal)}</StatusBadge>
                <span className="text-ink-secondary">
                  {withdrawal.scope ? `Nur: ${withdrawal.scope}` : "Die ganze Bestellung"}
                </span>
              </span>
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** On an order's desk: the customer withdrew, and what is left to do. */
export function OrderWithdrawals({ orderId }: { orderId: string }) {
  const withdrawals = useListWithdrawals({ order_id: orderId, limit: RECENT });
  const items = withdrawals.data?.items ?? [];
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="space-y-3">
      {items.map((withdrawal) => {
        const step = nextStep(withdrawal);
        return (
          <Callout
            key={withdrawal.id}
            tone={step === null ? "info" : "danger"}
            title={`Widerruf eingegangen am ${received(withdrawal)}`}
          >
            <p>
              {withdrawal.scope ? `Nur: ${withdrawal.scope}` : "Die ganze Bestellung"}, erklärt von {withdrawal.name} (
              <span className="break-all">{withdrawal.email}</span>). Die Eingangsbestätigung ist verschickt.
            </p>
            <p className="font-medium">{withdrawalStateLabel(withdrawal)}</p>
            {step ? <p>{step}</p> : null}
          </Callout>
        );
      })}
    </div>
  );
}
