import type { FieldPath, FieldValues, UseFormSetError } from "react-hook-form";

import { isApiProblem } from "@/lib/api/problem";
import { errorMessage, fieldErrorMessage } from "@/lib/i18n/problems";

/** Where a form shows errors that belong to no single field. */
export const FORM_ERROR = "root.server";

/**
 * Shows a failed submission in the form: field errors of a 422 problem at their
 * fields (the form's field names are the API's), everything else as one German
 * message above the form.
 */
export function applyProblemToForm<TValues extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<TValues>,
  fields: readonly FieldPath<TValues>[],
): void {
  if (isApiProblem(error) && error.code === "validation_failed" && error.fieldErrors.length > 0) {
    const known = new Set<string>(fields);
    const unassigned = error.fieldErrors.filter((fieldError) => !known.has(fieldError.field));
    error.fieldErrors
      .filter((fieldError) => known.has(fieldError.field))
      .forEach((fieldError, index) => {
        setError(
          fieldError.field as FieldPath<TValues>,
          { type: "server", message: fieldErrorMessage(fieldError.field, fieldError.code) },
          { shouldFocus: index === 0 },
        );
      });
    if (unassigned.length === 0) {
      return;
    }
  }
  setError(FORM_ERROR, { type: "server", message: errorMessage(error) });
}
