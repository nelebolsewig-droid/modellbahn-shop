"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const SECTIONS = [
  { href: "/konto", label: "Übersicht", exact: true },
  { href: "/konto/bestellungen", label: "Bestellungen", exact: false },
  { href: "/konto/adressen", label: "Adressen", exact: true },
] as const satisfies readonly { href: Route; label: string; exact: boolean }[];

/** The sections of "Mein Konto" as tabs on a hairline, the current one underlined in ink. */
export function AccountNav({ className }: { className?: string }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Mein Konto" className={cn("border-b border-line", className)}>
      <ul className="-mb-px flex gap-8 overflow-x-auto">
        {SECTIONS.map((section) => {
          const active = section.exact ? pathname === section.href : pathname.startsWith(section.href);
          return (
            <li key={section.href}>
              <Link
                href={section.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex h-12 items-center border-b-2 text-[0.9375rem] font-medium whitespace-nowrap transition-colors",
                  active ? "border-selected text-ink" : "border-transparent text-ink-secondary hover:border-line-strong hover:text-ink",
                )}
              >
                {section.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
