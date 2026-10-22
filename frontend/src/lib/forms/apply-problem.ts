import type { FieldPath, FieldValues, UseFormSetError } from "react-hook-form";

import { isApiProblem } from "@/lib/api/problem";
import { errorMessage, fieldErrorMessage, problemMessage } from "@/lib/i18n/problems";

/** Where a form shows errors that belong to no single field: `errors.root.server`. */
export const FORM_ERROR_KEY = "server";
export const FORM_ERROR = `root.${FORM_ERROR_KEY}` as const;

/** `type` of the form error when the failure was not an API problem at all. */
export const UNKNOWN_ERROR_TYPE = "unknown";

export type ProblemMapping<TValues extends FieldValues> = {
  /** The form's fields; they carry the API's (snake_case) names. */
  fields: readonly FieldPath<TValues>[];
  /**
   * Problem codes that are about one field, e.g. `invalid_password` → the field for
   * the current password. Their message is shown at that field.
   */
  codeFields?: Readonly<Partial<Record<string, FieldPath<TValues>>>>;
};

/**
 * Shows a failed submission in the form: a problem code that belongs to a field and
 * the field errors of a 422 problem at their fields, everything else as one German
 * message above the form. The form error's `type` is the problem code, so a form can
 * offer a matching way out (e.g. "request a new link" for `invalid_token`).
 */
export function applyProblemToForm<TValues extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<TValues>,
  { fields, codeFields = {} }: ProblemMapping<TValues>,
): void {
  if (!isApiProblem(error)) {
    setError(FORM_ERROR, { type: UNKNOWN_ERROR_TYPE, message: errorMessage(error) });
    return;
  }

  const codeField = Object.hasOwn(codeFields, error.code) ? codeFields[error.code] : undefined;
  if (codeField !== undefined) {
    setError(
      codeField,
      { type: error.code, message: problemMessage(error.code) },
      { shouldFocus: true },
    );
    return;
  }

  if (error.code === "validation_failed" && error.fieldErrors.length > 0) {
    const known = new Set<string>(fields);
    const assigned = error.fieldErrors.filter((fieldError) => known.has(fieldError.field));
    assigned.forEach((fieldError, index) => {
      setError(
        fieldError.field as FieldPath<TValues>,
        { type: fieldError.code, message: fieldErrorMessage(fieldError.field, fieldError.code) },
        { shouldFocus: index === 0 },
      );
    });
    if (assigned.length === error.fieldErrors.length) {
      return;
    }
  }

  setError(FORM_ERROR, { type: error.code, message: problemMessage(error.code) });
}
