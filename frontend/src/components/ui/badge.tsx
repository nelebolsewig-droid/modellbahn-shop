import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "label-caps rule inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral: "border-line-strong text-ink",
        success: "border-success text-success",
        warning: "border-accent text-accent-text",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

type BadgeProps = ComponentProps<"span"> & VariantProps<typeof badgeVariants>;

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
