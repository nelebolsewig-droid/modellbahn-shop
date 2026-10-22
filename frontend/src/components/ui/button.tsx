import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-sm whitespace-nowrap",
    "font-display font-semibold tracking-display uppercase",
    "transition-[background-color,border-color,color,box-shadow] duration-150",
    "disabled:cursor-not-allowed disabled:opacity-55 aria-busy:cursor-progress",
  ],
  {
    variants: {
      variant: {
        primary:
          "rule border-primary bg-primary text-primary-ink shadow-[inset_0_-3px_0_0_var(--color-accent)] hover:shadow-[inset_0_-5px_0_0_var(--color-accent)]",
        secondary:
          "rule border-line-strong bg-transparent text-ink hover:bg-surface-sunken",
        danger: "rule border-danger bg-danger text-danger-ink hover:brightness-110",
        ghost: "text-ink underline-offset-4 hover:bg-surface-sunken hover:underline",
      },
      size: {
        md: "h-11 px-5 text-lg",
        sm: "h-9 px-3 text-base",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    /** Renders the only child (e.g. a next/link) with the button's styles. */
    asChild?: boolean;
  };

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Component = asChild ? Slot : "button";
  return <Component className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
