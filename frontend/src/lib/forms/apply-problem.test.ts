import { describe, expect, it, vi } from "vitest";

import { ApiProblem } from "@/lib/api/problem";

import { applyProblemToForm, FORM_ERROR, UNKNOWN_ERROR_TYPE } from "./apply-problem";

type Values = { current_password: string; new_password: string };

function problem(
  status: number,
  code: string,
  errors?: { field: string; code: string; message: string }[],
): ApiProblem {
  return new ApiProblem({ type: "/problems/x", title: "t", status, detail: "d", code, errors });
}

function apply(error: unknown) {
  const setError = vi.fn();
  applyProblemToForm<Values>(error, setError, {
    fields: ["current_password", "new_password"],
    codeFields: { invalid_password: "current_password" },
  });
  return setError.mock.calls;
}

describe("applyProblemToForm", () => {
  it("puts field errors of a 422 at their fields, focusing the first", () => {
    const calls = apply(
      problem(422, "validation_failed", [
        { field: "new_password", code: "equals_email", message: "…" },
      ]),
    );
    expect(calls).toEqual([
      [
        "new_password",
        { type: "equals_email", message: "Das Passwort darf nicht deine E-Mail-Adresse sein." },
        { shouldFocus: true },
      ],
    ]);
  });

  it("adds a form error when some field errors belong to no field of the form", () => {
    const calls = apply(
      problem(422, "validation_failed", [
        { field: "new_password", code: "too_short", message: "…" },
        { field: "body", code: "invalid_json", message: "…" },
      ]),
    );
    expect(calls.map(([field]) => field)).toEqual(["new_password", FORM_ERROR]);
    expect(calls[1]?.[1]).toEqual({ type: "validation_failed", message: "Bitte prüfe deine Eingaben." });
  });

  it("shows a problem code that belongs to a field at that field", () => {
    expect(apply(problem(400, "invalid_password"))).toEqual([
      [
        "current_password",
        { type: "invalid_password", message: "Das Passwort ist nicht richtig." },
        { shouldFocus: true },
      ],
    ]);
  });

  it("shows other problems above the form, typed by their code", () => {
    expect(apply(problem(403, "csrf_header_missing"))).toEqual([
      [FORM_ERROR, { type: "csrf_header_missing", message: expect.stringContaining("Sicherheitsgründen") }],
    ]);
  });

  it("shows unexpected failures with the fallback text", () => {
    expect(apply(new Error("boom"))).toEqual([
      [FORM_ERROR, { type: UNKNOWN_ERROR_TYPE, message: expect.stringContaining("nicht geklappt") }],
    ]);
  });
});
