"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Button } from "@/components/ui/button";
import { getExportArticlesUrl } from "@/lib/api/generated/admin-catalog/admin-catalog";
import { getListLocationsQueryKey, getListStockQueryKey } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { StaffRole } from "@/lib/api/generated/model";
import { ADMIN_EVENTS_URL, INVENTORY_EVENT_TYPES, stockEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";

import { LocationPanel } from "./location-panel";
import { StockPanel } from "./stock-panel";
import { UnitsDialog } from "./units-dialog";

/** Owner and staff run the store; packers look and scan. */
export const MAY_MANAGE_STOCK: ReadonlySet<StaffRole> = new Set(["owner", "staff"]);

/** The store at a glance: stock per article and the tree of places, both live. */
export function InventoryOverview({ staffRole, onStreamClosed }: { staffRole: StaffRole; onStreamClosed: () => void }) {
  const queryClient = useQueryClient();
  const mayManage = MAY_MANAGE_STOCK.has(staffRole);
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: INVENTORY_EVENT_TYPES,
    onMessage(data) {
      const event = stockEventOf(data);
      if (event === null) {
        return;
      }
      void queryClient.invalidateQueries({ queryKey: getListStockQueryKey() });
      if (event.locationCodes.length > 0) {
        void queryClient.invalidateQueries({ queryKey: getListLocationsQueryKey() });
      }
    },
    onClosed: onStreamClosed,
  });

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label-caps text-ink-tertiary">Werkstatt</p>
          <h1 className="mt-3 text-heading sm:text-title">Lager</h1>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>
      <div className="mt-6 flex flex-wrap gap-2">
        {mayManage ? (
          <UnitsDialog
            trigger={
              <Button type="button" size="sm">
                Einheiten erfassen
              </Button>
            }
          />
        ) : null}
        <Button asChild size="sm" variant="secondary">
          <Link href="/admin/scanner">Scanner öffnen</Link>
        </Button>
        <Button asChild size="sm" variant="ghost">
          {/* A plain download: the browser sends the staff cookie along. */}
          <a href={getExportArticlesUrl()} download>
            Artikelliste für die Kasse (CSV)
          </a>
        </Button>
      </div>

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <StockPanel />
        <LocationPanel mayManage={mayManage} />
      </div>
    </>
  );
}
