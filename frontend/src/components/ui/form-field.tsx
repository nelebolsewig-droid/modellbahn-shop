import { useId, type ReactNode } from "react";

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
 * The error paragraph is always rendered (empty when there is no error) and is a
 * polite live region, so screen readers announce a message as soon as it appears.
 * It is never display:none: some screen readers ignore live regions that were not
 * in the accessibility tree before. The control references it only while it has
 * content.
 */
export function FormField({ label, hint, error, className, children }: FormFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : undefined, error ? errorId : undefined]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={className}>
      <Label htmlFor={id}>{label}</Label>
      <div className="mt-1.5">
        {children({
          id,
          ...(describedBy && { "aria-describedby": describedBy }),
          ...(error && { "aria-invalid": true }),
        })}
      </div>
      {hint ? (
        <p id={hintId} className="mt-1.5 text-hint text-ink-tertiary">
          {hint}
        </p>
      ) : null}
      <p
        id={errorId}
        aria-live="polite"
        className="text-hint font-medium text-danger not-empty:mt-1.5"
      >
        {error}
      </p>
    </div>
  );
}
