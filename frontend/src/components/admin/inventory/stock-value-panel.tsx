"use client";

import type { Route } from "next";
import Link from "next/link";

import { Panel } from "@/components/admin/panel";
import { PendingNotice } from "@/components/ui/pending-notice";
import { useGetStockValue } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { StockValueOut, ValueShareOut } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import { errorMessage } from "@/lib/i18n/problems";
import { partsWord, percentOf, piecesWord, topModels, type ValueRow } from "@/lib/inventory/value";

/**
 * Lagerwert: what the finished models on the shelves are worth at today's shop price,
 * free and reserved, by Ausführung, scale and model; the printed parts by number.
 * For owner and staff only (the server refuses packers). Live with the rest of the store:
 * every stock event refreshes all inventory queries.
 */
export function StockValuePanel() {
  const value = useGetStockValue();
  return (
    <Panel title="Lagerwert" code="LG 01">
      {value.isPending ? <PendingNotice>Der Lagerwert wird berechnet …</PendingNotice> : null}
      {value.isError ? <p className="text-small text-danger">{errorMessage(value.error)}</p> : null}
      {value.isSuccess ? <StockValueBody value={value.data} /> : null}
    </Panel>
  );
}

export function StockValueBody({ value }: { value: StockValueOut }) {
  const { rows, rest } = topModels(value.by_model);
  return (
    <div>
      <div className="grid gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div>
          <p className="text-label text-ink-secondary uppercase">Warenwert im Lager</p>
          <p className="mt-2 font-display text-title text-ink tabular-nums sm:text-display">
            {formatPrice(value.value_cents)}
          </p>
          <p className="mt-1 text-small text-ink-secondary">
            {piecesWord(value.pieces)} fertige Modelle · zum heutigen Shoppreis, brutto
          </p>
          {value.pieces > 0 ? <SplitBar value={value} /> : <EmptyNote />}
        </div>
        {value.pieces > 0 ? (
          <div className="grid gap-8 sm:grid-cols-2">
            <ShareList title="Nach Ausführung" shares={value.by_finish} total={value.value_cents} />
            <ShareList title="Nach Maßstab" shares={value.by_scale} total={value.value_cents} />
            <div className="sm:col-span-2">
              <ShareList title="Wertvollste Modelle" shares={rows} rest={rest} total={value.value_cents} />
            </div>
          </div>
        ) : null}
      </div>
      <Footer value={value} />
    </div>
  );
}

/** Free and reserved as one bar: the share the shop can still sell stands out. */
function SplitBar({ value }: { value: StockValueOut }) {
  const free = percentOf(value.free_cents, value.value_cents);
  const parts = [
    { key: "free", label: "Frei verkäuflich", pieces: value.free_pieces, cents: value.free_cents, width: free, swatch: "bg-action" },
    {
      key: "reserved",
      label: "Für Bestellungen reserviert",
      pieces: value.reserved_pieces,
      cents: value.reserved_cents,
      width: 100 - free,
      swatch: "bg-ink-secondary",
    },
  ];
  return (
    <div className="mt-6">
      <div
        role="img"
        aria-label={`${formatPrice(value.free_cents)} frei verkäuflich, ${formatPrice(value.reserved_cents)} reserviert`}
        className="flex h-4 gap-0.5 border border-ink shadow-[3px_3px_0_var(--ink)]"
      >
        {parts
          .filter((part) => part.cents > 0)
          .map((part) => (
            <div
              key={part.key}
              title={`${part.label}: ${formatPrice(part.cents)} · ${piecesWord(part.pieces)}`}
              className={`${part.swatch} h-full transition-[width] duration-500 ease-out`}
              style={{ width: `${part.width}%` }}
            />
          ))}
      </div>
      <dl className="mt-5 space-y-2">
        {parts.map((part) => (
          <div key={part.key} className="flex items-baseline justify-between gap-3 text-small">
            <dt className="flex min-w-0 items-baseline gap-2 text-ink-secondary">
              <span aria-hidden="true" className={`${part.swatch} inline-block size-2.5 shrink-0 translate-y-px`} />
              <span>{part.label}</span>
              <span className="shrink-0 text-hint text-ink-tertiary tabular-nums">{piecesWord(part.pieces)}</span>
            </dt>
            <dd className="shrink-0 font-medium text-ink tabular-nums">{formatPrice(part.cents)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ShareList({
  title,
  shares,
  rest = null,
  total,
}: {
  title: string;
  shares: readonly (ValueShareOut | ValueRow)[];
  rest?: ValueShareOut | null;
  total: number;
}) {
  return (
    <section aria-label={title}>
      <h3 className="border-b border-ink pb-1.5 text-label text-ink-secondary uppercase">{title}</h3>
      <ul className="mt-3 space-y-3">
        {shares.map((share) => (
          <ShareRow key={share.key} share={share} total={total} />
        ))}
        {rest ? <ShareRow share={rest} total={total} muted /> : null}
      </ul>
    </section>
  );
}

function ShareRow({ share, total, muted = false }: { share: ValueShareOut | ValueRow; total: number; muted?: boolean }) {
  const href = "href" in share ? share.href : null;
  const percent = percentOf(share.value_cents, total);
  return (
    <li title={`${share.name}: ${formatPrice(share.value_cents)} · ${piecesWord(share.pieces)} · ${Math.round(percent)} %`}>
      <div className="flex items-baseline justify-between gap-3 text-small">
        <span className={`min-w-0 truncate ${muted ? "text-ink-secondary" : "text-ink"}`}>
          {href ? (
            <Link href={href as Route} className="hover:text-accent hover:underline">
              {share.name}
            </Link>
          ) : (
            share.name
          )}
          <span className="ml-2 text-hint text-ink-tertiary tabular-nums">{piecesWord(share.pieces)}</span>
        </span>
        <span className="shrink-0 font-medium tabular-nums">{formatPrice(share.value_cents)}</span>
      </div>
      <div className="mt-1.5 h-1.5 bg-sunken" aria-hidden="true">
        <div
          className={`h-full transition-[width] duration-500 ease-out ${muted ? "bg-line-control" : "bg-action"}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </li>
  );
}

function EmptyNote() {
  return <p className="mt-6 text-small text-ink-secondary">Noch keine fertigen Modelle auf den Regalen.</p>;
}

function Footer({ value }: { value: StockValueOut }) {
  return (
    <div className="mt-8 flex flex-col gap-2 border-t border-line pt-4 text-hint text-ink-secondary sm:flex-row sm:flex-wrap sm:items-baseline sm:justify-between">
      <p>
        {value.part_pieces > 0 ? (
          <>
            Dazu <span className="font-medium text-ink tabular-nums">{partsWord(value.part_pieces)}</span> in Boxen (
            {value.part_kinds === 1 ? "1 Teilenummer" : `${value.part_kinds} Teilenummern`}), ohne eigenen Preis.
          </>
        ) : (
          "Keine gedruckten Teile in Boxen."
        )}
      </p>
      <p>Nicht gezählt: unverbuchte und gerade verpackte Stücke.</p>
      {value.unpriced_pieces > 0 ? (
        <p className="w-full text-warning">
          {piecesWord(value.unpriced_pieces)} gelöschter Modelle liegen noch im Lager und sind nicht im Wert enthalten.
        </p>
      ) : null}
    </div>
  );
}
