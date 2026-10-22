import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn(
        "rule block h-11 w-full min-w-0 rounded-sm border-line-strong bg-surface-raised px-3",
        "text-base text-ink placeholder:text-ink-muted",
        "aria-invalid:border-danger aria-invalid:shadow-[inset_3px_0_0_0_var(--color-danger)]",
        "disabled:cursor-not-allowed disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}
