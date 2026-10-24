import type { ComponentProps } from "react";

import { Button } from "@/components/ui/button";

type SubmitButtonProps = Omit<ComponentProps<typeof Button>, "type" | "asChild"> & {
  pending: boolean;
  /** Shown while the request is running. */
  pendingLabel?: string;
};

/** Submits its form; disabled while the request is running so it cannot be sent twice. */
export function SubmitButton({
  pending,
  pendingLabel = "Bitte warten …",
  children,
  disabled,
  ...props
}: SubmitButtonProps) {
  return (
    <Button type="submit" disabled={pending || disabled} aria-busy={pending || undefined} {...props}>
      {pending ? pendingLabel : children}
    </Button>
  );
}
