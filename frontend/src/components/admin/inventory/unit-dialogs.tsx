"use client";

import { useMutation } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { moveUnits, scrapUnits, useListLocations } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { ScrapReason, UnitMoveOut, UnitScrapOut, UnitStatus } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { SCRAP_REASON_LABELS } from "@/lib/inventory/labels";
import { moveMessage, onlyUnbooked, pathLabel, pieces, scrapMessage } from "@/lib/inventory/selection";
import { errorMessage } from "@/lib/i18n/problems";
import { SCRAP_REASONS } from "@/lib/validation/inventory";

import { useInventoryRefresh } from "./part-dialogs";

/** What the dialogs need of a ticked piece. */
export type SelectedUnit = { id: string; display_code: string; status: UnitStatus };

function what(units: readonly SelectedUnit[]): string {
  return units.length === 1 ? (units[0] as SelectedUnit).display_code : pieces(units.length);
}

function Failure({ error }: { error: unknown }) {
  return (
    <p role="alert" className="text-small text-danger not-empty:mt-4">
      {error ? errorMessage(error) : null}
    </p>
  );
}

type MoveUnitsDialogProps = {
  units: readonly SelectedUnit[];
  trigger: ReactNode;
  /** Gets the sentence to show once they are booked. */
  onMoved: (message: string) => void;
};

/**
 * Pieces go to another place in one booking, without the scanner. Labelled pieces that
 * were never put away are stored (Einlagern): only then does the shop count them.
 */
export function MoveUnitsDialog({ units, trigger, onMoved }: MoveUnitsDialogProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [target, setTarget] = useState("");
  const refresh = useInventoryRefresh();
  const places = useListLocations({
    query: { enabled: open, select: (tree) => tree.items.filter((item) => item.holds_goods) },
  });
  const storing = onlyUnbooked(units.map((unit) => unit.status));
  const move = useMutation<UnitMoveOut, ApiProblem>({
    mutationFn: () => moveUnits({ unit_ids: units.map((unit) => unit.id), location_code: target }),
    onSuccess(result) {
      refresh();
      setOpen(false);
      onMoved(moveMessage(result, storing));
    },
    onError(error) {
      if (error.code === "units_not_movable") {
        refresh();
      }
    },
  });
  const query = search.trim().toLowerCase();
  const shown = (places.data ?? []).filter(
    (place) => query === "" || place.code.toLowerCase().includes(query) || place.name.toLowerCase().includes(query),
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setSearch("");
          setTarget("");
          move.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogTitle>
          {what(units)} {storing ? "einlagern" : "umlagern"}
        </DialogTitle>
        <DialogDescription>
          {storing
            ? "Etikettiert, aber noch in keinem Platz. Danach sind sie im Shop lieferbar."
            : "Reservierte Stücke behalten ihre Bestellung; was schon dort liegt, bleibt, wie es ist."}
        </DialogDescription>
        <form
          noValidate
          className="mt-6 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (target !== "") {
              move.mutate();
            }
          }}
        >
          <FormField label="Platz suchen">
            {(control) => (
              <Input
                {...control}
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Code oder Name, z. B. R01-F02"
                autoComplete="off"
                spellCheck={false}
              />
            )}
          </FormField>
          <fieldset>
            <legend className="text-small font-medium">Ziel</legend>
            {places.isPending ? <p className="mt-2 text-small text-ink-secondary">Die Plätze werden geladen …</p> : null}
            {places.isError ? <p className="mt-2 text-small text-danger">{errorMessage(places.error)}</p> : null}
            {places.isSuccess && shown.length === 0 ? (
              <p className="mt-2 text-small text-ink-secondary">Kein Fach, keine Box und keine Ablage passt dazu.</p>
            ) : null}
            {shown.length > 0 ? (
              <ul className="mt-2 max-h-64 divide-y divide-line overflow-y-auto rounded-sm border border-line">
                {shown.map((place) => (
                  <li key={place.id}>
                    <label className="flex cursor-pointer items-start gap-3 px-4 py-2.5 hover:bg-sunken has-checked:bg-accent-subtle">
                      <input
                        type="radio"
                        name="move-target"
                        value={place.code}
                        checked={target === place.code}
                        onChange={() => setTarget(place.code)}
                        className="mt-1 size-4 shrink-0 accent-[var(--selected)]"
                      />
                      <span className="min-w-0">
                        <span className="block text-small">
                          <span className="font-mono font-medium">{place.code}</span>
                          {place.name ? <span className="ml-2 text-ink-secondary">{place.name}</span> : null}
                        </span>
                        <span className="block truncate font-mono text-hint text-ink-tertiary">{pathLabel(place.path)}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            ) : null}
          </fieldset>
          <Failure error={move.error} />
          <div className="flex flex-wrap justify-end gap-3 pt-2">
            <DialogClose asChild>
              <Button type="button" variant="secondary" size="sm">
                Abbrechen
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" disabled={target === "" || move.isPending} aria-busy={move.isPending || undefined}>
              {move.isPending ? "Wird gebucht …" : storing ? "Hier einlagern" : "Hierher umlagern"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type ScrapReasonChoiceProps = {
  value: string;
  onChange: (reason: ScrapReason) => void;
  error?: string | undefined;
};

/** Why pieces leave the stock by hand; one must be chosen. */
export function ScrapReasonChoice({ value, onChange, error }: ScrapReasonChoiceProps) {
  const name = useId();
  const errorId = `${name}-error`;
  return (
    <fieldset aria-describedby={error ? errorId : undefined}>
      <legend className="text-small font-medium">Grund</legend>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {SCRAP_REASONS.map((reason) => (
          <label
            key={reason}
            className="flex cursor-pointer items-center gap-3 rounded-sm border border-line px-3 py-2.5 text-small hover:border-ink has-checked:border-selected has-checked:bg-sunken"
          >
            <input
              type="radio"
              name={name}
              value={reason}
              checked={value === reason}
              onChange={() => onChange(reason)}
              className="size-4 shrink-0 accent-[var(--selected)]"
            />
            {SCRAP_REASON_LABELS[reason]}
          </label>
        ))}
      </div>
      <p id={errorId} aria-live="polite" className="text-hint font-medium text-danger not-empty:mt-1.5">
        {error}
      </p>
    </fieldset>
  );
}

type ScrapUnitsDialogProps = {
  units: readonly SelectedUnit[];
  trigger: ReactNode;
  onScrapped: (message: string) => void;
};

/**
 * Pieces leave the stock in one booking: sold at a fair, broken, not found when counting,
 * or recorded by mistake. A reserved piece's order gets another one or waits.
 */
export function ScrapUnitsDialog({ units, trigger, onScrapped }: ScrapUnitsDialogProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ScrapReason | "">("");
  const [note, setNote] = useState("");
  const [missingReason, setMissingReason] = useState(false);
  const refresh = useInventoryRefresh();
  const scrap = useMutation<UnitScrapOut, ApiProblem, ScrapReason>({
    mutationFn: (chosen) => scrapUnits({ unit_ids: units.map((unit) => unit.id), reason: chosen, note: note.trim() }),
    onSuccess(result, chosen) {
      refresh();
      setOpen(false);
      onScrapped(scrapMessage(result, SCRAP_REASON_LABELS[chosen]));
    },
    onError(error) {
      if (error.code === "units_not_scrappable") {
        refresh();
      }
    },
  });
  const reserved = units.some((unit) => unit.status === "allocated");

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setReason("");
          setNote("");
          setMissingReason(false);
          scrap.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogTitle>{what(units)} ausbuchen</DialogTitle>
        <DialogDescription>
          Sie verlassen den Bestand und zählen im Shop nicht mehr.
          {reserved ? " Reservierte Bestellungen bekommen ein anderes Stück oder warten auf die Fertigung." : ""}
        </DialogDescription>
        <form
          noValidate
          className="mt-6 space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (reason === "") {
              setMissingReason(true);
              return;
            }
            scrap.mutate(reason);
          }}
        >
          <ScrapReasonChoice
            value={reason}
            onChange={(next) => {
              setReason(next);
              setMissingReason(false);
            }}
            error={missingReason ? "Bitte einen Grund wählen." : undefined}
          />
          <FormField label="Notiz" hint="Optional, z. B. „Messe Leipzig“ oder „Inventur Oktober“.">
            {(control) => (
              <Textarea {...control} value={note} onChange={(event) => setNote(event.target.value)} maxLength={200} rows={2} />
            )}
          </FormField>
          <Failure error={scrap.error} />
          <div className="flex flex-wrap justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary" size="sm">
                Behalten
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" variant="danger" disabled={scrap.isPending} aria-busy={scrap.isPending || undefined}>
              {scrap.isPending ? "Wird ausgebucht …" : "Ausbuchen"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
