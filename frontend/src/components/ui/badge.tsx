import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-hint font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "border border-line text-ink-secondary",
        success: "bg-success-subtle text-success",
        warning: "bg-warning-subtle text-warning",
        accent: "bg-accent-subtle text-accent",
        highlight: "bg-highlight-subtle text-highlight-ink",
        sea: "bg-sea-subtle text-sea",
        plum: "bg-plum-subtle text-plum",
        rose: "bg-rose-subtle text-rose",
        sky: "bg-sky-subtle text-sky",
        sun: "bg-sun text-ink",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

type BadgeProps = ComponentProps<"span"> & VariantProps<typeof badgeVariants>;

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
