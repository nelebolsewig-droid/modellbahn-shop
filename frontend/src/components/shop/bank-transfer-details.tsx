"use client";

import { useState } from "react";

import type { BankTransferOut } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import { formatClock, formatLongDate } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Where the GiroCode of an order waiting for a transfer is served (an SVG). */
export function girocodeUrl(token: string): string {
  return `/api/v1/store/orders/${encodeURIComponent(token)}/girocode.svg`;
}

/**
 * What to transfer for an order paid in advance (ADR 0022): the account, the amount and the
 * order number as the only reference, each ready to copy, and the GiroCode that banking apps
 * read. The deadline closes it.
 */
export function BankTransferDetails({
  transfer,
  token,
  className,
}: {
  transfer: BankTransferOut;
  token: string;
  className?: string;
}) {
  const due = new Date(transfer.due_at);
  return (
    <div
      className={cn(
        "grid gap-8 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start",
        className,
      )}
    >
      <dl className="divide-y divide-line border-y border-line text-small">
        <Row label="Empfänger" value={transfer.account_holder} />
        <Row
          label="IBAN"
          value={transfer.iban}
          copy={transfer.iban.replaceAll(" ", "")}
          mono
        />
        {transfer.bic ? <Row label="BIC" value={transfer.bic} mono /> : null}
        {transfer.bank_name ? (
          <Row label="Bank" value={transfer.bank_name} />
        ) : null}
        <Row
          label="Betrag"
          value={formatPrice(transfer.amount_cents)}
          copy={(transfer.amount_cents / 100).toFixed(2).replace(".", ",")}
          strong
        />
        <Row
          label="Verwendungszweck"
          value={transfer.reference}
          copy={transfer.reference}
          mono
          strong
        />
        <Row
          label="Bitte bis"
          value={`${formatLongDate(due)}, ${formatClock(due)} Uhr`}
        />
      </dl>
      <figure className="mx-auto w-44 sm:mx-0">
        <div className="rounded-md border border-line bg-white p-2">
          {/* An SVG from our own API: next/image would add nothing but a loader. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={girocodeUrl(token)}
            alt={`GiroCode für die Überweisung von ${formatPrice(transfer.amount_cents)}`}
            width={160}
            height={160}
            className="block size-40"
          />
        </div>
        <figcaption className="mt-2 text-center text-hint text-ink-tertiary">
          GiroCode: mit der Banking-App scannen, alles ist ausgefüllt.
        </figcaption>
      </figure>
    </div>
  );
}

function Row({
  label,
  value,
  copy,
  mono = false,
  strong = false,
}: {
  label: string;
  value: string;
  /** What the copy button puts on the clipboard; no button without it. */
  copy?: string;
  mono?: boolean;
  strong?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 py-3">
      <dt className="text-ink-tertiary">{label}</dt>
      <dd className="flex flex-wrap items-baseline justify-end gap-x-3 gap-y-1">
        <span
          className={cn(
            "text-ink",
            // An IBAN or order number stays on one line; the button moves below it if need be.
            mono ? "font-mono whitespace-nowrap" : "break-words",
            strong && "font-medium",
            "tabular-nums",
          )}
        >
          {value}
        </span>
        {copy !== undefined ? <CopyButton text={copy} label={label} /> : null}
      </dd>
    </div>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 2000);
        });
      }}
      aria-label={`${label} kopieren`}
      className="shrink-0 rounded-full border border-line-control px-2.5 py-0.5 text-hint font-medium text-ink-secondary transition-colors hover:border-ink hover:text-ink"
    >
      <span aria-live="polite">{copied ? "Kopiert" : "Kopieren"}</span>
    </button>
  );
}
