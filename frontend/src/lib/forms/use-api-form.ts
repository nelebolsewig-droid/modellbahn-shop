"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  useForm,
  type DefaultValues,
  type FieldPath,
  type FieldValues,
  type UseFormReturn,
} from "react-hook-form";
import type { BaseSyntheticEvent } from "react";
import type { z } from "zod";

import { applyProblemToForm, FORM_ERROR_KEY, type ProblemMapping } from "./apply-problem";

type ApiFormOptions<TInput extends FieldValues, TOutput extends FieldValues> = {
  schema: z.ZodType<TOutput, TInput>;
  /** Every field of the form; their names are the API's field names. */
  defaultValues: DefaultValues<TInput> & TInput;
  codeFields?: ProblemMapping<TInput>["codeFields"];
  /** Sends the validated values; a thrown ApiProblem is shown in the form. */
  submit: (values: TOutput) => Promise<void>;
};

type ApiForm<TInput extends FieldValues, TOutput extends FieldValues> = {
  form: UseFormReturn<TInput, unknown, TOutput>;
  onSubmit: (event?: BaseSyntheticEvent) => Promise<void>;
  /** The German message for the form as a whole, and its problem code. */
  formError: { message: string; code: string } | undefined;
};

/**
 * A react-hook-form form validated by a zod schema (German messages, checked when a
 * field is left and then on every change) whose submission goes to the API.
 * Server-side failures land at the matching field or above the form.
 */
export function useApiForm<TInput extends FieldValues, TOutput extends FieldValues>({
  schema,
  defaultValues,
  codeFields,
  submit,
}: ApiFormOptions<TInput, TOutput>): ApiForm<TInput, TOutput> {
  const form = useForm<TInput, unknown, TOutput>({
    resolver: zodResolver(schema),
    defaultValues,
    mode: "onTouched",
  });
  const fields = Object.keys(defaultValues) as FieldPath<TInput>[];

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await submit(values);
    } catch (error) {
      applyProblemToForm(error, form.setError, { fields, codeFields });
    }
  });

  const rootError = form.formState.errors.root?.[FORM_ERROR_KEY];
  const formError =
    rootError?.message === undefined
      ? undefined
      : { message: rootError.message, code: String(rootError.type) };

  return { form, onSubmit, formError };
}
