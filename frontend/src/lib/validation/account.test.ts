import { describe, expect, it } from "vitest";
import type { z } from "zod";

import {
  accountDeletionSchema,
  displayNameSchema,
  emailSchema,
  loginSchema,
  passwordChangeSchema,
  registrationSchema,
} from "./account";

/** The German messages zod reports, by field. */
function messages(schema: z.ZodType, input: unknown): Record<string, string[]> {
  const result = schema.safeParse(input);
  if (result.success) {
    return {};
  }
  const byField: Record<string, string[]> = {};
  for (const issue of result.error.issues) {
    const field = issue.path.join(".");
    (byField[field] ??= []).push(issue.message);
  }
  return byField;
}

const VALID_REGISTRATION = {
  display_name: "Erika Mustermann",
  email: "erika@example.de",
  password: "Rangierlok fährt um sechs",
};

describe("registrationSchema", () => {
  it("accepts valid input and normalises it like the backend", () => {
    const parsed = registrationSchema.parse({
      ...VALID_REGISTRATION,
      display_name: "  Erika \t Mustermann ",
      email: " erika@example.de ",
    });
    expect(parsed).toEqual({ ...VALID_REGISTRATION });
  });

  it("asks for every empty field in German", () => {
    expect(messages(registrationSchema, { display_name: "", email: "", password: "" })).toEqual({
      display_name: ["Bitte gib einen Namen ein."],
      email: ["Bitte gib deine E-Mail-Adresse ein."],
      password: ["Bitte gib ein Passwort ein."],
    });
  });

  it("treats a name of only spaces as empty", () => {
    expect(messages(registrationSchema, { ...VALID_REGISTRATION, display_name: "   " })).toEqual({
      display_name: ["Bitte gib einen Namen ein."],
    });
  });

  it("rejects an invalid e-mail address", () => {
    expect(messages(registrationSchema, { ...VALID_REGISTRATION, email: "erika@" })).toEqual({
      email: ["Bitte gib eine gültige E-Mail-Adresse ein."],
    });
  });

  it("enforces the password length in code points, like Python's len()", () => {
    expect(messages(registrationSchema, { ...VALID_REGISTRATION, password: "kurz" })).toEqual({
      password: ["Das Passwort muss mindestens 10 Zeichen lang sein."],
    });
    // Ten emoji are ten characters for the backend, although twenty UTF-16 units.
    expect(registrationSchema.safeParse({ ...VALID_REGISTRATION, password: "🚂".repeat(10) }).success).toBe(true);
    expect(registrationSchema.safeParse({ ...VALID_REGISTRATION, password: "🚂".repeat(9) }).success).toBe(false);
    expect(messages(registrationSchema, { ...VALID_REGISTRATION, password: "x".repeat(257) })).toEqual({
      password: ["Das Passwort darf höchstens 256 Zeichen lang sein."],
    });
  });

  it("rejects a password that equals the e-mail address, ignoring case", () => {
    expect(
      messages(registrationSchema, { ...VALID_REGISTRATION, password: "Erika@Example.de" }),
    ).toEqual({ password: ["Das Passwort darf nicht deine E-Mail-Adresse sein."] });
  });

  it("limits the name to 80 characters and rejects control and bidi characters", () => {
    expect(messages(registrationSchema, { ...VALID_REGISTRATION, display_name: "x".repeat(81) })).toEqual({
      display_name: ["Der Name darf höchstens 80 Zeichen lang sein."],
    });
    for (const sneaky of ["Erika\u0000", "Erika‮akire", "Erika⁦"]) {
      expect(messages(registrationSchema, { ...VALID_REGISTRATION, display_name: sneaky })).toEqual({
        display_name: ["Der Name enthält unzulässige Zeichen."],
      });
    }
  });
});

describe("loginSchema", () => {
  it("does not apply the password policy to an existing password", () => {
    expect(loginSchema.safeParse({ email: "erika@example.de", password: "alt" }).success).toBe(true);
  });

  it("asks for both fields", () => {
    expect(messages(loginSchema, { email: "", password: "" })).toEqual({
      email: ["Bitte gib deine E-Mail-Adresse ein."],
      password: ["Bitte gib dein Passwort ein."],
    });
  });
});

describe("other account schemas", () => {
  it("validates the e-mail request", () => {
    expect(emailSchema.parse({ email: " erika@example.de" })).toEqual({ email: "erika@example.de" });
  });

  it("applies the policy to the new password only", () => {
    expect(
      messages(passwordChangeSchema, { current_password: "alt", new_password: "neu" }),
    ).toEqual({ new_password: ["Das Passwort muss mindestens 10 Zeichen lang sein."] });
  });

  it("normalises the display name", () => {
    expect(displayNameSchema.parse({ display_name: " Erika  M. " })).toEqual({ display_name: "Erika M." });
  });

  it("requires the password to delete the account", () => {
    expect(messages(accountDeletionSchema, { password: "" })).toEqual({
      password: ["Bitte gib dein Passwort ein."],
    });
  });
});

describe("registrationSchema across fields", () => {
  it("reports password = e-mail together with a missing name", () => {
    expect(
      messages(registrationSchema, {
        display_name: "",
        email: "erika@example.de",
        password: "erika@example.de",
      }),
    ).toEqual({
      display_name: ["Bitte gib einen Namen ein."],
      password: ["Das Passwort darf nicht deine E-Mail-Adresse sein."],
    });
  });

  it("does not compare while the address itself is invalid", () => {
    expect(
      messages(registrationSchema, { ...VALID_REGISTRATION, email: "kein-at", password: "kein-at" }),
    ).toEqual({
      email: ["Bitte gib eine gültige E-Mail-Adresse ein."],
      password: ["Das Passwort muss mindestens 10 Zeichen lang sein."],
    });
  });
});
