"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { VariantPicker, type ChosenVariant } from "@/components/admin/inventory/units-dialog";
import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { assignTillItem, getGetTillQueryKey, settleTillLine, useGetTill } from "@/lib/api/generated/admin-inventory/admin-inventory";
import { getGetSalesReportQueryKey } from "@/lib/api/generated/admin-sales/admin-sales";
import type { TillItemIn, TillItemOut, TillLineOut, TillOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { errorMessage } from "@/lib/i18n/problems";
import { longDayLabel, piecesLabel, shopDay, timeLabel } from "@/lib/sales/report";
import { cn } from "@/lib/utils";

/** The worker fetches every minute; the panel follows a little behind. */
const REFRESH_MS = 30_000;

/** What a till line still needs, in the words of the people at the stand. */
function waitingFor(line: TillLineOut): string {
  switch (line.state) {
    case "unassigned":
      return "Noch keinem Modell zugeordnet";
    case "custom":
      return "Preis ohne Artikel: bitte von Hand ausbuchen";
    case "short":
      return `${line.booked} von ${line.quantity} ausgebucht, es fehlt ${line.quantity - line.booked === 1 ? "ein Stück" : `${line.quantity - line.booked} Stück`} im Lager`;
    default:
      return "";
  }
}

/**
 * Die Kasse (ADR 0041): what the SumUp app sold books pieces out by itself. What it cannot
 * book (a name not yet assigned, a price typed in without an article, a piece not on a
 * shelf) waits here until somebody assigns the name or marks it done.
 */
export function TillPanel() {
  const till = useGetTill({ query: { refetchInterval: REFRESH_MS } });
  const [assigning, setAssigning] = useState<string | null>(null);
  const [showItems, setShowItems] = useState(false);

  if (!till.data) {
    return till.isError ? <p className="text-small text-danger">{errorMessage(till.error)}</p> : null;
  }
  const data = till.data;
  if (!data.enabled && data.open.length === 0 && data.items.length === 0) {
    return null;
  }

  return (
    <Panel title="Kasse" actions={<TillStatus till={data} />}>
      <p className="text-small text-ink-secondary">
        {data.booked_today > 0
          ? `Heute hat die Kasse ${piecesLabel(data.booked_today)} selbst ausgebucht.`
          : "Was an der SumUp-Kasse verkauft wird, bucht sich etwa eine Minute später selbst aus."}
      </p>

      {data.open.length > 0 ? (
        <div className="mt-4 -mx-5 border-y border-line">
          <p className="bg-sunken px-5 py-2 text-small font-medium">
            {data.open.length === 1 ? "1 Kassenverkauf braucht einen Blick" : `${data.open.length} Kassenverkäufe brauchen einen Blick`}
          </p>
          <ul className="divide-y divide-line">
            {data.open.map((line) => (
              <TillLineRow key={line.id} line={line} onAssign={() => setAssigning(line.name)} />
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-3 text-small font-medium text-ink">Alles zugeordnet.</p>
      )}

      {data.items.length > 0 ? (
        <div className="mt-4">
          <button
            type="button"
            aria-expanded={showItems}
            onClick={() => setShowItems((shown) => !shown)}
            className="inline-flex h-9 items-center text-hint font-medium text-ink-tertiary underline-offset-2 hover:underline"
          >
            {showItems ? "Zugeordnete Kassenartikel ausblenden" : `Zugeordnete Kassenartikel (${data.items.length})`}
          </button>
          {showItems ? <TillItems items={data.items} onChange={setAssigning} /> : null}
        </div>
      ) : null}

      <AssignDialog name={assigning} current={data.items.find((item) => item.name === assigning) ?? null} onClose={() => setAssigning(null)} />
    </Panel>
  );
}

function TillStatus({ till }: { till: TillOut }) {
  if (!till.enabled) {
    return <span className="text-hint text-ink-tertiary">Nicht verbunden</span>;
  }
  if (till.last_error) {
    return (
      <span className="inline-flex items-center gap-2 text-hint font-medium text-danger" title={till.last_error}>
        <span aria-hidden="true" className="size-2 rounded-full bg-danger" />
        SumUp nicht erreichbar
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2 text-hint text-ink-tertiary">
      <span aria-hidden="true" className="size-2 animate-lamp-pulse rounded-full bg-action" />
      {till.last_sync_at ? `Verbunden · abgeholt ${timeLabel(till.last_sync_at)}` : "Verbunden"}
    </span>
  );
}

function TillLineRow({ line, onAssign }: { line: TillLineOut; onAssign: () => void }) {
  const queryClient = useQueryClient();
  const settle = useMutation<TillOut, ApiProblem, void>({
    mutationFn: () => settleTillLine(line.id),
    onSuccess(result) {
      queryClient.setQueryData(getGetTillQueryKey(), result);
    },
  });
  const day = shopDay(line.sold_at);
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 px-5 py-3.5">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-hint text-ink-tertiary">
          <span className="tabular-nums">
            {day === shopDay(new Date()) ? "Heute" : longDayLabel(day)}, {timeLabel(line.sold_at)}
          </span>
          <span>{line.payment === "cash" ? "Bar" : "Karte"}</span>
          <span className="font-mono">{line.transaction_code}</span>
        </p>
        <p className="mt-1 text-small font-medium text-ink">
          {line.quantity > 1 ? `${line.quantity} × ` : null}
          {line.name}
        </p>
        <p className={cn("mt-0.5 text-hint", line.state === "short" ? "text-warning" : "text-ink-secondary")}>
          {waitingFor(line)}
          {line.variant ? <span className="text-ink-tertiary"> · {line.variant.title}</span> : null}
        </p>
      </div>
      <p className="text-right text-small font-medium text-ink tabular-nums">{formatPrice(line.unit_price_cents * line.quantity)}</p>
      <div className="col-span-2 flex flex-wrap gap-x-5">
        {line.state === "unassigned" ? (
          <button
            type="button"
            onClick={onAssign}
            className="inline-flex h-9 items-center text-hint font-medium text-accent underline-offset-2 hover:underline"
          >
            Modell zuordnen
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => settle.mutate()}
          disabled={settle.isPending}
          className="inline-flex h-9 items-center text-hint font-medium text-ink-tertiary underline-offset-2 hover:underline"
        >
          {line.state === "unassigned" ? "Kein Ausbuchen nötig" : "Erledigt, von Hand ausgebucht"}
        </button>
        {settle.error ? <span className="self-center text-hint text-danger">{errorMessage(settle.error)}</span> : null}
      </div>
    </li>
  );
}

function TillItems({ items, onChange }: { items: readonly TillItemOut[]; onChange: (name: string) => void }) {
  return (
    <ul className="mt-2 divide-y divide-line rounded-sm border border-line">
      {items.map((item) => (
        <li key={item.name} className="flex items-baseline justify-between gap-4 px-4 py-2.5">
          <div className="min-w-0">
            <p className="truncate text-small font-medium">{item.name}</p>
            <p className="truncate text-hint text-ink-tertiary">
              {item.ignored ? "Kein Modell, wird nicht ausgebucht" : (item.variant?.title ?? "Noch offen")}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onChange(item.name)}
            className="shrink-0 text-hint font-medium text-accent underline-offset-2 hover:underline"
          >
            Ändern
          </button>
        </li>
      ))}
    </ul>
  );
}

function AssignDialog({ name, current, onClose }: { name: string | null; current: TillItemOut | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const assign = useMutation<TillOut, ApiProblem, TillItemIn>({
    mutationFn: (body) => assignTillItem(body),
    onSuccess(result) {
      queryClient.setQueryData(getGetTillQueryKey(), result);
      // Waiting sales were booked out: the figures above change too.
      void queryClient.invalidateQueries({
        queryKey: getGetSalesReportQueryKey().slice(0, 1),
      });
      onClose();
    },
  });
  const choose = (variant: ChosenVariant) => {
    if (name !== null) {
      assign.mutate({ name, variant_id: variant.variantId, ignored: false });
    }
  };
  return (
    <Dialog
      open={name !== null}
      onOpenChange={(open) => {
        if (!open) {
          assign.reset();
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogTitle>„{name}“ zuordnen</DialogTitle>
        <DialogDescription>
          Welches Modell verkauft dieser Kassenartikel? Einmal zugeordnet, bucht jeder Verkauf unter diesem Namen das älteste freie Stück selbst aus,
          auch die Verkäufe, die schon warten.
        </DialogDescription>
        {current?.variant ? (
          <p className="mt-4 text-small text-ink-secondary">
            Bisher: <span className="font-medium text-ink">{current.variant.title}</span>
          </p>
        ) : null}
        <div className="mt-6">
          <VariantPicker onChoose={choose} />
        </div>
        {assign.error ? (
          <p role="alert" className="mt-4 text-small text-danger">
            {errorMessage(assign.error)}
          </p>
        ) : null}
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={assign.isPending || name === null}
            onClick={() => name !== null && assign.mutate({ name, variant_id: null, ignored: true })}
          >
            Kein Modell (z. B. Porto)
          </Button>
          <DialogClose asChild>
            <Button type="button" variant="secondary" size="sm">
              Abbrechen
            </Button>
          </DialogClose>
        </div>
        {assign.isPending ? <p className="mt-3 text-hint text-ink-tertiary">Wird gespeichert und ausgebucht …</p> : null}
      </DialogContent>
    </Dialog>
  );
}
