"use client";

import type { Route } from "next";
import Link from "next/link";

import type { LocationNodeOut } from "@/lib/api/generated/model";
import { LOCATION_KIND_LABELS, partCount } from "@/lib/inventory/labels";
import { cn } from "@/lib/utils";

import { LocationGlyph } from "./location-glyph";

/** Places as a tree: shelves, Böden and boxes, with what lies in them. */
export function LocationTree({ items, className }: { items: readonly LocationNodeOut[]; className?: string }) {
  const base = Math.min(...items.map((item) => item.depth));
  return (
    <ul className={cn("-mx-2", className)}>
      {items.map((item) => {
        const level = item.depth - base;
        return (
          <li key={item.id}>
            <Link
              href={`/admin/lager/plaetze/${item.code}` as Route}
              className="group flex items-center gap-2.5 rounded-sm px-2 py-1.5 hover:bg-sunken"
            >
              {Array.from({ length: level }, (_, index) => (
                <span key={index} aria-hidden="true" className="-my-1.5 h-8 w-3 shrink-0 border-l border-line" />
              ))}
              <LocationGlyph kind={item.kind} className={item.holds_goods ? "text-ink" : "text-ink-tertiary"} />
              <span className="min-w-0 flex-1 truncate">
                <span className="font-mono text-small font-medium group-hover:underline">{item.code}</span>
                <span className="ml-2 text-hint text-ink-tertiary">{item.name || LOCATION_KIND_LABELS[item.kind]}</span>
              </span>
              {item.part_count > 0 ? (
                <span className="rounded-full border border-accent/40 px-2 py-0.5 text-hint whitespace-nowrap tabular-nums text-accent">
                  {partCount(item.part_count)}
                </span>
              ) : null}
              {item.total_count > 0 ? (
                <span className="rounded-full bg-sunken px-2 py-0.5 text-hint font-medium tabular-nums text-ink-secondary">
                  {item.total_count}
                </span>
              ) : null}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
