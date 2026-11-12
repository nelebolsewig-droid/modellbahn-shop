"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogTitle, DialogTrigger, SheetContent } from "@/components/ui/dialog";
import type { StaffRole } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

import { activeSection, barSections, headerSections, moreSections, section, type Section, type SectionKey } from "./sections";

type NavProps = { role: StaffRole; pathname: string };

/**
 * The entries in the header on a desk, only those the role can use. The quick capture
 * has no entry of its own there (it is a button in the catalogue), so it lights up Katalog.
 */
export function HeaderNav({ role, pathname }: NavProps) {
  const active = activeSection(pathname);
  const current = active === "newModel" ? "catalog" : active;
  return (
    <nav aria-label="Stellwerk" className="max-sm:hidden sm:flex-1">
      <ul className="flex flex-wrap gap-1">
        {headerSections(role).map((entry) => (
          <li key={entry.key}>
            <Link
              href={entry.href}
              aria-current={entry.key === current ? "page" : undefined}
              className={cn(
                "inline-flex h-9 items-center rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors",
                entry.key === current ? "bg-selected text-on-selected" : "text-ink-secondary hover:bg-sunken hover:text-ink",
              )}
            >
              {entry.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** Scannen beside the account actions on a desk; on the phone it sits in the bottom bar. */
export function ScanButton({ pathname }: { pathname: string }) {
  const scan = section("scan");
  return (
    <Button asChild size="sm" className="max-sm:hidden">
      <Link href={scan.href} aria-current={activeSection(pathname) === "scan" ? "page" : undefined}>
        <Glyph name="scan" className="size-4" />
        {scan.label}
      </Link>
    </Button>
  );
}

/**
 * The phone's navigation: a bar at the bottom edge, within reach of the thumb, with
 * Scannen in the middle. What does not fit waits behind "Mehr"; when only one entry is
 * left (a packer's Fertigung), it takes that place itself.
 */
export function PhoneBar({ role, pathname }: NavProps) {
  const active = activeSection(pathname);
  const more = moreSections(role);
  const [single] = more;
  return (
    <nav
      aria-label="Stellwerk"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 pr-[env(safe-area-inset-right)] pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)] backdrop-blur sm:hidden"
    >
      <ul className="grid h-16 grid-cols-5">
        {barSections(role).map((entry) => (
          <li key={entry.key} className="min-w-0">
            {entry.key === "scan" ? (
              <ScanTab entry={entry} current={active === "scan"} />
            ) : (
              <Tab entry={entry} current={active === entry.key} />
            )}
          </li>
        ))}
        {single !== undefined && more.length === 1 ? (
          <li className="min-w-0">
            <Tab entry={single} current={active === single.key} />
          </li>
        ) : more.length > 1 ? (
          <li className="min-w-0">
            <MoreTab entries={more} active={active} />
          </li>
        ) : null}
      </ul>
    </nav>
  );
}

const TAB_CLASSES =
  "relative flex h-full w-full cursor-pointer flex-col items-center justify-center gap-1 px-1 text-[0.6875rem] leading-none font-medium transition-colors";

function Tab({ entry, current }: { entry: Section; current: boolean }) {
  return (
    <Link
      href={entry.href}
      aria-current={current ? "page" : undefined}
      className={cn(TAB_CLASSES, current ? "text-ink" : "text-ink-secondary hover:text-ink")}
    >
      <Marker shown={current} />
      <Glyph name={entry.key} />
      <span className="max-w-full truncate">{entry.label}</span>
    </Link>
  );
}

function ScanTab({ entry, current }: { entry: Section; current: boolean }) {
  return (
    <Link
      href={entry.href}
      aria-current={current ? "page" : undefined}
      className={cn(TAB_CLASSES, "gap-0.5 text-ink")}
    >
      <span
        className={cn(
          "grid size-10 place-items-center rounded-full bg-selected text-on-selected",
          current && "ring-4 ring-accent-subtle",
        )}
      >
        <Glyph name="scan" />
      </span>
      <span className="max-w-full truncate">{entry.label}</span>
    </Link>
  );
}

function MoreTab({ entries, active }: { entries: readonly Section[]; active: SectionKey | null }) {
  const inside = entries.some((entry) => entry.key === active);
  return (
    <Dialog>
      <DialogTrigger className={cn(TAB_CLASSES, inside ? "text-ink" : "text-ink-secondary hover:text-ink")}>
        <Marker shown={inside} />
        <Glyph name="more" />
        <span>Mehr</span>
      </DialogTrigger>
      <SheetContent aria-describedby={undefined}>
        <DialogTitle className="text-body font-medium tracking-normal">Mehr</DialogTitle>
        <ul className="mt-3 divide-y divide-line border-y border-line">
          {entries.map((entry) => (
            <li key={entry.key}>
              <DialogClose asChild>
                <Link
                  href={entry.href}
                  aria-current={entry.key === active ? "page" : undefined}
                  className={cn(
                    "flex h-13 items-center gap-3 text-body",
                    entry.key === active ? "font-medium text-ink" : "text-ink-secondary hover:text-ink",
                  )}
                >
                  <Glyph name={entry.key} />
                  {entry.label}
                </Link>
              </DialogClose>
            </li>
          ))}
        </ul>
      </SheetContent>
    </Dialog>
  );
}

/** The current tab's mark: a short bar on the top edge, like a lit section of track. */
function Marker({ shown }: { shown: boolean }) {
  return shown ? (
    <span aria-hidden="true" className="absolute inset-x-1/4 top-0 h-0.5 rounded-b-xs bg-selected" />
  ) : null;
}

/** Line drawings in the stroke of the blueprints, one per entry. */
const GLYPHS: Readonly<Record<SectionKey | "more", string>> = {
  overview: "M3.5 3.5h5v5h-5Z M11.5 3.5h5v5h-5Z M3.5 11.5h5v5h-5Z M11.5 11.5h5v5h-5Z",
  orders: "M3 6.5 10 3l7 3.5v7L10 17l-7-3.5Z M3 6.5l7 3.5 7-3.5 M10 10v7",
  stock: "M4 3v14 M16 3v14 M4 7h12 M4 11.5h12 M4 16h12",
  manufacturing: "M3.5 3.5h13v13h-13Z M3.5 6.5h13 M8 6.5v3h4v-3 M10 9.5v2 M6.5 16.5v-2.5h7v2.5",
  scan: "M3 7V3h4 M13 3h4v4 M17 13v4h-4 M7 17H3v-4 M6 10h8",
  catalog: "M4 3.5h12v13H4Z M7 7h6 M7 10h6 M7 13h3",
  newModel: "M10 4v12 M4 10h12",
  fairs: "M3.5 5.5h13v11h-13Z M3.5 9h13 M7 3.5v4 M13 3.5v4",
  ebay: "M4 7.5h12l-1 9H5Z M7.5 7.5V6a2.5 2.5 0 0 1 5 0v1.5",
  settings: "M4 6h12 M4 14h12 M7.5 4v4 M12.5 12v4",
  more: "M4.5 10h.01 M10 10h.01 M15.5 10h.01",
};

function Glyph({ name, className }: { name: SectionKey | "more"; className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={name === "more" ? 2.5 : 1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("size-5 shrink-0", className)}
    >
      <path d={GLYPHS[name]} />
    </svg>
  );
}
