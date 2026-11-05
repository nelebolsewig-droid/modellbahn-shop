"use client";

import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

/** The harmonised notice on the legal guarantee, unchanged, as the EU publishes it in German. */
export const WARRANTY_NOTICE_SRC = "/rechtliches/eu-gewaehrleistung.jpg";
const WIDTH = 1219;
const HEIGHT = 1668;

const ALT =
  "EU-Hinweis „Gesetzliche Gewährleistung“: Mindestens zwei Jahre gesetzliche Gewährleistung der Vertragsmäßigkeit " +
  "für Waren, die in der Europäischen Union verkauft werden. Entspricht eine Ware nicht der Beschreibung oder " +
  "funktioniert sie nicht bestimmungsgemäß, haften Verkäufer für jede Vertragswidrigkeit, die bei Lieferung bestand: " +
  "kostenlose Nachbesserung oder Ersatzlieferung, in bestimmten Fällen Preisminderung oder vollständige Erstattung. " +
  "Melden Sie das Problem dem Verkäufer so bald wie möglich und legen Sie einen Kaufnachweis vor. " +
  "Mehr unter europa.eu/youreurope/garantien.";

/**
 * The EU's harmonised notice on the legal guarantee (Directive (EU) 2024/825, Implementing
 * Regulation (EU) 2025/1960), shown prominently before the order is placed. The image is the
 * official notice and is never altered; `compact` shows it small with a click to enlarge.
 */
export function WarrantyNotice({ compact = false, className }: { compact?: boolean; className?: string }) {
  const image = (
    // A plain <img>: the notice must keep its exact appearance, so no re-encoding by an optimiser.
    // eslint-disable-next-line @next/next/no-img-element
    <img src={WARRANTY_NOTICE_SRC} width={WIDTH} height={HEIGHT} alt={ALT} className="h-auto w-full" />
  );
  if (!compact) {
    return <figure className={cn("overflow-hidden rounded-md border border-line bg-white", className)}>{image}</figure>;
  }
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className={cn(
            "group block w-full overflow-hidden rounded-md border border-line bg-white text-left",
            "transition-[border-color,box-shadow] hover:border-ink-secondary focus-visible:outline-offset-2",
            className,
          )}
          aria-label="EU-Hinweis zur gesetzlichen Gewährleistung vergrößern"
        >
          {image}
          <span className="block border-t border-line bg-surface px-3 py-2 text-hint text-ink-secondary group-hover:text-ink">
            Gesetzliche Gewährleistung: mindestens 2 Jahre · vergrößern
          </span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl p-4 sm:p-6">
        <DialogTitle className="sr-only">EU-Hinweis zur gesetzlichen Gewährleistung</DialogTitle>
        {image}
      </DialogContent>
    </Dialog>
  );
}
