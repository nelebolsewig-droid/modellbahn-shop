"use client";

import { useMutation } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { correctUnit } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { HistoryEntryOut, UnitDetailsOut, UnitOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { errorMessage } from "@/lib/i18n/problems";

import { LabelPrinter } from "./label-printer";
import { useInventoryRefresh } from "./part-dialogs";
import { VariantPicker, type ChosenVariant } from "./units-dialog";

/**
 * Whether the Stellwerk offers to change a piece's Ausführung: labelled or free in the
 * store, and never picked for an order (mirrors Unit.is_correctable; the backend decides).
 */
export function mayCorrect(unit: UnitDetailsOut): boolean {
  const orderSteps = new Set<HistoryEntryOut["reason"]>(["pick", "ship"]);
  return (unit.status === "labeled" || unit.status === "in_stock") && !unit.history.some((entry) => orderSteps.has(entry.reason));
}

type CorrectVariantDialogProps = { unit: UnitDetailsOut; trigger: ReactNode };

/**
 * A piece labelled as the wrong Ausführung becomes the right one where it lies. The EAN
 * on its label is the Ausführung's, so the dialog ends with printing a new label.
 */
export function CorrectVariantDialog({ unit, trigger }: CorrectVariantDialogProps) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<ChosenVariant | null>(null);
  const [corrected, setCorrected] = useState<UnitOut | null>(null);
  const refresh = useInventoryRefresh();
  const correct = useMutation<UnitOut, ApiProblem, ChosenVariant>({
    mutationFn: (variant) => correctUnit(unit.code, { variant_id: variant.variantId }),
    onSuccess(result) {
      refresh();
      setCorrected(result);
    },
  });
  const same = chosen !== null && chosen.variantId === unit.variant_id;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setChosen(null);
          setCorrected(null);
          correct.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-2xl">
        {corrected === null ? (
          <>
            <DialogTitle>Ausführung von {unit.display_code} ändern</DialogTitle>
            <DialogDescription>
              Falsch etikettiert? Das Stück wird zur gewählten Ausführung und bleibt, wo es liegt. Danach das Etikett neu
              drucken: Die EAN darauf gehört zur Ausführung.
            </DialogDescription>
            <form
              noValidate
              className="mt-6 space-y-5"
              onSubmit={(event) => {
                event.preventDefault();
                if (chosen !== null && !same) {
                  correct.mutate(chosen);
                }
              }}
            >
              <div className="rounded-sm border border-line bg-canvas px-4 py-3">
                <p className="label-caps text-ink-tertiary">Bisher</p>
                <p className="mt-1 text-small">{unit.variant?.title ?? "Gelöschtes Modell"}</p>
                {unit.variant ? (
                  <p className="font-mono text-hint text-ink-tertiary">
                    {unit.variant.sku}
                    {unit.variant.gtin ? ` · EAN ${unit.variant.gtin}` : ""}
                  </p>
                ) : null}
              </div>
              {chosen === null ? (
                <VariantPicker onChoose={setChosen} />
              ) : (
                <div className="flex items-center justify-between gap-4 rounded-sm border border-selected bg-sunken px-4 py-3">
                  <div className="min-w-0">
                    <p className="label-caps text-ink-tertiary">Richtig ist</p>
                    <p className="mt-1 truncate text-small font-medium">{chosen.title}</p>
                    <p className="font-mono text-hint text-ink-tertiary">{chosen.sku}</p>
                    {same ? <p className="mt-1 text-hint font-medium text-danger">Das ist die bisherige Ausführung.</p> : null}
                  </div>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setChosen(null)}>
                    Andere wählen
                  </Button>
                </div>
              )}
              <p role="alert" className="text-small text-danger empty:hidden">
                {correct.error ? errorMessage(correct.error) : null}
              </p>
              <div className="flex flex-wrap justify-end gap-3">
                <DialogClose asChild>
                  <Button type="button" variant="secondary" size="sm">
                    Abbrechen
                  </Button>
                </DialogClose>
                <Button
                  type="submit"
                  size="sm"
                  disabled={chosen === null || same || correct.isPending}
                  aria-busy={correct.isPending || undefined}
                >
                  {correct.isPending ? "Wird geändert …" : "Ausführung ändern"}
                </Button>
              </div>
            </form>
          </>
        ) : (
          <>
            <DialogTitle>Ausführung geändert</DialogTitle>
            <DialogDescription>
              {unit.display_code} ist jetzt {corrected.variant?.title ?? "die gewählte Ausführung"}.
              {corrected.order_number ? ` Es ging gleich an die wartende Bestellung ${corrected.order_number}.` : ""} Das
              alte Etikett trägt die falsche EAN: bitte neu drucken und austauschen.
            </DialogDescription>
            <section aria-label="Etikett neu drucken" className="mt-6 border-t border-line pt-6">
              <h3 className="text-small font-medium">Etikett neu drucken</h3>
              <LabelPrinter unitCodes={[unit.code]} className="mt-4" />
            </section>
            <div className="mt-6 flex justify-end">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Fertig
                </Button>
              </DialogClose>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
