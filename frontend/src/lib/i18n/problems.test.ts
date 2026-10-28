// @vitest-environment node
import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { ApiProblem, CLIENT_PROBLEM_CODES } from "@/lib/api/problem";

import {
  errorMessage,
  FALLBACK_PROBLEM_MESSAGE,
  FIELD_MESSAGES,
  fieldErrorMessage,
  PROBLEM_MESSAGES,
  problemMessage,
} from "./problems";

/** Every problem code the OpenAPI document lists ("Problem codes: `a`, `b`."). */
function documentedProblemCodes(): string[] {
  const openapi = readFileSync(new URL("../../../openapi.json", import.meta.url), "utf8");
  const codes = new Set<string>();
  for (const [, list] of openapi.matchAll(/Problem codes: ([^."]+)\./g)) {
    for (const [, code] of (list ?? "").matchAll(/`([a-z_]+)`/g)) {
      codes.add(code ?? "");
    }
  }
  return [...codes].sort();
}

function problem(code: string, status = 400): ApiProblem {
  return new ApiProblem({
    type: `/problems/${code}`,
    title: "Forbidden",
    status,
    detail: "The e-mail address has not been verified yet.",
    code,
  });
}

describe("problem messages", () => {
  it("has a German text for every problem code in openapi.json", () => {
    const documented = documentedProblemCodes();
    expect(documented.length).toBeGreaterThan(5);
    const missing = documented.filter((code) => !Object.hasOwn(PROBLEM_MESSAGES, code));
    expect(missing).toEqual([]);
  });

  it("covers the codes the backend raises outside the documented routes", () => {
    // Defaults of the AppError classes and codes FastAPI's HTTPException produces.
    for (const code of [
      "bad_request",
      "forbidden",
      "not_found",
      "method_not_allowed",
      "conflict",
      "service_unavailable",
      "internal_error",
      "database_unavailable",
    ]) {
      expect(PROBLEM_MESSAGES[code], code).toBeDefined();
    }
  });

  it("covers the codes the client assigns itself", () => {
    for (const code of Object.values(CLIENT_PROBLEM_CODES)) {
      expect(PROBLEM_MESSAGES[code], code).toBeDefined();
    }
  });

  it("translates known codes", () => {
    expect(problemMessage("invalid_credentials")).toBe("E-Mail-Adresse oder Passwort ist falsch.");
    expect(problemMessage("invalid_token")).toMatch(/Link ist ungültig/);
  });

  it("falls back for unknown codes, including prototype property names", () => {
    expect(problemMessage("brand_new_code")).toBe(FALLBACK_PROBLEM_MESSAGE);
    expect(problemMessage("constructor")).toBe(FALLBACK_PROBLEM_MESSAGE);
    expect(problemMessage("__proto__")).toBe(FALLBACK_PROBLEM_MESSAGE);
  });

  it("never shows the backend's English detail", () => {
    const error = problem("email_not_verified", 403);
    expect(errorMessage(error)).not.toContain(error.detail);
    expect(errorMessage(error)).toMatch(/bestätige zuerst deine E-Mail-Adresse/);
  });

  it("uses the fallback for anything that is not an ApiProblem", () => {
    expect(errorMessage(new TypeError("boom"))).toBe(FALLBACK_PROBLEM_MESSAGE);
    expect(errorMessage(undefined)).toBe(FALLBACK_PROBLEM_MESSAGE);
  });
});

describe("field messages", () => {
  it("has a German text for every field code the backend uses", () => {
    for (const code of [
      "required",
      "too_short",
      "too_long",
      "invalid_json",
      "unknown_field",
      "invalid_type",
      "invalid",
      "equals_email",
      "invalid_parent",
      "holds_no_goods",
    ]) {
      expect(FIELD_MESSAGES[code], code).toBeDefined();
    }
  });

  it("prefers a message for the specific field", () => {
    expect(fieldErrorMessage("password", "too_short")).toBe(
      "Das Passwort muss mindestens 10 Zeichen lang sein.",
    );
    expect(fieldErrorMessage("new_password", "equals_email")).toBe(
      "Das Passwort darf nicht deine E-Mail-Adresse sein.",
    );
    expect(fieldErrorMessage("email", "invalid")).toBe("Bitte gib eine gültige E-Mail-Adresse ein.");
    expect(fieldErrorMessage("display_name", "too_long")).toBe(
      "Der Name darf höchstens 80 Zeichen lang sein.",
    );
  });

  it("falls back to the generic message for the code, then to 'invalid'", () => {
    expect(fieldErrorMessage("current_password", "required")).toBe("Bitte fülle dieses Feld aus.");
    expect(fieldErrorMessage("email", "something_new")).toBe("Die Eingabe ist ungültig.");
    expect(fieldErrorMessage("toString", "constructor")).toBe("Die Eingabe ist ungültig.");
  });
});
