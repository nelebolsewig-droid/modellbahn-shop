import { z } from "zod";

/*
 * Client-side mirror of the backend's input rules (backend/src/modellbahn/modules/
 * identity: api/schemas.py and domain/model.py). The backend stays authoritative;
 * these give immediate feedback in German. Field names are the API's snake_case
 * names, so that 422 field errors map onto the form directly.
 */

export const PASSWORD_MIN_LENGTH = 10;
const PASSWORD_MAX_LENGTH = 256;
const DISPLAY_NAME_MAX_LENGTH = 80;

// Like Python's len(): code points, not UTF-16 units (an emoji counts once).
const codePoints = (value: string): number => Array.from(value).length;

// C0/C1 control characters and the bidi overrides the backend rejects in names.
const FORBIDDEN_NAME_CHARACTERS = /[\p{Cc}\u202A-\u202E\u2066-\u2069]/u;

const email = z
  .string()
  .trim()
  .min(1, "Bitte gib deine E-Mail-Adresse ein.")
  .pipe(z.email("Bitte gib eine gültige E-Mail-Adresse ein."));

// An empty field gets only "please enter", hence `value === ""` in the length rule.
// (No `abort: true` here: zod would then skip the form-level rule below entirely.)
const newPassword = z
  .string()
  .min(1, "Bitte gib ein Passwort ein.")
  .refine((value) => value === "" || codePoints(value) >= PASSWORD_MIN_LENGTH, {
    error: `Das Passwort muss mindestens ${PASSWORD_MIN_LENGTH} Zeichen lang sein.`,
  })
  .refine((value) => codePoints(value) <= PASSWORD_MAX_LENGTH, {
    error: `Das Passwort darf höchstens ${PASSWORD_MAX_LENGTH} Zeichen lang sein.`,
  });

/** An existing password: only bounded, never checked against the policy again. */
const currentPassword = z
  .string()
  .min(1, "Bitte gib dein Passwort ein.")
  .refine((value) => codePoints(value) <= PASSWORD_MAX_LENGTH, {
    error: `Das Passwort darf höchstens ${PASSWORD_MAX_LENGTH} Zeichen lang sein.`,
  });

const displayName = z
  .string()
  .transform((value) => value.split(/\s+/u).filter(Boolean).join(" "))
  .pipe(
    z
      .string()
      .min(1, "Bitte gib einen Namen ein.")
      .refine((value) => codePoints(value) <= DISPLAY_NAME_MAX_LENGTH, {
        error: `Der Name darf höchstens ${DISPLAY_NAME_MAX_LENGTH} Zeichen lang sein.`,
      })
      .refine((value) => !FORBIDDEN_NAME_CHARACTERS.test(value), {
        error: "Der Name enthält unzulässige Zeichen.",
      }),
  );

const PASSWORD_EQUALS_EMAIL = "Das Passwort darf nicht deine E-Mail-Adresse sein.";

const differsFromEmail = (password: string, address: string): boolean =>
  password.toLocaleLowerCase("de") !== address.toLocaleLowerCase("de");

const registrationFields = z.object({ display_name: displayName, email, password: newPassword });
const credentialFields = registrationFields.pick({ email: true, password: true });

export const registrationSchema = registrationFields.refine(
  (value) => differsFromEmail(value.password, value.email),
  {
    path: ["password"],
    error: PASSWORD_EQUALS_EMAIL,
    // Checked as soon as address and password are valid themselves, even while the
    // name is still missing, so that one submission shows every problem.
    when: (payload) => credentialFields.safeParse(payload.value).success,
  },
);

export const loginSchema = z.object({ email, password: currentPassword });

/** Resend verification mail, request password reset. */
export const emailSchema = z.object({ email });

export const passwordResetSchema = z.object({ new_password: newPassword });

export const passwordChangeSchema = z.object({
  current_password: currentPassword,
  new_password: newPassword,
});

export const displayNameSchema = z.object({ display_name: displayName });

export const accountDeletionSchema = z.object({ password: currentPassword });

export type LoginValues = z.output<typeof loginSchema>;
export type EmailValues = z.output<typeof emailSchema>;
export type PasswordChangeValues = z.output<typeof passwordChangeSchema>;
