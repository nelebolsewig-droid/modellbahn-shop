"use client";

import { useMutation } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import {
  createShelf,
  listUnits,
  scrapUnits,
  useListLocations,
  useListPlaceStock,
  useListStock,
} from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { LocationNodeOut, PlaceStockOut, ShelfOut, StaffRole } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { pieces, unitListHref } from "@/lib/inventory/selection";
import { lying } from "@/lib/inventory/stock";
import { errorMessage } from "@/lib/i18n/problems";
import { ADMIN_EVENTS_URL, INVENTORY_EVENT_TYPES, stockEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";

import { LabelPrinter } from "./label-printer";
import { useInventoryRefresh } from "./part-dialogs";
import { PartStockPanel, ReceivingPanel } from "./parts-panels";
import { CountDialog } from "./stock-dialogs";

/** Owner and staff run the store; packers look and scan. */
export const MAY_MANAGE_STOCK: ReadonlySet<StaffRole> = new Set(["owner", "staff"]);

const BOARDS_MAX = 20;
/** As many pieces as one request books out (UNITS_SELECTED_MAX). */
const SCRAP_BATCH = 500;

/** A shelf with its Böden, or a place of its own (a packing table, an old box). */
export type Rack = { shelf: LocationNodeOut | null; places: LocationNodeOut[] };

/**
 * The store as people see it: shelves, and in each its Böden (a shelf without Böden is
 * one place). Places that hold goods outside a shelf follow as "Weitere Plätze".
 */
export function racks(tree: readonly LocationNodeOut[]): Rack[] {
  const byParent = new Map<string | null, LocationNodeOut[]>();
  for (const node of tree) {
    byParent.set(node.parent_id, [...(byParent.get(node.parent_id) ?? []), node]);
  }
  const placesBelow = (node: LocationNodeOut): LocationNodeOut[] =>
    (byParent.get(node.id) ?? []).flatMap((child) => [...(child.holds_goods ? [child] : []), ...placesBelow(child)]);
  const shelves = tree.filter((node) => node.kind === "shelf");
  const onShelves = new Set<string>();
  const result: Rack[] = shelves.map((shelf) => {
    const below = placesBelow(shelf);
    const places = below.length > 0 ? below : shelf.holds_goods ? [shelf] : [];
    places.forEach((place) => onShelves.add(place.id));
    return { shelf, places };
  });
  const loose = tree.filter((node) => node.holds_goods && node.kind !== "shelf" && !onShelves.has(node.id));
  return loose.length > 0 ? [...result, { shelf: null, places: loose }] : result;
}

/** The store at a glance: shelves and Böden with the models on them, live. */
export function InventoryOverview({ staffRole, onStreamClosed }: { staffRole: StaffRole; onStreamClosed: () => void }) {
  const mayManage = MAY_MANAGE_STOCK.has(staffRole);
  const refresh = useInventoryRefresh();
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: INVENTORY_EVENT_TYPES,
    onMessage(data) {
      if (stockEventOf(data) !== null) {
        refresh();
      }
    },
    onClosed: onStreamClosed,
  });

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-heading sm:text-title">Lager</h1>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>
      <div className="mt-6 flex flex-wrap gap-2">
        {mayManage ? <NewShelfDialog /> : null}
        <Button asChild size="sm" variant="secondary">
          <Link href="/admin/scanner">Scannen</Link>
        </Button>
        {mayManage ? (
          <Button asChild size="sm" variant="secondary">
            <Link href="/admin/lager/montage">Montage</Link>
          </Button>
        ) : null}
      </div>
      {mayManage ? <UnbookedHint /> : null}
      <div className="mt-8 space-y-6">
        <ShelfBoard mayManage={mayManage} />
        <ReceivingPanel mayManage={mayManage} />
        <PartStockPanel />
      </div>
    </>
  );
}

function ShelfBoard({ mayManage }: { mayManage: boolean }) {
  const tree = useListLocations();
  const stock = useListPlaceStock();
  const [message, setMessage] = useState("");
  if (tree.isPending || stock.isPending) {
    return <PendingNotice>Das Lager wird geladen …</PendingNotice>;
  }
  if (tree.isError || stock.isError) {
    return <p className="text-small text-danger">{errorMessage(tree.error ?? stock.error)}</p>;
  }
  const byPlace = new Map<string, PlaceStockOut[]>();
  for (const line of stock.data.items) {
    byPlace.set(line.location.code, [...(byPlace.get(line.location.code) ?? []), line]);
  }
  const all = racks(tree.data.items);
  if (all.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-line-strong px-5 py-10 text-center text-small text-ink-secondary">
        Noch kein Regal. {mayManage ? "Mit „Neues Regal“ geht es los." : ""}
      </p>
    );
  }
  return (
    <div className="space-y-6">
      <p role="status" className="text-small font-medium text-success empty:hidden">
        {message}
      </p>
      {all.map((rack) => (
        <section key={rack.shelf?.id ?? "loose"} aria-label={rack.shelf?.place ?? "Weitere Plätze"} className="rounded-md border border-line bg-surface">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
            <h2 className="text-body font-medium tracking-normal">
              {rack.shelf ? rack.shelf.place : "Weitere Plätze"}
              {rack.shelf ? <span className="ml-2 font-mono text-hint text-ink-tertiary">{rack.shelf.code}</span> : null}
            </h2>
            {rack.places.length > 0 ? (
              <PlaceLabelsDialog
                codes={rack.places.map((place) => place.code)}
                trigger={
                  <Button type="button" size="sm" variant="ghost">
                    Etiketten
                  </Button>
                }
              />
            ) : null}
          </header>
          {rack.places.length === 0 ? <p className="px-5 py-4 text-small text-ink-secondary">Kein Boden.</p> : null}
          <ul className="divide-y divide-line">
            {rack.places.map((place) => (
              <PlaceBlock key={place.id} place={place} lines={byPlace.get(place.code) ?? []} mayManage={mayManage} onDone={setMessage} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function PlaceBlock({
  place,
  lines,
  mayManage,
  onDone,
}: {
  place: LocationNodeOut;
  lines: readonly PlaceStockOut[];
  mayManage: boolean;
  onDone: (message: string) => void;
}) {
  const total = lines.reduce((sum, line) => sum + lying(line), 0);
  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-small font-medium">
          <Link href={`/admin/lager/plaetze/${place.code}` as Route} className="hover:underline">
            {place.name || place.code}
          </Link>
          <span className="ml-2 font-mono text-hint font-normal text-ink-tertiary">{place.code}</span>
          <span className="ml-2 text-hint font-normal text-ink-tertiary">{pieces(total)}</span>
        </p>
        {mayManage && lines.length > 0 ? (
          <CountDialog
            title={place.place}
            rows={lines.map((line) => ({
              variantId: line.variant_id,
              locationCode: line.location.code,
              expected: lying(line),
              counted: lying(line),
              label: line.variant?.title ?? line.variant_id,
            }))}
            onDone={onDone}
            trigger={
              <Button type="button" size="sm" variant="ghost">
                Zählen
              </Button>
            }
          />
        ) : null}
      </div>
      {lines.length > 0 ? (
        <ul className="mt-1.5 space-y-1">
          {lines.map((line) => (
            <li key={line.variant_id} className="flex items-baseline justify-between gap-3 text-small">
              {line.variant ? (
                <Link href={`/admin/modelle/${line.variant.product_id}` as Route} className="min-w-0 truncate hover:underline">
                  {line.variant.title}
                </Link>
              ) : (
                <span className="min-w-0 truncate text-ink-tertiary">Gelöschtes Modell</span>
              )}
              <span className="shrink-0 tabular-nums">
                <span className="font-medium">{lying(line)}</span>
                {line.reserved > 0 ? <span className="text-hint text-ink-tertiary"> ({line.reserved} reserviert)</span> : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function PlaceLabelsDialog({ codes, trigger }: { codes: readonly string[]; trigger: ReactNode }) {
  return (
    <Dialog>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogTitle>Etiketten der Plätze</DialogTitle>
        <DialogDescription>Für jeden Boden eins, mit Regal und Boden darauf.</DialogDescription>
        <LabelPrinter locationCodes={codes} className="mt-6" />
      </DialogContent>
    </Dialog>
  );
}

/** Neues Regal in one step: a name and how many Böden; then all their labels at once. */
function NewShelfDialog() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [boards, setBoards] = useState("3");
  const refresh = useInventoryRefresh();
  const count = Number.parseInt(boards, 10);
  const valid = Number.isInteger(count) && count >= 0 && count <= BOARDS_MAX;
  const create = useMutation<ShelfOut, ApiProblem>({
    mutationFn: () => createShelf({ name: name.trim(), levels: count }),
    onSuccess: refresh,
  });
  const made = create.data;
  const codes = made ? (made.levels.length > 0 ? made.levels.map((level) => level.code) : [made.shelf.code]) : [];
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setName("");
          setBoards("3");
          create.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" size="sm">
          Neues Regal
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        {made ? (
          <>
            <DialogTitle>{made.shelf.name} ist angelegt</DialogTitle>
            <DialogDescription>
              {made.levels.length === 0 ? "Ohne Böden: Das Regal selbst ist der Platz." : `Mit ${made.levels.length} Böden. Jetzt die Etiketten drucken und anbringen.`}
            </DialogDescription>
            <LabelPrinter locationCodes={codes} className="mt-6" />
            <div className="mt-6 flex justify-end">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Fertig
                </Button>
              </DialogClose>
            </div>
          </>
        ) : (
          <>
            <DialogTitle>Neues Regal</DialogTitle>
            <DialogDescription>Name und Zahl der Böden; die Böden heißen Boden 1, Boden 2 …</DialogDescription>
            <form
              noValidate
              className="mt-6 space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                if (valid) {
                  create.mutate();
                }
              }}
            >
              <FormField label="Name" hint="Leer: Regal 1, Regal 2 …">
                {(control) => <Input {...control} value={name} onChange={(event) => setName(event.target.value)} maxLength={60} placeholder="z. B. Regal am Fenster" />}
              </FormField>
              <FormField label="Böden" hint={`0 bis ${BOARDS_MAX}; ohne Böden ist das Regal selbst der Platz.`}>
                {(control) => <Input {...control} value={boards} onChange={(event) => setBoards(event.target.value)} inputMode="numeric" className="w-24" />}
              </FormField>
              <p role="alert" className="text-small text-danger empty:hidden">
                {create.error ? errorMessage(create.error) : null}
              </p>
              <div className="flex justify-end gap-3">
                <DialogClose asChild>
                  <Button type="button" variant="secondary">
                    Abbrechen
                  </Button>
                </DialogClose>
                <Button type="submit" disabled={!valid || create.isPending}>
                  {create.isPending ? "Wird angelegt …" : "Anlegen"}
                </Button>
              </div>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/**
 * Pieces labelled the old way and never put away (before ADR 0027): shown only while
 * there are some, with one button that books them all out as Versehen.
 */
function UnbookedHint() {
  const stock = useListStock();
  const refresh = useInventoryRefresh();
  const unbooked = (stock.data?.items ?? []).reduce((sum, line) => sum + line.labeled, 0);
  const clear = useMutation<number, ApiProblem>({
    async mutationFn() {
      let done = 0;
      for (;;) {
        const listed = await listUnits({ status: ["labeled"] });
        const ids = listed.items.map((unit) => unit.id).slice(0, SCRAP_BATCH);
        if (ids.length === 0) {
          return done;
        }
        const result = await scrapUnits({ unit_ids: ids, reason: "mistake", note: "Alter Ablauf" });
        done += result.scrapped;
        if (!listed.more) {
          return done;
        }
      }
    },
    onSuccess: refresh,
  });
  if (unbooked === 0 && !clear.isSuccess) {
    return null;
  }
  return (
    <div role="status" className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-md border border-warning bg-warning-subtle px-5 py-4 text-small">
      {clear.isSuccess ? (
        <p>{pieces(clear.data)} als Versehen ausgebucht.</p>
      ) : (
        <>
          <p>
            <span className="font-medium">{pieces(unbooked)} unverbucht</span> aus dem alten Ablauf: gedruckt, aber nie eingelagert.{" "}
            <Link href={unitListHref({ filter: "unverbucht" })} className="underline underline-offset-2 hover:no-underline">
              Ansehen
            </Link>
          </p>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            disabled={clear.isPending}
            onClick={() => {
              if (window.confirm(`${pieces(unbooked)} als Versehen ausbuchen?`)) {
                clear.mutate();
              }
            }}
          >
            {clear.isPending ? "Wird ausgebucht …" : "Alle als Versehen ausbuchen"}
          </Button>
          {clear.isError ? <p className="w-full text-danger">{errorMessage(clear.error)}</p> : null}
        </>
      )}
    </div>
  );
}
