import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

// Flat, tinted fields without borders; the title always says what happened, so the
// tint is never the only carrier of the message.
const calloutVariants = cva("rounded-md px-5 py-4 text-small text-ink", {
  variants: {
    tone: {
      info: "bg-accent-subtle",
      success: "bg-success-subtle",
      danger: "bg-danger-subtle",
    },
  },
});

const titleVariants = cva("font-medium", {
  variants: {
    tone: {
      info: "text-accent",
      success: "text-success",
      danger: "text-danger",
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
      {title ? <p className={titleVariants({ tone })}>{title}</p> : null}
      {children ? <div className={cn(title ? "mt-1.5" : undefined, "space-y-2")}>{children}</div> : null}
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
