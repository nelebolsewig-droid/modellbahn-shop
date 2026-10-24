import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn(
        "block h-12 w-full min-w-0 rounded-sm border border-line-control bg-surface px-4",
        "text-base text-ink transition-colors placeholder:text-ink-tertiary hover:border-ink-secondary",
        "aria-invalid:border-danger aria-invalid:shadow-[inset_0_0_0_1px_var(--danger)]",
        "disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-disabled",
        "werkstatt:h-10 werkstatt:text-[0.9375rem]",
        className,
      )}
      {...props}
    />
  );
}
