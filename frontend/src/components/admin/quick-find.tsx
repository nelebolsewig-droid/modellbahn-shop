"use client";

import { Content, Overlay, Portal, Root, Title } from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useId, useState, useSyncExternalStore, type KeyboardEvent } from "react";

import { listProducts } from "@/lib/api/generated/admin-catalog/admin-catalog";
import { listOrders } from "@/lib/api/generated/admin-sales/admin-sales";
import type { StaffRole } from "@/lib/api/generated/model";
import { findShortcuts, looksLikeOrderNumber } from "@/lib/admin/quick-find";
import { formatPrice } from "@/lib/catalog/format";
import { ORDER_STATUS_LABELS } from "@/lib/sales/labels";
import { OFFICE_ROLES } from "@/lib/staff";
import { cn } from "@/lib/utils";

type Hit = { key: string; group: string; label: string; hint: string; href: Route };

const LIMIT = 5;

/** ⌘K on a Mac, Ctrl+K elsewhere: what the button and the search field show. */
function useShortcutLabel(): string {
  return useSyncExternalStore(
    noSubscription,
    () => (/Mac|iPhone|iPad/.test(navigator.userAgent) ? "⌘K" : "Strg K"),
    () => "Strg K",
  );
}

function noSubscription(): () => void {
  return () => {};
}

/**
 * The Stellwerk's quick search (ADR 0033): ⌘K or Strg+K anywhere, or the button, opens one
 * field that finds pages, actions, orders and models. Arrow keys choose, Enter opens.
 */
export function QuickFind({ role, className }: { role: StaffRole; className?: string }) {
  const [open, setOpen] = useState(false);
  const keys = useShortcutLabel();

  useEffect(() => {
    function onKey(event: globalThis.KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((before) => !before);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <Root open={open} onOpenChange={setOpen}>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-keyshortcuts="Meta+K Control+K"
        className={cn(
          "flex min-h-10 shrink-0 cursor-pointer items-center gap-2.5 border border-line bg-canvas px-3 text-small text-ink-secondary transition-colors hover:border-ink hover:text-ink",
          className,
        )}
      >
        <SearchGlyph className="size-4" />
        <span className="max-lg:sr-only">Suchen</span>
        <kbd className="ml-auto font-mono text-[0.6875rem] text-ink-tertiary max-lg:hidden">{keys}</kbd>
      </button>
      {open ? <FindDialog role={role} onDone={() => setOpen(false)} /> : null}
    </Root>
  );
}

function FindDialog({ role, onDone }: { role: StaffRole; onDone: () => void }) {
  const router = useRouter();
  const id = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const typed = useDeferredValue(query.trim());
  const office = OFFICE_ROLES.has(role);
  const searching = typed.length >= 2;

  const orders = useQuery({
    queryKey: ["admin", "quick-find", "orders", typed],
    queryFn: ({ signal }) => listOrders({ q: typed, limit: LIMIT }, { signal }),
    enabled: searching,
    staleTime: 10_000,
  });
  const models = useQuery({
    queryKey: ["admin", "quick-find", "models", typed],
    queryFn: ({ signal }) => listProducts({ q: typed, limit: LIMIT }, { signal }),
    enabled: searching && office && !looksLikeOrderNumber(typed),
    staleTime: 10_000,
  });

  const pageHits: Hit[] = findShortcuts(query, role).map((entry) => ({
    key: `page:${entry.href}`,
    group: "Seiten",
    label: entry.label,
    hint: entry.hint,
    href: entry.href,
  }));
  const orderHits: Hit[] = searching
    ? (orders.data?.items ?? []).map((order) => ({
        key: `order:${order.id}`,
        group: "Bestellungen",
        label: `${order.number} · ${order.recipient}`,
        hint: `${ORDER_STATUS_LABELS[order.status]} · ${formatPrice(order.total_cents)} · ${order.first_line_title}`,
        href: `/admin/bestellungen/${order.id}` as Route,
      }))
    : [];
  const modelHits: Hit[] = searching
    ? (models.data?.items ?? []).map((model) => ({
        key: `model:${model.id}`,
        group: "Modelle",
        label: model.name,
        hint: [model.scale_codes.join(", "), model.price_from_cents !== null ? `ab ${formatPrice(model.price_from_cents)}` : null].filter(Boolean).join(" · "),
        href: `/admin/modelle/${model.id}` as Route,
      }))
    : [];
  const hits = looksLikeOrderNumber(typed) ? [...orderHits, ...pageHits] : [...pageHits, ...orderHits, ...modelHits];
  const current = Math.min(active, Math.max(hits.length - 1, 0));
  const loading = searching && (orders.isFetching || models.isFetching);

  function go(hit: Hit | undefined) {
    if (!hit) {
      return;
    }
    onDone();
    router.push(hit.href);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current + step + hits.length) % Math.max(hits.length, 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(hits[current]);
    }
  }

  const groups = [...new Set(hits.map((hit) => hit.group))];
  return (
    <Portal>
      <Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-[2px]" />
      <Content
        aria-describedby={undefined}
        className="fixed top-[12dvh] left-1/2 z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 animate-feed-in border border-line bg-surface text-ink shadow-overlay"
      >
        <Title className="sr-only">Schnellsuche</Title>
        <div className="flex items-center gap-3 border-b border-line px-4">
          <SearchGlyph className="size-5 shrink-0 text-ink-secondary" />
          <input
            // Radix focuses the first focusable element: this field.
            role="combobox"
            aria-expanded={hits.length > 0}
            aria-controls={`${id}-list`}
            aria-activedescendant={hits[current] ? `${id}-${current}` : undefined}
            aria-autocomplete="list"
            aria-label="Suchen"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
            placeholder={office ? "Bestellnummer, Kunde, Modell oder Seite …" : "Bestellnummer, Kunde oder Seite …"}
            className="h-14 min-w-0 flex-1 bg-transparent text-body-lg outline-none placeholder:text-ink-tertiary"
            autoComplete="off"
            spellCheck={false}
          />
          {loading ? <span aria-hidden="true" className="size-2 animate-lamp-pulse rounded-full bg-accent" /> : null}
          <kbd className="font-mono text-[0.6875rem] text-ink-tertiary max-sm:hidden">Esc</kbd>
        </div>
        <ul id={`${id}-list`} role="listbox" aria-label="Treffer" className="max-h-[min(60dvh,28rem)] overflow-y-auto py-2">
          {groups.map((group) => (
            <li key={group} role="presentation">
              <p className="px-4 pt-3 pb-1 label-caps text-ink-tertiary">{group}</p>
              <ul role="presentation">
                {hits.map((hit, index) =>
                  hit.group === group ? (
                    // The keys are the search field's (combobox): arrows choose, Enter opens.
                    // eslint-disable-next-line jsx-a11y/click-events-have-key-events
                    <li
                      key={hit.key}
                      id={`${id}-${index}`}
                      role="option"
                      aria-selected={index === current}
                      onMouseMove={() => setActive(index)}
                      onClick={() => go(hit)}
                      className={cn(
                        "mx-2 flex cursor-pointer items-center gap-3 border-l-2 px-3 py-2",
                        index === current ? "border-accent bg-accent-subtle" : "border-transparent",
                      )}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{hit.label}</span>
                        <span className="block truncate text-hint text-ink-tertiary">{hit.hint}</span>
                      </span>
                      {index === current ? (
                        <kbd aria-hidden="true" className="font-mono text-[0.6875rem] text-ink-secondary">
                          ↵
                        </kbd>
                      ) : null}
                    </li>
                  ) : null,
                )}
              </ul>
            </li>
          ))}
          {hits.length === 0 ? (
            <li role="presentation" className="px-4 py-6 text-center text-small text-ink-secondary">
              {loading ? "Sucht …" : `Nichts gefunden für „${typed}“.`}
            </li>
          ) : null}
        </ul>
        <p className="flex gap-4 border-t border-line px-4 py-2 font-mono text-[0.6875rem] text-ink-tertiary max-sm:hidden">
          <span>↑↓ wählen</span>
          <span>↵ öffnen</span>
          <span>Esc schließen</span>
        </p>
      </Content>
    </Portal>
  );
}

function SearchGlyph({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className={className}>
      <circle cx="8.5" cy="8.5" r="5.5" />
      <path d="m12.5 12.5 4.5 4.5" strokeLinecap="square" />
    </svg>
  );
}
