"use client";

import type { Route } from "next";
import Link from "next/link";

import { Panel } from "@/components/admin/panel";
import { Callout } from "@/components/ui/alert";
import { useListWithdrawals } from "@/lib/api/generated/admin-sales/admin-sales";
import type { WithdrawalOut } from "@/lib/api/generated/model";
import { formatClock, formatLongDate } from "@/lib/format";

const RECENT = 10;

function received(withdrawal: WithdrawalOut): string {
  const at = new Date(withdrawal.received_at);
  return `${formatLongDate(at)}, ${formatClock(at)} Uhr`;
}

/**
 * Declarations from the withdrawal function (§ 356a BGB), newest first. Shown only when there
 * are any; one that fits no order is marked, so someone checks it by hand (e.g. an eBay sale).
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
              <span className="block text-ink-secondary">
                {withdrawal.scope ? `Nur: ${withdrawal.scope}` : "Die ganze Bestellung"}
                {withdrawal.order_id ? "" : " · keine passende Bestellung, bitte von Hand prüfen"}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** On an order's desk: the customer withdrew. Refunding is up to staff once the goods are back. */
export function OrderWithdrawals({ orderId }: { orderId: string }) {
  const withdrawals = useListWithdrawals({ order_id: orderId, limit: RECENT });
  const items = withdrawals.data?.items ?? [];
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="space-y-3">
      {items.map((withdrawal) => (
        <Callout key={withdrawal.id} tone="danger" title={`Widerruf eingegangen am ${received(withdrawal)}`}>
          <p>
            {withdrawal.scope ? `Nur: ${withdrawal.scope}` : "Die ganze Bestellung"}, erklärt von {withdrawal.name} (
            <span className="break-all">{withdrawal.email}</span>). Die Eingangsbestätigung ist verschickt.
          </p>
          <p>
            Noch nicht versendet: stornieren, das erstattet den Betrag. Schon versendet: Ware zurücknehmen und den
            Betrag samt Hinsendekosten innerhalb von 14 Tagen erstatten (im SumUp-Konto).
          </p>
        </Callout>
      ))}
    </div>
  );
}
