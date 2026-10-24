import type { ReactNode } from "react";

import { Callout } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

type FormErrorProps = {
  /** The German message; nothing is shown while undefined. */
  message: string | undefined;
  /** A way out that fits the error, e.g. a link to request a new e-mail. */
  children?: ReactNode;
  className?: string;
};

/**
 * The error of a form as a whole, above its fields. The live region stays in the
 * DOM while it is empty, so that every new message is announced right away; it only
 * takes up space while it shows something.
 */
export function FormError({ message, children, className }: FormErrorProps) {
  return (
    <div role="alert" aria-atomic="true" className={cn("not-empty:mb-6", className)}>
      {message ? (
        <Callout tone="danger">
          <p>{message}</p>
          {children}
        </Callout>
      ) : null}
    </div>
  );
}
