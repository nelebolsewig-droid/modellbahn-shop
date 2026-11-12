"use client";

import { useMutation } from "@tanstack/react-query";
import { useEffect, useEffectEvent, useState, type FormEvent } from "react";

import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { getUnit, takeStock } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { LocatedUnitOut, StocktakeOut } from "@/lib/api/generated/model";
import { ApiProblem } from "@/lib/api/problem";
import { SCRAP_REASON_LABELS, UNIT_STATUS_LABELS, UNIT_STATUS_TONES } from "@/lib/inventory/labels";
import { WedgeReader } from "@/lib/inventory/scanner-input";
import { pieces } from "@/lib/inventory/selection";
import {
  addFound,
  EMPTY_COUNT,
  expectedPieces,
  foundPiece,
  lookupVerdict,
  recognise,
  removeFound,
  stocktakeBody,
  stocktakeMessage,
  summarise,
  toggleSeen,
  type Count,
  type FoundPiece,
  type Summary,
} from "@/lib/inventory/stocktake";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";

import { useInventoryRefresh } from "./part-dialogs";

type Feedback = { tone: "success" | "info" | "danger"; text: string };

const FEEDBACK_TONES: Readonly<Record<Feedback["tone"], string>> = {
  success: "text-success",
  info: "text-ink-secondary",
  danger: "text-danger",
};

const NOT_A_UNIT: Readonly<Record<"variant" | "location" | "part" | "none", string>> = {
  variant: "Das ist die EAN des Modells. Bitte den Stück-Code auf dem Etikett scannen.",
  location: "Das ist ein Platz. Bitte die Etiketten der Stücke scannen.",
  part: "Das ist ein Teil, kein Stück.",
  none: "Diesen Code kann das Lager nicht lesen.",
};

/** Typing into a text field; a ticked checkbox may keep the focus while a hand scanner reads. */
function isTextEntry(target: EventTarget | null): boolean {
  if (target instanceof HTMLInputElement) {
    return target.type !== "checkbox" && target.type !== "radio";
  }
  return target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || (target instanceof HTMLElement && target.isContentEditable);
}

/** Where the journal has a found piece. */
function whence(piece: FoundPiece): string {
  if (piece.from) {
    return `gebucht in ${piece.from}`;
  }
  return piece.status === "scrapped" ? "ausgebucht" : "unverbucht";
}

type StocktakePanelProps = {
  here: string;
  units: readonly LocatedUnitOut[];
  /** The count was booked (with the sentence to show) or given up (without). */
  onDone: (message?: string) => void;
};

/**
 * Counting one place: the pieces the journal has here are ticked by hand or by scanning
 * their labels; pieces that turn up here but are booked elsewhere are noted as found.
 * Nothing is booked until „Abschließen“; the count lives only in this browser tab.
 */
export function StocktakePanel({ here, units, onDone }: StocktakePanelProps) {
  const [count, setCount] = useState<Count>(EMPTY_COUNT);
  const [manual, setManual] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [checking, setChecking] = useState(false);
  // The expected list follows the place live; ticks are kept by piece.
  const expected = expectedPieces(units, here);

  async function check(raw: string) {
    const recognised = recognise(raw, expected, count);
    switch (recognised.kind) {
      case "not_a_unit":
        setFeedback({ tone: "danger", text: NOT_A_UNIT[recognised.reading ?? "none"] });
        return;
      case "expected":
        setCount((current) => toggleSeen(current, recognised.piece.id, true));
        setFeedback({
          tone: recognised.already ? "info" : "success",
          text: `${recognised.piece.display_code} ${recognised.already ? "ist schon gezählt." : "gezählt."}`,
        });
        return;
      case "found_already":
        setFeedback({ tone: "info", text: `${recognised.piece.display_code} ist schon als gefunden notiert.` });
        return;
      case "lookup":
        break;
    }
    setChecking(true);
    try {
      const unit = await getUnit(recognised.code);
      const verdict = lookupVerdict(unit, here);
      if (verdict === "order") {
        setFeedback({
          tone: "danger",
          text: `${unit.display_code} ist ${UNIT_STATUS_LABELS[unit.status].toLowerCase()} und gehört zu einer Bestellung${unit.order_number ? ` (${unit.order_number})` : ""}. Es bleibt außen vor.`,
        });
      } else if (verdict === "here") {
        setCount((current) => toggleSeen(current, unit.id, true));
        setFeedback({ tone: "success", text: `${unit.display_code} gezählt.` });
      } else if (verdict === "below") {
        setFeedback({
          tone: "info",
          text: `${unit.display_code} ist in ${unit.location?.code ?? "einem Platz darin"} gebucht, einem Platz in diesem. Den bitte für sich zählen.`,
        });
      } else {
        const piece = foundPiece(unit);
        setCount((current) => addFound(current, piece));
        setFeedback({ tone: "success", text: `${unit.display_code} gefunden (${whence(piece)}): wird hier eingelagert.` });
      }
    } catch (error) {
      setFeedback({
        tone: "danger",
        text: error instanceof ApiProblem && error.code === "unit_not_found" ? "Diesen Stück-Code kennt das Lager nicht." : errorMessage(error),
      });
    } finally {
      setChecking(false);
    }
  }

  // A hand scanner types wherever the focus is; it is recognised by its rhythm.
  const onWedgeScan = useEffectEvent((code: string) => void check(code));
  useEffect(() => {
    const reader = new WedgeReader((code) => onWedgeScan(code));
    const onKey = (event: KeyboardEvent) => {
      if (isTextEntry(event.target) || event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      if (reader.feed(event.key, event.timeStamp)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);

  function onManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const raw = manual;
    setManual("");
    if (raw.trim() !== "") {
      void check(raw);
    }
  }

  const summary = summarise(expected, count);

  return (
    <Panel title={`Inventur · ${here}`} code="LG 14">
      <p className="text-small text-ink-secondary">
        Jedes Stück, das hier liegt, abhaken oder sein Etikett scannen. Liegt hier ein Stück, das anderswo gebucht ist,
        unverbucht oder ausgebucht, sein Etikett scannen: Es wird als gefunden notiert. Gebucht wird erst beim Abschließen.
      </p>
      <form onSubmit={onManual} className="mt-4 flex gap-2" aria-label="Code scannen oder eintippen">
        <label htmlFor="stocktake-code" className="sr-only">
          Code scannen oder eintippen
        </label>
        <Input
          id="stocktake-code"
          value={manual}
          onChange={(event) => setManual(event.target.value)}
          placeholder="Stück-Code scannen oder eintippen"
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={300}
          className="font-mono"
        />
        <Button type="submit" variant="secondary" disabled={manual.trim() === "" || checking}>
          Prüfen
        </Button>
      </form>
      <p role="status" className={cn("text-small font-medium not-empty:mt-3", feedback ? FEEDBACK_TONES[feedback.tone] : "")}>
        {checking ? "Wird nachgeschlagen …" : (feedback?.text ?? "")}
      </p>

      <h3 className="mt-6 flex items-baseline justify-between gap-3 text-small font-medium">
        <span>Erwartet</span>
        <span className="tabular-nums text-ink-secondary">
          {summary.confirmed.length} von {expected.length} gezählt
        </span>
      </h3>
      {expected.length === 0 ? (
        <p className="mt-2 text-small text-ink-secondary">Laut Lager liegt hier nichts.</p>
      ) : (
        <ul className="mt-2 divide-y divide-line border-y border-line">
          {expected.map((piece) => (
            <li key={piece.id}>
              <label className="grid cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-baseline gap-x-3 py-2.5">
                <input
                  type="checkbox"
                  checked={count.seen.has(piece.id)}
                  onChange={() => setCount((current) => toggleSeen(current, piece.id))}
                  className="size-4 shrink-0 self-center accent-[var(--selected)]"
                />
                <span className="min-w-0">
                  <span className="block font-mono text-small font-medium">{piece.display_code}</span>
                  <span className="block truncate text-hint text-ink-tertiary">
                    {piece.title ?? "Unbekanntes Modell"}
                    {piece.sku ? ` · ${piece.sku}` : ""}
                  </span>
                </span>
                <span className="text-right">
                  <StatusBadge tone={UNIT_STATUS_TONES[piece.status]}>{UNIT_STATUS_LABELS[piece.status]}</StatusBadge>
                  {piece.order_number ? <span className="mt-0.5 block font-mono text-hint text-ink-tertiary">{piece.order_number}</span> : null}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}

      {count.found.length > 0 ? (
        <>
          <h3 className="mt-6 text-small font-medium">Gefunden · {pieces(count.found.length)}</h3>
          <ul className="mt-2 divide-y divide-line border-y border-line">
            {count.found.map((piece) => (
              <li key={piece.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 py-2.5">
                <span className="min-w-0">
                  <span className="block font-mono text-small font-medium">{piece.display_code}</span>
                  <span className="block truncate text-hint text-ink-tertiary">
                    {piece.title ?? "Unbekanntes Modell"} · {whence(piece)}
                  </span>
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setCount((current) => removeFound(current, piece.id))}
                  aria-label={`${piece.display_code} nicht mehr als gefunden notieren`}
                >
                  Entfernen
                </Button>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <div className="mt-6 flex flex-wrap justify-end gap-3">
        <Button type="button" variant="ghost" size="sm" onClick={() => onDone()}>
          Inventur abbrechen
        </Button>
        <FinishDialog here={here} summary={summary} onBooked={(result) => onDone(stocktakeMessage(result))} />
      </div>
    </Panel>
  );
}

/** What the count books, said before it is booked; one confirmation books it all. */
function FinishDialog({ here, summary, onBooked }: { here: string; summary: Summary; onBooked: (result: StocktakeOut) => void }) {
  const [open, setOpen] = useState(false);
  const refresh = useInventoryRefresh();
  const book = useMutation<StocktakeOut, ApiProblem>({
    mutationFn: () => takeStock(here, stocktakeBody(summary)),
    onSuccess(result) {
      refresh();
      setOpen(false);
      onBooked(result);
    },
    onError(error) {
      if (error.code === "stocktake_outdated" || error.code === "units_not_movable") {
        refresh();
      }
    },
  });
  const { confirmed, missing, missingReserved, found, foundScrapped } = summary;
  const nothing = missing.length === 0 && found.length === 0;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          book.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" size="sm">
          Abschließen …
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogTitle>Inventur {here} abschließen</DialogTitle>
        <DialogDescription>
          {nothing ? "Alles stimmt: Es ist nichts zu buchen." : "Ein Klick bucht alles zusammen, oder nichts, falls sich der Platz inzwischen geändert hat."}
        </DialogDescription>
        <ul className="mt-6 space-y-4 text-small">
          <li>
            <span className="font-medium tabular-nums">{confirmed.length} bestätigt</span>
            <span className="text-ink-secondary">: liegen, wo das Lager sie führt.</span>
          </li>
          <li>
            <span className={cn("font-medium tabular-nums", missing.length > 0 && "text-danger")}>{missing.length} fehlen</span>
            {missing.length > 0 ? (
              <>
                <span className="text-ink-secondary">
                  {" "}
                  → werden ausgebucht mit Grund „{SCRAP_REASON_LABELS.missing}“.
                  {missingReserved.length > 0
                    ? ` ${missingReserved.length === 1 ? "Eins davon ist" : `${missingReserved.length} davon sind`} reserviert: Die Bestellung bekommt ein anderes Stück oder wartet auf die Fertigung.`
                    : ""}
                </span>
                <span className="mt-1 block font-mono text-hint text-ink-tertiary">{missing.map((piece) => piece.display_code).join(", ")}</span>
              </>
            ) : null}
          </li>
          <li>
            <span className="font-medium tabular-nums">{found.length} gefunden</span>
            {found.length > 0 ? (
              <>
                <span className="text-ink-secondary">
                  {" "}
                  → werden hier eingelagert.
                  {foundScrapped.length > 0
                    ? ` ${foundScrapped.length === 1 ? "Eins davon war" : `${foundScrapped.length} davon waren`} ausgebucht und wird wieder eingebucht.`
                    : ""}
                </span>
                <span className="mt-1 block font-mono text-hint text-ink-tertiary">{found.map((piece) => piece.display_code).join(", ")}</span>
              </>
            ) : null}
          </li>
        </ul>
        <p role="alert" className="text-small text-danger not-empty:mt-4">
          {book.error
            ? book.error.code === "units_not_movable"
              ? "Ein gefundenes Stück gehört inzwischen zu einer Bestellung und lässt sich hier nicht einlagern. Es wurde nichts gebucht; bitte es aus „Gefunden“ entfernen."
              : errorMessage(book.error)
            : null}
        </p>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <DialogClose asChild>
            <Button type="button" variant="secondary" size="sm">
              Weiter zählen
            </Button>
          </DialogClose>
          <Button
            type="button"
            size="sm"
            variant={missing.length > 0 ? "danger" : "primary"}
            disabled={book.isPending}
            aria-busy={book.isPending || undefined}
            onClick={() => book.mutate()}
          >
            {book.isPending ? "Wird gebucht …" : "Inventur buchen"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
