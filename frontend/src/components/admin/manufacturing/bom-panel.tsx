"use client";

import { useMutation } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useDeferredValue, useState } from "react";

import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { QuantityStepper } from "@/components/ui/quantity-stepper";
import { replaceBillOfMaterials } from "@/lib/api/generated/admin-manufacturing/admin-manufacturing";
import type { BomLineOut, BomOut, PartRefOut, ProductOut, ProductScaleOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { errorMessage } from "@/lib/i18n/problems";
import { formatMinutes } from "@/lib/manufacturing/hall";

import { useBom, useManufacturingRefresh, useParts } from "./use-manufacturing";

const PARTS_PAGE = "/admin/fertigung/teile" as Route;

/**
 * "Stückliste" in the product editor: which parts make the product in each scale. Every
 * variant of a scale shares it, kit or finished model, because painting comes after
 * printing. The product editor is for owner and staff, who keep the bills of materials too.
 */
export function ProductBomPanel({ product }: { product: ProductOut }) {
  return (
    <Panel title="Stückliste" code="PRD 03">
      {product.scales.length === 0 ? (
        <p className="text-small text-ink-secondary">Leg zuerst einen Maßstab an; die Stückliste gilt je Maßstab.</p>
      ) : (
        <div className="space-y-6">
          {product.scales.map((scale) => (
            <ScaleBom key={scale.id} scale={scale} />
          ))}
        </div>
      )}
    </Panel>
  );
}

function ScaleBom({ scale }: { scale: ProductScaleOut }) {
  const bom = useBom(scale.id);
  const [editing, setEditing] = useState(false);

  return (
    <section aria-label={`Stückliste ${scale.scale_code}`}>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="label-caps text-ink-tertiary">{bom.data?.product_scale.scale_name ?? scale.scale_code}</h3>
        {!editing && bom.isSuccess ? (
          <Button type="button" variant="ghost" size="sm" className="-mr-3" onClick={() => setEditing(true)}>
            {bom.data.lines.length === 0 ? "Anlegen" : "Bearbeiten"}
          </Button>
        ) : null}
      </div>
      {bom.isPending ? (
        <PendingNotice className="mt-2">Wird geladen …</PendingNotice>
      ) : bom.isError ? (
        <p role="alert" className="mt-2 text-small text-danger">
          {errorMessage(bom.error)}
        </p>
      ) : editing ? (
        <BomEditor bom={bom.data} onDone={() => setEditing(false)} />
      ) : bom.data.lines.length === 0 ? (
        <p className="mt-2 text-small text-ink-secondary">Noch keine Teile eingetragen.</p>
      ) : (
        <BomSheet bom={bom.data} />
      )}
    </section>
  );
}

/** The bill of materials as a drawing's parts list: position, quantity, part. */
function BomSheet({ bom }: { bom: BomOut }) {
  return (
    <>
      <ol className="mt-2 divide-y divide-line border-y border-line">
        {bom.lines.map((line, index) => (
          <li
            key={line.part.id}
            className="grid grid-cols-[1.75rem_2.5rem_minmax(0,1fr)] items-baseline gap-x-2 py-2 text-small"
          >
            <span className="font-mono text-hint text-ink-tertiary">{String(index + 1).padStart(2, "0")}</span>
            <span className="text-right tabular-nums">{line.quantity} ×</span>
            <span className="min-w-0">
              <span className={line.active ? "block truncate" : "block truncate text-ink-tertiary line-through"}>
                {line.part.name}
              </span>
              <span className="block truncate font-mono text-hint text-ink-tertiary">{line.part.part_number}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="mt-2 flex flex-wrap justify-between gap-x-4 text-hint text-ink-secondary">
        <span>{bom.part_count === 1 ? "1 Teil" : `${bom.part_count} Teile`} je Bausatz</span>
        <span>
          {bom.print_minutes !== null
            ? `etwa ${formatMinutes(bom.print_minutes)} Druckzeit`
            : "Druckzeit offen: nicht jedes Teil hat Druckdaten"}
        </span>
      </p>
    </>
  );
}

type DraftLine = { part: PartRefOut; quantity: number };

function draftOf(lines: readonly BomLineOut[]): DraftLine[] {
  return lines.map((line) => ({ part: line.part, quantity: line.quantity }));
}

function BomEditor({ bom, onDone }: { bom: BomOut; onDone: () => void }) {
  const [lines, setLines] = useState<DraftLine[]>(() => draftOf(bom.lines));
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search.trim());
  const refresh = useManufacturingRefresh();
  const candidates = useParts({ scale: bom.product_scale.scale_code, ...(query ? { q: query } : {}) });
  const save = useMutation<BomOut, ApiProblem>({
    mutationFn: () =>
      replaceBillOfMaterials(bom.product_scale.product_scale_id, {
        lines: lines.map((line) => ({ part_id: line.part.id, quantity: line.quantity })),
      }),
    onSuccess() {
      refresh();
      onDone();
    },
  });
  const offered = (candidates.data ?? []).filter((part) => !lines.some((line) => line.part.id === part.id)).slice(0, 6);
  const move = (index: number, delta: number) =>
    setLines((current) => {
      const next = [...current];
      const [line] = next.splice(index, 1);
      if (line) next.splice(index + delta, 0, line);
      return next;
    });

  return (
    <div className="mt-2">
      {lines.length === 0 ? (
        <p className="text-small text-ink-secondary">Keine Teile. Gespeichert ohne Teile, entfällt die Stückliste.</p>
      ) : (
        <ol className="divide-y divide-line border-y border-line">
          {lines.map((line, index) => (
            <li key={line.part.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2">
              <span className="min-w-0 flex-1 text-small">
                <span className="block truncate">{line.part.name}</span>
                <span className="block truncate font-mono text-hint text-ink-tertiary">{line.part.part_number}</span>
              </span>
              <QuantityStepper
                value={line.quantity}
                max={999}
                label={`Menge ${line.part.name}`}
                onChange={(quantity) =>
                  setLines((current) => current.map((entry, at) => (at === index ? { ...entry, quantity } : entry)))
                }
              />
              <span className="flex">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="px-2"
                  aria-label={`${line.part.name} nach oben`}
                  disabled={index === 0}
                  onClick={() => move(index, -1)}
                >
                  ↑
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="px-2"
                  aria-label={`${line.part.name} entfernen`}
                  onClick={() => setLines((current) => current.filter((_, at) => at !== index))}
                >
                  ✕
                </Button>
              </span>
            </li>
          ))}
        </ol>
      )}
      <div className="mt-3">
        <Input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={`Teil für ${bom.product_scale.scale_name} suchen`}
          aria-label="Teil suchen"
        />
        {offered.length > 0 ? (
          <ul className="mt-2 flex flex-wrap gap-2" aria-label="Passende Teile">
            {offered.map((part) => (
              <li key={part.id}>
                <button
                  type="button"
                  onClick={() => setLines((current) => [...current, { part, quantity: 1 }])}
                  className="inline-flex max-w-full items-center gap-2 rounded-full border border-line-strong bg-surface px-3 py-1.5 text-small transition-colors hover:border-ink"
                >
                  <span aria-hidden="true" className="text-accent">
                    +
                  </span>
                  <span className="truncate">{part.name}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : candidates.isSuccess ? (
          <p className="mt-2 text-hint text-ink-tertiary">
            Kein weiteres Teil in {bom.product_scale.scale_name}.{" "}
            <Link href={PARTS_PAGE} className="text-accent hover:underline">
              Teile anlegen
            </Link>
          </p>
        ) : null}
      </div>
      <p role="alert" className="text-small text-danger not-empty:mt-3">
        {save.isError ? errorMessage(save.error) : null}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          disabled={save.isPending}
          aria-busy={save.isPending || undefined}
          onClick={() => save.mutate()}
        >
          {save.isPending ? "Speichert …" : "Stückliste speichern"}
        </Button>
        <Button type="button" size="sm" variant="secondary" onClick={onDone}>
          Abbrechen
        </Button>
      </div>
    </div>
  );
}
