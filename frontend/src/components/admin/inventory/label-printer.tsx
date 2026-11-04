"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { printLabels } from "@/lib/api/generated/admin-inventory/admin-inventory";
import { LabelSheet } from "@/lib/api/generated/model";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";

/** A4 sheet with 3 x 8 labels of 70 x 37 mm (e.g. Avery Zweckform 3474). */
export const A4_COLUMNS = 3;
export const A4_ROWS = 8;
export const A4_LABELS = A4_COLUMNS * A4_ROWS;

const SHEET_KEY = "mb-label-sheet";

const SHEET_NAMES: Readonly<Record<LabelSheet, string>> = {
  a4_70x37: "A4-Bogen · 70 × 37 mm",
  ql_62x29: "Brother QL · 62 mm Rolle",
};

/** The printer this computer used last (the packing desk has the QL, the office A4). */
function rememberedSheet(): LabelSheet {
  try {
    const stored = window.localStorage.getItem(SHEET_KEY);
    return stored === LabelSheet.ql_62x29 ? LabelSheet.ql_62x29 : LabelSheet.a4_70x37;
  } catch {
    return LabelSheet.a4_70x37;
  }
}

function remember(sheet: LabelSheet): void {
  try {
    window.localStorage.setItem(SHEET_KEY, sheet);
  } catch {
    // Private mode or blocked storage: the choice just isn't kept.
  }
}

function fileName(now: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `etiketten-${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}.pdf`;
}

type LabelPrinterProps = {
  unitCodes?: readonly string[];
  locationCodes?: readonly string[];
  /** Labels for boxes of printed parts. */
  partNumbers?: readonly string[];
  className?: string;
};

/** Choose the label stock, where to start on a used sheet, and get the PDF to print. */
export function LabelPrinter({ unitCodes = [], locationCodes = [], partNumbers = [], className }: LabelPrinterProps) {
  const count = unitCodes.length + locationCodes.length + partNumbers.length;
  // Rendered only in the browser (behind the staff session check), so storage is there.
  const [sheet, setSheet] = useState<LabelSheet>(rememberedSheet);
  const [skip, setSkip] = useState(0);
  const [pdf, setPdf] = useState<{ url: string; name: string } | null>(null);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => () => {
    if (pdf) {
      URL.revokeObjectURL(pdf.url);
    }
  }, [pdf]);

  function choose(next: LabelSheet) {
    setSheet(next);
    setPdf(null);
    remember(next);
  }

  async function generate() {
    setPending(true);
    setProblem(null);
    try {
      const blob = await printLabels({
        sheet,
        skip: sheet === LabelSheet.a4_70x37 ? skip : 0,
        unit_codes: [...unitCodes],
        location_codes: [...locationCodes],
        part_numbers: [...partNumbers],
      });
      setPdf({ url: URL.createObjectURL(blob), name: fileName(new Date()) });
    } catch (error) {
      setProblem(errorMessage(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className={className}>
      <OptionGroup label="Etiketten" value={sheet} onValueChange={(value) => choose(value as LabelSheet)}>
        {Object.values(LabelSheet).map((value) => (
          <OptionPill key={value} value={value}>
            {SHEET_NAMES[value]}
          </OptionPill>
        ))}
      </OptionGroup>

      <div className="mt-5 flex flex-wrap items-start gap-6">
        {sheet === LabelSheet.a4_70x37 ? (
          <SheetPreview
            count={count}
            skip={skip}
            onSkip={(next) => {
              setSkip(next);
              setPdf(null);
            }}
          />
        ) : (
          <RollPreview count={count} />
        )}
        <div className="min-w-48 flex-1 space-y-3 text-small">
          <p>
            <span className="font-medium tabular-nums">{count}</span> {count === 1 ? "Etikett" : "Etiketten"}
          </p>
          {sheet === LabelSheet.a4_70x37 ? (
            <p className="text-ink-secondary">
              Angebrochener Bogen? Auf das erste freie Feld tippen. {skip > 0 ? `Gedruckt wird ab Feld ${skip + 1}.` : ""}
            </p>
          ) : (
            <p className="text-ink-secondary">Im Druckdialog die Rolle 62 mm wählen und „Tatsächliche Größe“ einstellen.</p>
          )}
          {pdf ? (
            <div className="flex flex-wrap gap-2">
              <Button asChild size="sm">
                <a href={pdf.url} target="_blank" rel="noopener">
                  PDF öffnen
                </a>
              </Button>
              <Button asChild size="sm" variant="secondary">
                <a href={pdf.url} download={pdf.name}>
                  Herunterladen
                </a>
              </Button>
            </div>
          ) : (
            <Button type="button" size="sm" onClick={() => void generate()} disabled={pending || count === 0} aria-busy={pending || undefined}>
              {pending ? "PDF wird erstellt …" : "Etiketten als PDF"}
            </Button>
          )}
          <p role="alert" className="text-hint font-medium text-danger">
            {problem}
          </p>
        </div>
      </div>
    </div>
  );
}

/** The A4 sheet in miniature: used fields hatched, the ones this print fills in blue. */
function SheetPreview({ count, skip, onSkip }: { count: number; skip: number; onSkip: (skip: number) => void }) {
  const sheets = Math.max(1, Math.ceil((skip + count) / A4_LABELS));
  return (
    <figure className="shrink-0">
      <div
        role="group"
        aria-label="Startfeld auf dem Bogen"
        className="grid w-36 grid-cols-3 gap-[3px] rounded-xs border border-line-strong bg-surface p-[5px] shadow-[0_1px_0_var(--line)] [aspect-ratio:210/297]"
      >
        {Array.from({ length: A4_LABELS }, (_, index) => {
          const used = index < skip;
          const printed = !used && index < skip + count;
          return (
            <button
              key={index}
              type="button"
              aria-label={`Ab Feld ${index + 1} drucken`}
              aria-pressed={index === skip}
              onClick={() => onSkip(index)}
              className={cn(
                "cursor-pointer rounded-[2px] border transition-colors",
                used && "border-line bg-[repeating-linear-gradient(135deg,var(--line)_0_2px,transparent_2px_5px)]",
                printed && "border-accent bg-accent-subtle",
                !used && !printed && "border-line hover:border-ink-tertiary",
                index === skip && "outline-2 outline-offset-1 outline-accent",
              )}
            />
          );
        })}
      </div>
      <figcaption className="mt-2 text-hint text-ink-tertiary">
        {sheets === 1 ? "1 Bogen" : `${sheets} Bögen`}
      </figcaption>
    </figure>
  );
}

/** The QL roll: one label after the other. */
function RollPreview({ count }: { count: number }) {
  const shown = Math.min(count, 6);
  return (
    <figure className="shrink-0">
      <div aria-hidden="true" className="flex w-36 flex-col items-center gap-1 rounded-xs border border-line-strong bg-sunken px-3 py-2">
        {Array.from({ length: Math.max(shown, 1) }, (_, index) => (
          <span key={index} className={cn("block h-6 w-full rounded-[2px] border", count > 0 ? "border-accent bg-accent-subtle" : "border-line bg-surface")} />
        ))}
        {count > shown ? <span className="text-hint text-ink-tertiary">+ {count - shown}</span> : null}
      </div>
      <figcaption className="mt-2 text-hint text-ink-tertiary">62 × 29 mm</figcaption>
    </figure>
  );
}
