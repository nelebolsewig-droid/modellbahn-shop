"use client";

import type { Route } from "next";
import Link from "next/link";

import { OrderDetails } from "@/components/shop/order-status";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { useGetMyOrder } from "@/lib/api/generated/store-account/store-account";
import { isApiProblem } from "@/lib/api/problem";
import { errorMessage } from "@/lib/i18n/problems";

import { CustomerGate } from "./customer-gate";

/** One order of the account's history, with the same view as the status page. */
export function MyOrder({ number }: { number: string }) {
  return (
    <CustomerGate pending="Die Bestellung wird geladen …">{() => <MyOrderDetails number={number} />}</CustomerGate>
  );
}

function MyOrderDetails({ number }: { number: string }) {
  const order = useGetMyOrder(number);

  return (
    <div>
      <Link
        href="/konto/bestellungen"
        className="inline-flex items-center gap-2 text-small font-medium text-ink-secondary hover:text-ink"
      >
        <span aria-hidden="true">←</span> Alle Bestellungen
      </Link>
      <div className="mt-8">
        {order.isPending ? (
          <PendingNotice>Die Bestellung wird geladen …</PendingNotice>
        ) : order.isError ? (
          <div className="max-w-xl space-y-6">
            <Alert
              tone="danger"
              title={
                isApiProblem(order.error) && order.error.status === 404
                  ? `Die Bestellung ${number} gibt es in deinem Konto nicht`
                  : "Die Bestellung konnte nicht geladen werden"
              }
            >
              <p>{errorMessage(order.error)}</p>
            </Alert>
            <Button asChild variant="secondary">
              <Link href="/konto/bestellungen">Zu den Bestellungen</Link>
            </Button>
          </div>
        ) : (
          <OrderDetails order={order.data} payHref={`/bestellung/${order.data.public_token}/bezahlen` as Route} />
        )}
      </div>
    </div>
  );
}
