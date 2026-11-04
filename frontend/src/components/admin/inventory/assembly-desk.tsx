"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { PendingNotice } from "@/components/ui/pending-notice";
import { QuantityStepper } from "@/components/ui/quantity-stepper";
import { Select } from "@/components/ui/select";
import { assemble, useListLocations, usePlanAssembly } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { AssemblyOut, AssemblyPartOut, AssemblyPlanOut, StaffRole } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatUnitCode } from "@/lib/inventory/codes";
import { partCount } from "@/lib/inventory/labels";
import { coverage } from "@/lib/inventory/parts";
import { errorMessage } from "@/lib/i18n/problems";
import { ADMIN_EVENTS_URL, INVENTORY_EVENT_TYPES, stockEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";
import { cn } from "@/lib/utils";

import { MAY_MANAGE_STOCK } from "./inventory-overview";
import { LabelPrinter } from "./label-printer";
import { useInventoryRefresh } from "./part-dialogs";
import { partHref } from "./parts-panels";
import { VariantPicker, type ChosenVariant } from "./units-dialog";

const KITS_MAX = 50;
const PLAN_PREFIX = "/api/v1/admin/inventory/assembly-plan";

/**
 * "Montage": parts out of their boxes by the bill of materials, into units with their
 * own labels. The plan shows where to take what, in walking order, before anything is
 * booked; a box that ran short meanwhile stops the booking.
 */
export function AssemblyDesk({ staffRole, onStreamClosed }: { staffRole: StaffRole; onStreamClosed: () => void }) {
  const queryClient = useQueryClient();
  const mayAssemble = MAY_MANAGE_STOCK.has(staffRole);
  const [chosen, setChosen] = useState<ChosenVariant | null>(null);
  const [kits, setKits] = useState(1);
  const [place, setPlace] = useState("");
  const [done, setDone] = useState<{ result: AssemblyOut; variant: ChosenVariant } | null>(null);
  const refresh = useInventoryRefresh();
  const plan = usePlanAssembly(
    { variant_id: chosen?.variantId ?? "", quantity: kits },
    { query: { enabled: chosen !== null, retry: false } },
  );
  const places = useListLocations({ query: { select: (tree) => tree.items.filter((item) => item.holds_goods) } });
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: INVENTORY_EVENT_TYPES,
    onMessage(data) {
      if (stockEventOf(data)?.partNumber) {
        void queryClient.invalidateQueries({ predicate: (query) => String(query.queryKey[0]).startsWith(PLAN_PREFIX) });
      }
    },
    onClosed: onStreamClosed,
  });
  const book = useMutation<AssemblyOut, ApiProblem>({
    mutationFn: () =>
      assemble({ variant_id: chosen?.variantId ?? "", quantity: kits, location_code: place === "" ? null : place }),
    onSuccess(result) {
      refresh();
      if (chosen) {
        setDone({ result, variant: chosen });
      }
    },
    onError() {
      void plan.refetch();
    },
  });

  const restart = () => {
    setDone(null);
    setKits(1);
    book.reset();
  };

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label-caps text-ink-tertiary">
            <Link href="/admin/lager" className="hover:text-ink">
              Lager
            </Link>
          </p>
          <h1 className="mt-3 text-heading sm:text-title">Montage</h1>
          <p className="mt-2 max-w-2xl text-small text-ink-secondary">
            Teile aus den Boxen nach der Stückliste, zu Bausätzen und Modellen. Jedes Stück bekommt sein Etikett, und
            das Journal weiß, aus welchen Boxen seine Teile stammen.
          </p>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        {done ? (
          <Assembled result={done.result} variant={done.variant} onAgain={restart} />
        ) : (
          <Panel title="Auftrag" code="MT 01">
            <div className="space-y-5">
              {chosen ? (
                <div className="flex items-center justify-between gap-4 rounded-sm border border-line bg-canvas px-4 py-3">
                  <div className="min-w-0">
                    <p className="label-caps text-ink-tertiary">Artikel</p>
                    <p className="mt-1 text-small font-medium">{chosen.title}</p>
                    <p className="font-mono text-hint text-ink-tertiary">{chosen.sku}</p>
                  </div>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setChosen(null)}>
                    Ändern
                  </Button>
                </div>
              ) : (
                <VariantPicker onChoose={setChosen} />
              )}
              <div>
                <p className="text-small font-medium">Stück</p>
                <QuantityStepper
                  value={kits}
                  onChange={setKits}
                  label="Anzahl der Stücke"
                  min={1}
                  max={KITS_MAX}
                  className="mt-2"
                />
              </div>
              <FormField label="Platz" hint="Ohne Platz warten die Stücke mit Etikett, bis jemand sie einlagert.">
                {(control) => (
                  <Select
                    {...control}
                    value={place}
                    onChange={(event) => setPlace(event.target.value)}
                    disabled={places.isPending}
                  >
                    <option value="">Später beim Einlagern scannen</option>
                    {(places.data ?? []).map((location) => (
                      <option key={location.id} value={location.code}>
                        {location.code}
                        {location.name ? ` · ${location.name}` : ""}
                      </option>
                    ))}
                  </Select>
                )}
              </FormField>
              <p role="alert" className="text-small text-danger empty:hidden">
                {book.isError ? errorMessage(book.error) : null}
              </p>
              {mayAssemble ? (
                <Button
                  type="button"
                  className="w-full"
                  disabled={!plan.data?.ready || book.isPending}
                  aria-busy={book.isPending || undefined}
                  onClick={() => book.mutate()}
                >
                  {book.isPending ? "Wird gebucht …" : kits === 1 ? "1 Stück montieren" : `${kits} Stück montieren`}
                </Button>
              ) : (
                <p className="text-hint text-ink-tertiary">Montage buchen dürfen Inhaber und Mitarbeiter.</p>
              )}
            </div>
          </Panel>
        )}
        <Panel title="Entnahmeliste" code="MT 02">
          {chosen === null && !done ? (
            <p className="text-small text-ink-secondary">
              Wähle einen Artikel. Hier steht dann, welche Teile er braucht und aus welchen Boxen sie kommen.
            </p>
          ) : null}
          {chosen !== null && !done && plan.isPending ? <PendingNotice>Der Plan wird berechnet …</PendingNotice> : null}
          {chosen !== null && !done && plan.isError ? (
            <p role="alert" className="text-small text-danger">
              {errorMessage(plan.error)}
            </p>
          ) : null}
          {done ? <PickSheet plan={done.result.plan} booked /> : plan.data ? <PickSheet plan={plan.data} /> : null}
        </Panel>
      </div>
    </>
  );
}

/** How many kits the stock gives, as a row of kit slots: filled, or still missing parts. */
function KitGauge({ plan }: { plan: AssemblyPlanOut }) {
  const ready = Math.min(plan.possible, plan.quantity);
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="label-caps text-ink-tertiary">Aus dem Lager möglich</p>
        <p
          className={cn(
            "mt-1 text-[2.5rem] leading-[2.75rem] font-extralight tabular-nums",
            plan.possible === 0 && "text-ink-disabled",
          )}
        >
          {plan.possible}
          <span className="ml-2 text-small font-normal text-ink-secondary">Stück aus den Boxen</span>
        </p>
      </div>
      <ol
        aria-label={`${ready} von ${plan.quantity} Stück lassen sich jetzt montieren`}
        className="flex max-w-full flex-wrap gap-1"
      >
        {Array.from({ length: plan.quantity }, (_, index) => (
          <li
            key={index}
            className={cn(
              "size-4 rounded-[3px] border",
              index < ready ? "border-accent bg-accent-subtle" : "border-dashed border-danger bg-danger-subtle",
            )}
          />
        ))}
      </ol>
    </div>
  );
}

function PickSheet({ plan, booked = false }: { plan: AssemblyPlanOut; booked?: boolean }) {
  return (
    <>
      {booked ? <p className="text-small text-ink-secondary">So wurde entnommen:</p> : <KitGauge plan={plan} />}
      <ol className="mt-5 divide-y divide-line border-y border-line">
        {plan.parts.map((line, index) => (
          <PickLine key={line.part.part_id} line={line} position={index + 1} kits={plan.quantity} booked={booked} />
        ))}
      </ol>
      {!booked && !plan.ready ? (
        <p className="mt-4 text-small text-ink-secondary">
          Es fehlen Teile.{" "}
          <Link href={"/admin/fertigung" as Route} className="text-accent hover:underline">
            In der Druckerhalle eine Platte planen
          </Link>
          , oder weniger Stück montieren.
        </p>
      ) : null}
    </>
  );
}

function PickLine({
  line,
  position,
  kits,
  booked,
}: {
  line: AssemblyPartOut;
  position: number;
  kits: number;
  booked: boolean;
}) {
  const share = coverage(line);
  return (
    <li className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3 py-3">
      <span className="pt-0.5 font-mono text-hint text-ink-tertiary">{String(position).padStart(2, "0")}</span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <p className="min-w-0 text-small">
            <Link href={partHref(line.part.part_number)} className="font-medium hover:underline">
              {line.part.name}
            </Link>
            <span className="ml-2 font-mono text-hint text-ink-tertiary">{line.part.part_number}</span>
          </p>
          <p className="text-small tabular-nums text-ink-secondary">
            {line.per_kit} × {kits} = <span className="font-medium text-ink">{line.needed}</span>
          </p>
        </div>
        {!booked ? (
          <div className="mt-2 flex items-center gap-3">
            <span aria-hidden="true" className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken">
              <span
                className={cn("block h-full rounded-full", share >= 1 ? "bg-success" : "bg-danger")}
                style={{ width: `${Math.round(share * 100)}%` }}
              />
            </span>
            <span className={cn("text-hint whitespace-nowrap", line.missing > 0 ? "text-danger" : "text-ink-tertiary")}>
              {line.missing > 0 ? `es fehlen ${line.missing}` : `${partCount(line.available)} da`}
            </span>
          </div>
        ) : null}
        {line.takes.length > 0 ? (
          <ul className="mt-2 flex flex-wrap gap-1.5" aria-label={`Entnahme ${line.part.name}`}>
            {line.takes.map((take) => (
              <li
                key={take.location_code}
                className="inline-flex items-baseline gap-1.5 rounded-xs border border-line bg-canvas px-2 py-0.5 font-mono text-hint"
              >
                {take.location_code}
                <span className="font-sans text-ink-tertiary">nimm</span>
                <span className="font-medium tabular-nums">{take.quantity}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </li>
  );
}

function Assembled({ result, variant, onAgain }: { result: AssemblyOut; variant: ChosenVariant; onAgain: () => void }) {
  const stored = result.units[0]?.location?.code;
  return (
    <Panel
      title={result.units.length === 1 ? "1 Stück montiert" : `${result.units.length} Stück montiert`}
      code="MT 01"
    >
      <p className="text-small font-medium">{variant.title}</p>
      <p className="mt-1 text-small text-ink-secondary">
        {stored ? `Liegen in ${stored}.` : "Liegen bereit zum Einlagern: Platz scannen, dann die Etiketten."}
      </p>
      <ul className="mt-4 flex flex-wrap gap-1.5">
        {result.units.slice(0, 12).map((unit) => (
          <li key={unit.id}>
            <Link
              href={`/admin/lager/einheiten/${unit.code}` as Route}
              className="block rounded-xs bg-sunken px-2 py-1 font-mono text-hint hover:bg-line"
            >
              {formatUnitCode(unit.code)}
            </Link>
          </li>
        ))}
        {result.units.length > 12 ? (
          <li className="px-2 py-1 text-hint text-ink-tertiary">+ {result.units.length - 12}</li>
        ) : null}
      </ul>
      <LabelPrinter unitCodes={result.units.map((unit) => unit.code)} className="mt-6 border-t border-line pt-6" />
      <Button type="button" variant="secondary" className="mt-6 w-full" onClick={onAgain}>
        Weiter montieren
      </Button>
    </Panel>
  );
}
