import { describe, expect, it } from "vitest";

import { bookEntrySchema, checkoutSchema, EMPTY_ADDRESS } from "./checkout";

const ADDRESS = {
  recipient: "Erika  Mustermann ",
  street: "Bahnhofstraße 12",
  postal_code: "38707",
  city: "Altenau",
  country_code: "DE" as const,
};

function messages(result: { success: boolean; error?: { issues: { path: PropertyKey[]; message: string }[] } }) {
  return Object.fromEntries((result.error?.issues ?? []).map((issue) => [String(issue.path[0]), issue.message]));
}

describe("checkoutSchema", () => {
  it("asks a guest for e-mail address and every address field", () => {
    const result = checkoutSchema({ email: true, address: true }).safeParse({
      email: "",
      ...EMPTY_ADDRESS,
      save_address: false,
    });
    expect(Object.keys(messages(result)).sort()).toEqual(["city", "email", "postal_code", "recipient", "street"]);
  });

  it("checks the postal code of the chosen country", () => {
    const schema = checkoutSchema({ email: false, address: true });
    const austria = { email: "", ...ADDRESS, country_code: "AT" as const, save_address: false };
    expect(messages(schema.safeParse(austria)).postal_code).toBe("Bitte gib eine vierstellige Postleitzahl ein.");
    expect(schema.safeParse({ ...austria, postal_code: "6020" }).success).toBe(true);
  });

  it("collapses the whitespace the API would collapse too", () => {
    const result = checkoutSchema({ email: true, address: true }).safeParse({
      email: " erika@example.de ",
      ...ADDRESS,
      save_address: true,
    });
    expect(result.success && result.data).toMatchObject({ email: "erika@example.de", recipient: "Erika Mustermann" });
  });

  it("needs nothing typed for a logged-in customer with an entry of the address book", () => {
    const result = checkoutSchema({ email: false, address: false }).safeParse({
      email: "",
      ...EMPTY_ADDRESS,
      save_address: true,
    });
    expect(result.success).toBe(true);
  });
});

describe("bookEntrySchema", () => {
  it("limits the label and keeps the default flag", () => {
    const entry = { label: "W".repeat(41), ...ADDRESS, is_default: true };
    expect(messages(bookEntrySchema.safeParse(entry)).label).toBe("Bitte höchstens 40 Zeichen.");
    expect(bookEntrySchema.safeParse({ ...entry, label: "Werkstatt" }).data?.is_default).toBe(true);
  });
});

describe("EU addresses", () => {
  it("takes a Dutch postal code as people write it and stores it upper case", () => {
    const schema = checkoutSchema({ email: false, address: true });
    const result = schema.safeParse({
      email: "",
      ...ADDRESS,
      postal_code: " 1012  ab ",
      country_code: "NL",
      save_address: false,
    });
    expect(result.success && result.data.postal_code).toBe("1012 AB");
  });

  it("names an example of the country's postal codes", () => {
    const schema = checkoutSchema({ email: false, address: true });
    const result = schema.safeParse({ email: "", ...ADDRESS, postal_code: "1234", country_code: "PL", save_address: false });
    expect(messages(result).postal_code).toBe("Bitte gib eine Postleitzahl aus Polen ein, z. B. 00-950.");
  });
});
