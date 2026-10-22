import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const calloutVariants = cva("rule rounded-sm py-3 pr-4 pl-5 text-sm leading-6 text-ink", {
  variants: {
    tone: {
      info: "border-line-strong bg-surface-raised shadow-[inset_4px_0_0_0_var(--color-accent)]",
      success: "border-success bg-success-surface shadow-[inset_4px_0_0_0_var(--color-success)]",
      danger: "border-danger bg-danger-surface shadow-[inset_4px_0_0_0_var(--color-danger)]",
    },
  },
});

export type Tone = "info" | "success" | "danger";

type CalloutProps = {
  tone: Tone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
};

/** The look of a message box, without any live-region semantics. */
export function Callout({ tone, title, children, className }: CalloutProps) {
  return (
    <div className={cn(calloutVariants({ tone }), className)}>
      {title ? <p className="font-semibold">{title}</p> : null}
      {children ? <div className={cn(title ? "mt-1" : undefined, "space-y-2")}>{children}</div> : null}
    </div>
  );
}

/**
 * A message box that is announced when it appears: errors immediately (role
 * "alert"), everything else politely (role "status"). For messages that come and go
 * in the same place, use a permanent live region instead (see FormError).
 */
export function Alert(props: CalloutProps) {
  return (
    <div role={props.tone === "danger" ? "alert" : "status"}>
      <Callout {...props} />
    </div>
  );
}
