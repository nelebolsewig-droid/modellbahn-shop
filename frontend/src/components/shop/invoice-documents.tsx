import type { InvoiceOut } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import { formatLongDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export const INVOICE_TITLES = {
  invoice: "Rechnung",
  correction: "Rechnungskorrektur",
} as const satisfies Record<InvoiceOut["kind"], string>;

type InvoiceDocumentsProps = {
  invoices: readonly InvoiceOut[];
  /** Where the PDF of one invoice is served. */
  urlOf: (invoice: InvoiceOut) => string;
  className?: string;
};

/**
 * The order's invoices and corrections (ADR 0038), each a small paper slip with its
 * number, date and amount: open it in the browser or save the PDF.
 */
export function InvoiceDocuments({ invoices, urlOf, className }: InvoiceDocumentsProps) {
  return (
    <ul className={cn("space-y-3", className)}>
      {invoices.map((invoice) => {
        const url = urlOf(invoice);
        const correction = invoice.kind === "correction";
        return (
          <li
            key={invoice.id}
            className={cn(
              "relative overflow-hidden rounded-md border border-line bg-surface py-3 pr-4 pl-5",
              // The slip's edge: mandarin for the invoice, ink for a correction.
              "before:absolute before:inset-y-0 before:left-0 before:w-1",
              correction ? "before:bg-ink" : "before:bg-accent",
            )}
          >
            <span
              aria-hidden
              className="absolute top-0 right-0 size-4 bg-canvas [clip-path:polygon(0_0,100%_100%,100%_0)]"
            />
            <div className="flex items-baseline justify-between gap-4">
              <span className="label-caps text-ink-tertiary">{INVOICE_TITLES[invoice.kind]}</span>
              <span className="text-small font-medium tabular-nums">{formatPrice(invoice.total_cents)}</span>
            </div>
            <p className="mt-1 font-mono text-small tabular-nums">{invoice.number}</p>
            <p className="text-hint text-ink-tertiary">vom {formatLongDate(new Date(invoice.issued_at))}</p>
            <p className="mt-2 flex gap-4 text-small font-medium">
              <a
                href={url}
                target="_blank"
                rel="noopener"
                className="text-ink underline underline-offset-4 hover:text-accent"
              >
                Ansehen
              </a>
              <a
                href={url}
                download={invoice.filename}
                className="text-ink underline underline-offset-4 hover:text-accent"
              >
                Als PDF speichern
              </a>
            </p>
          </li>
        );
      })}
    </ul>
  );
}
