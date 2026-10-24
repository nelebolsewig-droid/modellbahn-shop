import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/** The browser's own select, in the look of Input: reliable on phones and with keyboards. */
export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "block h-12 w-full min-w-0 cursor-pointer appearance-none rounded-sm border border-line-control bg-surface",
        "bg-[length:12px] bg-[right_1rem_center] bg-no-repeat pr-10 pl-4 text-base text-ink",
        // A thin chevron, drawn in the ink colour.
        "bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 12 8%22><path d=%22M1 1l5 5 5-5%22 fill=%22none%22 stroke=%22%231e2124%22 stroke-width=%221.2%22/></svg>')]",
        "transition-colors hover:border-ink-secondary aria-invalid:border-danger",
        "disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-disabled",
        "werkstatt:h-10 werkstatt:text-[0.9375rem]",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
