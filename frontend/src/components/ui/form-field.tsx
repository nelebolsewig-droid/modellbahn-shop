import { useId, type ReactNode } from "react";

import { cn } from "@/lib/utils";

import { Label } from "./label";

/** Attributes that tie a control to its label, hint and error message. */
export type FieldControlProps = {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
};

type FormFieldProps = {
  label: ReactNode;
  hint?: ReactNode;
  error?: string | undefined;
  className?: string;
  /** Renders the control; spread the given props onto it. */
  children: (control: FieldControlProps) => ReactNode;
};

/**
 * Label, control, hint and error message of one form field.
 *
 * The error paragraph is always in the DOM and a polite live region, so that screen
 * readers announce a message as soon as it appears; the control references it via
 * aria-describedby only while there is one.
 */
export function FormField({ label, hint, error, className, children }: FormFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : undefined, error ? errorId : undefined]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children({
        id,
        ...(describedBy && { "aria-describedby": describedBy }),
        ...(error && { "aria-invalid": true }),
      })}
      {hint ? (
        <p id={hintId} className="text-sm text-ink-muted">
          {hint}
        </p>
      ) : null}
      <p id={errorId} aria-live="polite" className="text-sm font-medium text-danger empty:hidden">
        {error}
      </p>
    </div>
  );
}
