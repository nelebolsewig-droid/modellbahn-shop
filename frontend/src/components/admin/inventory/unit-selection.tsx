"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import type { UnitStatus } from "@/lib/api/generated/model";
import { NOT_SELECTABLE_REASONS, onlyScrapped, onlyUnbooked, pieces, SELECTABLE_STATUSES } from "@/lib/inventory/selection";

import { MoveUnitsDialog, ScrapUnitsDialog, type SelectedUnit } from "./unit-dialogs";

export type UnitSelection<T extends SelectedUnit> = {
  /** The ticked pieces among those shown, in list order. */
  selected: T[];
  /** The pieces shown that can be ticked. */
  selectable: T[];
  /** Whether a piece in this state can be ticked here. */
  canSelect: (unit: SelectedUnit) => boolean;
  isSelected: (id: string) => boolean;
  toggle: (id: string) => void;
  /** Ticks or unticks all of `units`. */
  setAll: (units: readonly T[], on: boolean) => void;
  clear: () => void;
};

/**
 * Which pieces of a list are ticked. Only the pieces shown count: a piece that left the
 * list (moved on, filtered out) or can no longer be ticked drops out of the selection.
 * `statuses`: the states that can be ticked here (scrapped pieces in their own list).
 */
export function useUnitSelection<T extends SelectedUnit>(
  units: readonly T[],
  statuses: ReadonlySet<UnitStatus> = SELECTABLE_STATUSES,
): UnitSelection<T> {
  const [ticked, setTicked] = useState<ReadonlySet<string>>(new Set());
  const canSelect = (unit: SelectedUnit) => statuses.has(unit.status);
  const selectable = units.filter(canSelect);
  return {
    selected: selectable.filter((unit) => ticked.has(unit.id)),
    selectable,
    canSelect,
    isSelected: (id) => ticked.has(id),
    toggle(id) {
      setTicked((current) => {
        const next = new Set(current);
        if (!next.delete(id)) {
          next.add(id);
        }
        return next;
      });
    },
    setAll(some, on) {
      setTicked((current) => {
        const next = new Set(current);
        for (const unit of some) {
          if (on) {
            next.add(unit.id);
          } else {
            next.delete(unit.id);
          }
        }
        return next;
      });
    },
    clear: () => setTicked(new Set()),
  };
}

const CHECKBOX = "size-4 shrink-0 accent-[var(--selected)] disabled:cursor-not-allowed";

/** The box in front of one piece; a piece that cannot be ticked says why. */
export function UnitCheckbox<T extends SelectedUnit>({ unit, selection }: { unit: T; selection: UnitSelection<T> }) {
  if (!selection.canSelect(unit)) {
    const reason = NOT_SELECTABLE_REASONS[unit.status] ?? "";
    return <input type="checkbox" disabled title={reason} aria-label={`${unit.display_code}: ${reason}`} className={CHECKBOX} />;
  }
  return (
    <input
      type="checkbox"
      checked={selection.isSelected(unit.id)}
      onChange={() => selection.toggle(unit.id)}
      aria-label={`${unit.display_code} auswählen`}
      className={CHECKBOX}
    />
  );
}

/** Ticks every piece of `units` that can be ticked; half ticked when some are. */
export function SelectAllCheckbox<T extends SelectedUnit>({
  units,
  selection,
  label = "Alle auswählen",
  className,
}: {
  units: readonly T[];
  selection: UnitSelection<T>;
  label?: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const candidates = units.filter(selection.canSelect);
  const count = candidates.filter((unit) => selection.isSelected(unit.id)).length;
  const all = candidates.length > 0 && count === candidates.length;
  useEffect(() => {
    if (ref.current) {
      ref.current.indeterminate = count > 0 && !all;
    }
  }, [count, all]);
  return (
    <label className={className ?? "inline-flex cursor-pointer items-center gap-2.5 text-small"}>
      <input
        ref={ref}
        type="checkbox"
        checked={all}
        disabled={candidates.length === 0}
        onChange={() => selection.setAll(candidates, !all)}
        className={CHECKBOX}
      />
      {label}
    </label>
  );
}

/**
 * The bar under a list once pieces are ticked: move or store them, or take them out of
 * the stock; scrapped ones are booked in again. What was booked stays readable after the
 * bar is gone. `mayScrap`: owner and staff, who also book scrapped pieces in again.
 */
export function UnitSelectionBar<T extends SelectedUnit>({ selection, mayScrap }: { selection: UnitSelection<T>; mayScrap: boolean }) {
  const [message, setMessage] = useState("");
  const { selected } = selection;
  const statuses = selected.map((unit) => unit.status);
  const storing = onlyUnbooked(statuses);
  const restoring = onlyScrapped(statuses);
  const mixed = !restoring && statuses.includes("scrapped");
  const done = (text: string) => {
    selection.clear();
    setMessage(text);
  };
  return (
    <>
      <p role="status" className="text-small font-medium text-success not-empty:mt-4">
        {message}
      </p>
      {/* On the phone the bar rests on the Stellwerk's bottom bar, which keeps the safe area. */}
      {selected.length > 0 ? (
        <section
          aria-label="Auswahl"
          className="sticky bottom-[var(--stellwerk-bar,0px)] z-10 -mx-5 mt-4 flex flex-wrap items-center gap-x-4 gap-y-3 border-t border-line bg-surface/95 px-5 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur max-sm:pb-3 sm:mx-0 sm:rounded-md sm:border"
        >
          <p className="mr-auto text-small font-medium" aria-live="polite">
            {pieces(selected.length)} ausgewählt
          </p>
          <div className="flex flex-wrap gap-2">
            {(restoring && mayScrap) || !(restoring || mixed) ? (
              <MoveUnitsDialog
                units={selected}
                onMoved={done}
                trigger={
                  <Button type="button" size="sm">
                    {restoring ? "Wieder einbuchen …" : storing ? "Einlagern …" : "Umlagern …"}
                  </Button>
                }
              />
            ) : null}
            {mayScrap && !restoring && !mixed ? (
              <ScrapUnitsDialog
                units={selected}
                onScrapped={done}
                trigger={
                  <Button type="button" size="sm" variant="secondary" className="border-danger text-danger hover:border-danger hover:bg-danger-subtle">
                    Ausbuchen …
                  </Button>
                }
              />
            ) : null}
            <Button type="button" size="sm" variant="ghost" onClick={selection.clear}>
              Auswahl aufheben
            </Button>
          </div>
        </section>
      ) : null}
    </>
  );
}
