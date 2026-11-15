import { StatusBadge } from "@/components/ui/status-badge";
import type { PickItemOut, PickListOut, PieceState } from "@/lib/api/generated/model";
import { PIECE_STATE_LABELS, PIECE_STATE_TONES } from "@/lib/inventory/labels";
import { cn } from "@/lib/utils";

/** Up to this many pieces the bar shows one block each; beyond, it fills continuously. */
const BLOCKS_MAX = 24;

const BLOCK_CLASSES: Readonly<Record<PieceState, string>> = {
  picked: "bg-success",
  shipped: "bg-ink-tertiary",
  reserved: "border border-accent bg-accent-subtle",
  backordered:
    "border border-warning bg-[repeating-linear-gradient(135deg,var(--warning-subtle)_0_4px,transparent_4px_8px)]",
  released: "border border-dashed border-line-strong",
};

/** The next piece to fetch: the first reserved one in walking order. */
export function nextPiece(list: PickListOut): PickItemOut | undefined {
  return list.items.find((item) => item.state === "reserved");
}

/**
 * Progress like a track occupancy panel: a block per piece, green once picked, blue
 * while it waits on the shelf, hatched amber while it still has to be made.
 */
export function PickProgress({ list, className }: { list: PickListOut; className?: string }) {
  const pieces = list.items.filter((item) => item.state !== "released");
  return (
    <div className={className}>
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-small">
          <span className="text-body-lg font-medium tabular-nums">{list.picked}</span>
          <span className="text-ink-secondary"> von {list.total} kommissioniert</span>
        </p>
        {list.complete ? <StatusBadge tone="success">Bereit zum Packen</StatusBadge> : null}
      </div>
      {pieces.length <= BLOCKS_MAX ? (
        <ol aria-hidden="true" className="mt-3 flex gap-1">
          {pieces.map((item) => (
            <li key={item.allocation_id} className={cn("h-2.5 min-w-2 flex-1 rounded-xs", BLOCK_CLASSES[item.state])} />
          ))}
        </ol>
      ) : (
        <div aria-hidden="true" className="mt-3 h-2.5 overflow-hidden rounded-xs bg-sunken">
          <div className="h-full bg-success transition-[width]" style={{ width: `${(list.picked / Math.max(list.total, 1)) * 100}%` }} />
        </div>
      )}
    </div>
  );
}

/**
 * ``Stellwerk Altenau · H0 · Fertigmodell, Rot`` → the model and its Ausführung. An order
 * line freezes the title as product name, then scale and finish (catalogue contract).
 */
export function splitTitle(title: string): { model: string; finish: string } {
  const parts = title.split(" · ");
  return parts.length >= 3 ? { model: parts.slice(0, -2).join(" · "), finish: parts.slice(-2).join(" · ") } : { model: title, finish: "" };
}

/** Pieces of the same Ausführung, at the same place and as far along, in one row. */
export function pickRows(items: readonly PickItemOut[]): PickItemOut[][] {
  const rows: PickItemOut[][] = [];
  for (const item of items) {
    const last = rows.at(-1)?.[0];
    if (last && last.variant_id === item.variant_id && last.state === item.state && last.location?.code === item.location?.code) {
      rows.at(-1)?.push(item);
    } else {
      rows.push([item]);
    }
  }
  return rows;
}

/**
 * What to fetch, in the order of a walk through the store; backorders at the end. Each
 * row names the model, its Ausführung and the place: one label fits every piece of an
 * Ausführung, so which piece it is does not matter (ADR 0027).
 */
export function PickList({ list, className }: { list: PickListOut; className?: string }) {
  const next = nextPiece(list);
  return (
    <ol className={cn("divide-y divide-line border-y border-line", className)}>
      {pickRows(list.items).map((row) => {
        const [item] = row as [PickItemOut, ...PickItemOut[]];
        const isNext = row.some((piece) => piece.allocation_id === next?.allocation_id);
        const done = item.state === "picked" || item.state === "shipped";
        const { model, finish } = splitTitle(item.title);
        return (
          <li
            key={item.allocation_id}
            aria-current={isNext ? "step" : undefined}
            className={cn(
              "grid grid-cols-[5.5rem_minmax(0,1fr)] items-start gap-x-4 gap-y-1 py-3 pr-1 pl-3 sm:grid-cols-[6.5rem_minmax(0,1fr)_auto]",
              isNext && "bg-accent-subtle/60 shadow-[inset_3px_0_0_var(--accent)]",
            )}
          >
            <PlaceTag item={item} />
            <div className="min-w-0">
              <p className={cn("text-small font-medium", done && "text-ink-secondary")}>
                {isNext ? <span className="mr-2 label-caps text-accent">Als Nächstes</span> : null}
                {row.length > 1 ? <span className="tabular-nums">{row.length} × </span> : null}
                {model}
              </p>
              <p className="mt-0.5 text-hint text-ink-secondary">
                {finish ? `${finish} · ` : null}
                <span className="font-mono text-ink-tertiary">{item.sku}</span>
              </p>
            </div>
            <StatusBadge tone={PIECE_STATE_TONES[item.state]} className="col-start-2 sm:col-start-auto sm:justify-self-end">
              {PIECE_STATE_LABELS[item.state]}
            </StatusBadge>
          </li>
        );
      })}
    </ol>
  );
}

/** The place as it stands on the shelf label, or the workbench for a piece still to make. */
function PlaceTag({ item }: { item: PickItemOut }) {
  if (item.state === "picked" || item.state === "shipped") {
    return (
      <span className="inline-flex h-7 items-center justify-center gap-1.5 rounded-xs bg-success-subtle px-2 text-hint font-medium text-success">
        <svg aria-hidden="true" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-3.5">
          <path d="m3.5 8.5 3 3 6-7" />
        </svg>
        {item.state === "picked" ? "Entnommen" : "Versendet"}
      </span>
    );
  }
  if (item.location === null) {
    return (
      <span className="inline-flex h-7 items-center justify-center rounded-xs border border-dashed border-warning px-2 text-hint font-medium text-warning">
        Fertigung
      </span>
    );
  }
  // "Regal 2, Boden 3" as people say it; the code where the place has no name.
  return (
    <span
      title={item.location.code}
      className="inline-flex min-h-7 min-w-0 items-center justify-center rounded-xs bg-selected px-2 py-0.5 text-center text-hint leading-tight font-medium text-on-selected"
    >
      {item.place ?? item.location.code}
    </span>
  );
}
