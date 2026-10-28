"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Panel } from "@/components/admin/panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { PendingNotice } from "@/components/ui/pending-notice";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  getGetLocationQueryKey,
  getListLocationsQueryKey,
  useGetLocation,
  useListLocations,
} from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { LocatedUnitOut, LocationContentsOut, StaffRole } from "@/lib/api/generated/model";
import { LOCATION_KIND_LABELS, UNIT_STATUS_LABELS, UNIT_STATUS_TONES } from "@/lib/inventory/labels";
import { childKinds, labelCodes, subtree } from "@/lib/inventory/locations";
import { errorMessage } from "@/lib/i18n/problems";
import { ADMIN_EVENTS_URL, INVENTORY_EVENT_TYPES, stockEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";

import { MAY_MANAGE_STOCK } from "./inventory-overview";
import { LabelPrinter } from "./label-printer";
import { LocationCreateDialog, LocationDeleteDialog, LocationRenameDialog } from "./location-dialogs";
import { LocationGlyph } from "./location-glyph";
import { LocationTree } from "./location-panel";

/** Whether a stock event touched this location or a place below it. */
function concerns(codes: readonly string[], contents: LocationContentsOut | undefined, code: string): boolean {
  if (contents?.location.kind === "site") {
    return true;
  }
  return codes.some((other) => other === code || other.startsWith(`${code}-`));
}

/** One location: where it sits, what lies in it, and the places below it. */
export function LocationDesk({ code, staffRole, onStreamClosed }: { code: string; staffRole: StaffRole; onStreamClosed: () => void }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const contents = useGetLocation(code);
  // The whole tree, for everything below this place (the contents name the direct children).
  const tree = useListLocations();
  const mayManage = MAY_MANAGE_STOCK.has(staffRole);
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: INVENTORY_EVENT_TYPES,
    onMessage(data) {
      const event = stockEventOf(data);
      if (event !== null && concerns(event.locationCodes, contents.data, code)) {
        void queryClient.invalidateQueries({ queryKey: getGetLocationQueryKey(code) });
        void queryClient.invalidateQueries({ queryKey: getListLocationsQueryKey() });
      }
    },
    onClosed: onStreamClosed,
  });

  if (contents.isPending) {
    return <PendingNotice>Der Lagerplatz wird geladen …</PendingNotice>;
  }
  if (contents.isError) {
    return (
      <div className="space-y-4">
        <Alert tone="danger" title="Der Lagerplatz konnte nicht geladen werden">
          <p>{errorMessage(contents.error)}</p>
        </Alert>
        <Button asChild variant="secondary">
          <Link href="/admin/lager">Zurück zum Lager</Link>
        </Button>
      </div>
    );
  }
  const { location, ancestors, children, units } = contents.data;
  const nested = subtree(tree.data?.items ?? [], location.code);
  const below = nested.length > 0 ? nested : [location, ...children];
  const canHaveChildren = childKinds(location).length > 0;

  return (
    <>
      <nav aria-label="Lage im Lager" className="flex flex-wrap items-center gap-2 text-small text-ink-secondary">
        <Link href="/admin/lager" className="font-medium hover:text-ink">
          Lager
        </Link>
        {ancestors.map((ancestor) => (
          <span key={ancestor.id} className="flex items-center gap-2">
            <span aria-hidden="true">/</span>
            <Link href={`/admin/lager/plaetze/${ancestor.code}` as Route} className="font-mono hover:text-ink">
              {ancestor.code}
            </Link>
          </span>
        ))}
      </nav>

      <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-5">
          <span className="flex size-16 items-center justify-center rounded-md border border-line bg-surface">
            <LocationGlyph kind={location.kind} className="size-9 text-ink" />
          </span>
          <div>
            <p className="label-caps text-ink-tertiary">{LOCATION_KIND_LABELS[location.kind]}</p>
            <h1 className="mt-1 font-mono text-heading tracking-wide sm:text-title">{location.code}</h1>
            {location.name ? <p className="mt-1 text-small text-ink-secondary">{location.name}</p> : null}
          </div>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {location.kind !== "site" ? <LabelsDialog codes={labelCodes(below)} title={location.code} /> : null}
        {mayManage && canHaveChildren ? (
          <LocationCreateDialog
            parent={location}
            trigger={
              <Button type="button" size="sm" variant="secondary">
                Platz darin anlegen
              </Button>
            }
          />
        ) : null}
        {mayManage ? (
          <LocationRenameDialog
            location={location}
            trigger={
              <Button type="button" size="sm" variant="ghost">
                Umbenennen
              </Button>
            }
          />
        ) : null}
        {mayManage ? (
          <LocationDeleteDialog
            location={location}
            onDeleted={() => router.push(ancestors.length > 0 ? (`/admin/lager/plaetze/${ancestors.at(-1)?.code}` as Route) : "/admin/lager")}
            trigger={
              <Button type="button" size="sm" variant="ghost" className="text-danger hover:bg-danger-subtle hover:text-danger">
                Entfernen
              </Button>
            }
          />
        ) : null}
      </div>

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Panel title={units.length === 1 ? "Inhalt · 1 Stück" : `Inhalt · ${units.length} Stück`} code="LG 11">
          {units.length === 0 ? (
            <p className="text-small text-ink-secondary">
              {location.holds_goods ? "Leer. Beim Einlagern diesen Platz scannen, dann die Ware." : "Hier liegt nichts direkt; die Ware liegt in den Plätzen darin."}
            </p>
          ) : (
            <UnitTable units={units} here={location.code} />
          )}
        </Panel>
        {canHaveChildren ? (
          <Panel title="Plätze darin" code="LG 12">
            {below.length <= 1 ? (
              <p className="text-small text-ink-secondary">Noch keine.</p>
            ) : (
              <LocationTree items={below.slice(1)} />
            )}
          </Panel>
        ) : null}
      </div>
    </>
  );
}

function UnitTable({ units, here }: { units: readonly LocatedUnitOut[]; here: string }) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {units.map((unit) => (
        <li key={unit.code} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 gap-y-1 py-2.5">
          <div className="min-w-0">
            <Link href={`/admin/lager/einheiten/${unit.code}` as Route} className="font-mono text-small font-medium hover:underline">
              {unit.display_code}
            </Link>
            <p className="truncate text-small text-ink-secondary">
              {unit.title ?? "Unbekannter Artikel"}
              {unit.sku ? <span className="ml-2 font-mono text-hint text-ink-tertiary">{unit.sku}</span> : null}
            </p>
          </div>
          <div className="text-right">
            <StatusBadge tone={UNIT_STATUS_TONES[unit.status]}>{UNIT_STATUS_LABELS[unit.status]}</StatusBadge>
            <p className="mt-0.5 font-mono text-hint text-ink-tertiary">
              {unit.location_code && unit.location_code !== here ? unit.location_code : ""}
              {unit.order_number ? ` ${unit.order_number}` : ""}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function LabelsDialog({ codes, title }: { codes: string[]; title: string }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" size="sm">
          {codes.length === 1 ? "Etikett drucken" : `Etiketten drucken (${codes.length})`}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogTitle>Etiketten für {title}</DialogTitle>
        <DialogDescription>
          {codes.length === 1 ? "Das Etikett für diesen Platz." : "Für diesen Platz und alle Plätze darin."}
        </DialogDescription>
        <LabelPrinter locationCodes={codes} className="mt-6" />
      </DialogContent>
    </Dialog>
  );
}
