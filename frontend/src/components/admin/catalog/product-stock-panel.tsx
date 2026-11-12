"use client";

import Link from "next/link";

import { UnitsDialog } from "@/components/admin/inventory/units-dialog";
import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { ColorDot } from "@/components/ui/color-dot";
import { PendingNotice } from "@/components/ui/pending-notice";
import { useListStock } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { ProductOut, ReferencesOut, StockLineOut } from "@/lib/api/generated/model";
import { finishLabel } from "@/lib/catalog/format";
import { unitListHref } from "@/lib/inventory/selection";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";

type Figure = { label: string; value: (line: StockLineOut | undefined) => number; tone: string };

/** What the store holds of one Ausführung, as on the Lager page. */
const FIGURES: readonly Figure[] = [
  { label: "Frei", value: (line) => line?.in_stock ?? 0, tone: "text-success" },
  { label: "Reserviert", value: (line) => (line ? line.allocated + line.picked : 0), tone: "text-accent" },
  { label: "Unverbucht", value: (line) => line?.labeled ?? 0, tone: "text-warning" },
];

/**
 * The stock of a Modell per Ausführung, live from the store: free, reserved and unbooked
 * pieces, the way to the pieces themselves and to recording new ones.
 */
export function ProductStockPanel({ product, references }: { product: ProductOut; references: ReferencesOut }) {
  const stock = useListStock();
  const lines = new Map((stock.data?.items ?? []).map((line) => [line.variant_id, line]));
  const variants = product.scales.flatMap((scale) => scale.variants.map((variant) => ({ scale: scale.scale_code, variant })));
  const finishName = (code: string) => references.finishes.find((finish) => finish.code === code)?.name ?? code;

  return (
    <Panel title="Bestand" code="PRD 05">
      {stock.isPending ? <PendingNotice>Der Bestand wird geladen …</PendingNotice> : null}
      {stock.isError ? <p className="text-small text-danger">{errorMessage(stock.error)}</p> : null}
      {stock.isSuccess && variants.length === 0 ? (
        <p className="text-small text-ink-secondary">Noch keine Ausführung, also auch keine Stücke.</p>
      ) : null}
      {stock.isSuccess && variants.length > 0 ? (
        <ul className="divide-y divide-line border-y border-line">
          {variants.map(({ scale, variant }) => {
            const line = lines.get(variant.id);
            const name = `${scale} · ${finishLabel(finishName(variant.finish_code), variant.color)}`;
            const waiting = line?.backordered ?? 0;
            return (
              <li key={variant.id} className="py-3">
                <p className="flex items-center gap-2 text-small font-medium">
                  {variant.color !== "" ? <ColorDot color={variant.color} size="sm" /> : null}
                  <span className="min-w-0 truncate">{name}</span>
                </p>
                <p className="font-mono text-hint text-ink-tertiary">{variant.sku}</p>
                <dl className="mt-2 grid grid-cols-3 gap-px overflow-hidden rounded-sm border border-line bg-line">
                  {FIGURES.map((figure) => {
                    const value = figure.value(line);
                    return (
                      <div key={figure.label} className="bg-surface px-2 py-1.5">
                        <dt className="text-hint text-ink-tertiary">{figure.label}</dt>
                        <dd className={cn("text-body-lg font-medium tabular-nums", value > 0 ? figure.tone : "text-ink-disabled")}>{value}</dd>
                      </div>
                    );
                  })}
                </dl>
                {waiting > 0 ? (
                  <p className="mt-1.5 text-hint text-warning">{waiting === 1 ? "1 bestelltes Stück wartet" : `${waiting} bestellte Stücke warten`} auf die Fertigung.</p>
                ) : null}
                <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
                  <Link href={unitListHref({ variantId: variant.id })} className="text-small text-accent hover:underline">
                    Stücke<span className="sr-only"> von {name}</span>
                  </Link>
                  <UnitsDialog
                    variant={{ variantId: variant.id, title: `${product.name} · ${name}`, sku: variant.sku }}
                    trigger={
                      <Button type="button" size="sm" variant="ghost" className="-ml-2">
                        Stücke erfassen<span className="sr-only">: {name}</span>
                      </Button>
                    }
                  />
                </p>
              </li>
            );
          })}
        </ul>
      ) : null}
    </Panel>
  );
}
