import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-full whitespace-nowrap",
    "font-medium transition-[background-color,border-color,color] duration-150 ease-out",
    "disabled:cursor-not-allowed aria-busy:cursor-progress",
  ],
  {
    variants: {
      variant: {
        // Matte black; one per area ("In den Warenkorb", "Speichern").
        primary: "bg-selected text-on-selected hover:bg-ink-secondary disabled:bg-sunken disabled:text-ink-disabled",
        // The second action next to it, with a visible border (3:1).
        secondary:
          "border border-line-control bg-transparent text-ink hover:border-ink disabled:border-line disabled:text-ink-disabled",
        danger: "bg-danger text-on-selected hover:bg-ink disabled:bg-sunken disabled:text-ink-disabled",
        // Quiet actions inside a page, in the accent colour.
        ghost: "text-accent hover:bg-accent-subtle hover:text-accent-hover disabled:text-ink-disabled",
      },
      size: {
        md: "h-12 px-6 text-[0.9375rem] werkstatt:h-10 werkstatt:px-5 werkstatt:text-sm",
        sm: "h-10 px-5 text-sm werkstatt:h-9 werkstatt:px-4",
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
