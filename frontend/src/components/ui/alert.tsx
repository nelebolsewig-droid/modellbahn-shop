import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const alertVariants = cva("rule rounded-sm px-4 py-3 text-sm leading-6 text-ink", {
  variants: {
    tone: {
      info: "border-line-strong bg-surface-raised shadow-[inset_4px_0_0_0_var(--color-accent)]",
      success: "border-success bg-success-surface shadow-[inset_4px_0_0_0_var(--color-success)]",
      danger: "border-danger bg-danger-surface shadow-[inset_4px_0_0_0_var(--color-danger)]",
    },
  },
});

type AlertProps = {
  tone: "info" | "success" | "danger";
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
};

/**
 * A message box. Errors are announced immediately (role "alert"), everything else
 * politely (role "status").
 */
export function Alert({ tone, title, children, className }: AlertProps) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={cn(alertVariants({ tone }), "pl-5", className)}
    >
      {title ? <p className="font-semibold">{title}</p> : null}
      {children ? <div className={cn(title ? "mt-1" : undefined)}>{children}</div> : null}
    </div>
  );
}
