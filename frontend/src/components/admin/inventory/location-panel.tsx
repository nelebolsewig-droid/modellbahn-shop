"use client";

import type { Route } from "next";
import Link from "next/link";

import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { PendingNotice } from "@/components/ui/pending-notice";
import { useListLocations } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { LocationNodeOut } from "@/lib/api/generated/model";
import { LOCATION_KIND_LABELS } from "@/lib/inventory/labels";
import { labelCodes } from "@/lib/inventory/locations";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";

import { LabelPrinter } from "./label-printer";
import { LocationCreateDialog } from "./location-dialogs";
import { LocationGlyph } from "./location-glyph";

/** The store as a tree: sites, shelves, compartments and boxes, with what lies in them. */
export function LocationPanel({ mayManage }: { mayManage: boolean }) {
  const tree = useListLocations();
  const items = tree.data?.items ?? [];
  return (
    <Panel
      title="Lagerplätze"
      code="LG 02"
      actions={
        <div className="flex gap-2">
          {items.length > 0 ? <LocationLabelsDialog items={items} /> : null}
          {mayManage ? (
            <LocationCreateDialog
              parent={null}
              trigger={
                <Button type="button" size="sm" variant="secondary">
                  Lager anlegen
                </Button>
              }
            />
          ) : null}
        </div>
      }
    >
      {tree.isPending ? <PendingNotice>Die Lagerplätze werden geladen …</PendingNotice> : null}
      {tree.isError ? <p className="text-small text-danger">{errorMessage(tree.error)}</p> : null}
      {tree.isSuccess && items.length === 0 ? <EmptyStore mayManage={mayManage} /> : null}
      {items.length > 0 ? <LocationTree items={items} /> : null}
    </Panel>
  );
}

function EmptyStore({ mayManage }: { mayManage: boolean }) {
  return (
    <div className="py-6 text-center">
      <LocationGlyph kind="shelf" className="mx-auto size-10 text-ink-disabled" />
      <p className="mt-4 text-small text-ink-secondary">
        Noch keine Lagerplätze.{" "}
        {mayManage ? "Erst ein Lager anlegen, dann Regale und Fächer darin." : "Inhaber oder Mitarbeiter legen sie an."}
      </p>
    </div>
  );
}

/** Indented rows with guide lines, like the branches of a track plan. */
export function LocationTree({ items, className }: { items: readonly LocationNodeOut[]; className?: string }) {
  const base = Math.min(...items.map((item) => item.depth));
  return (
    <ul className={cn("-mx-2", className)}>
      {items.map((item) => {
        const level = item.depth - base;
        return (
          <li key={item.id}>
            <Link
              href={`/admin/lager/plaetze/${item.code}` as Route}
              className="group flex items-center gap-2.5 rounded-sm px-2 py-1.5 hover:bg-sunken"
            >
              {Array.from({ length: level }, (_, index) => (
                <span key={index} aria-hidden="true" className="-my-1.5 h-8 w-3 shrink-0 border-l border-line" />
              ))}
              <LocationGlyph kind={item.kind} className={item.holds_goods ? "text-ink" : "text-ink-tertiary"} />
              <span className="min-w-0 flex-1 truncate">
                <span className="font-mono text-small font-medium group-hover:underline">{item.code}</span>
                <span className="ml-2 text-hint text-ink-tertiary">{item.name || LOCATION_KIND_LABELS[item.kind]}</span>
              </span>
              {item.total_count > 0 ? (
                <span className="rounded-full bg-sunken px-2 py-0.5 text-hint font-medium tabular-nums text-ink-secondary">
                  {item.total_count}
                </span>
              ) : null}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function LocationLabelsDialog({ items }: { items: readonly LocationNodeOut[] }) {
  const codes = labelCodes(items);
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" size="sm" variant="ghost">
          Etiketten
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogTitle>Etiketten für alle Plätze</DialogTitle>
        <DialogDescription>
          Ein Etikett je Regal, Fach, Box und Ablage. Einzelne Plätze druckt die Seite des Platzes.
        </DialogDescription>
        <LabelPrinter locationCodes={codes} className="mt-6" />
      </DialogContent>
    </Dialog>
  );
}
