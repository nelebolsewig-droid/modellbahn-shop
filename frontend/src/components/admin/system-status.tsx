"use client";

import { Button } from "@/components/ui/button";
import { SignalLamp, type LampColor } from "@/components/ui/signal-lamp";
import { useGetReadiness } from "@/lib/api/generated/system/system";
import { formatTime } from "@/lib/format";
import { systemStatusFrom, type ComponentStatus } from "@/lib/system-status";

import { Panel } from "./panel";

const CHECK_INTERVAL_MS = 15_000;

const DISPLAY: Record<ComponentStatus, { color: LampColor; label: string }> = {
  up: { color: "green", label: "Erreichbar" },
  down: { color: "red", label: "Nicht erreichbar" },
  unknown: { color: "off", label: "Unbekannt" },
};

/** API and database health from /readyz, checked every 15 seconds. */
export function SystemStatus() {
  const readiness = useGetReadiness({
    query: {
      refetchInterval: CHECK_INTERVAL_MS,
      // The point is to show failures as they are, not to hide them behind retries.
      retry: false,
      staleTime: 0,
    },
  });
  const status = systemStatusFrom(readiness);
  const checkedAt = Math.max(readiness.dataUpdatedAt, readiness.errorUpdatedAt);

  return (
    <Panel title="Systemstatus" code="STW 02">
      <dl className="divide-y divide-line">
        <StatusRow label="API" status={status.api} />
        <StatusRow label="Datenbank" status={status.database} />
      </dl>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-hint text-ink-tertiary tabular-nums">
          {checkedAt > 0 ? <>Geprüft {formatTime(new Date(checkedAt))}</> : "Wird geprüft …"}
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={readiness.isFetching}
          onClick={() => void readiness.refetch()}
        >
          Jetzt prüfen
        </Button>
      </div>
    </Panel>
  );
}

function StatusRow({ label, status }: { label: string; status: ComponentStatus }) {
  const display = DISPLAY[status];
  return (
    <div className="flex items-center justify-between gap-4 py-3 first:pt-0">
      <dt className="label-caps text-ink-secondary">{label}</dt>
      <dd className="flex items-center gap-2 text-small">
        <span>{display.label}</span>
        <SignalLamp color={display.color} />
      </dd>
    </div>
  );
}
