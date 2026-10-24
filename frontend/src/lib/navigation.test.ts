import { describe, expect, it } from "vitest";

import { CUSTOMER_AREA, loginPath, safeReturnPath, STAFF_AREA } from "./navigation";
import { protectionFor } from "./route-protection";

describe("safeReturnPath", () => {
  it.each([
    ["/konto", "/konto"],
    ["/konto/", "/konto/"],
    ["/konto?tab=1", "/konto?tab=1"],
  ])("follows a path inside the area: %s", (value, expected) => {
    expect(safeReturnPath(value, CUSTOMER_AREA)).toBe(expected);
  });

  it.each([
    [null],
    [undefined],
    [""],
    ["https://evil.example/konto"],
    ["//evil.example/konto"],
    ["/\\evil.example"],
    ["konto"],
    ["/admin"],
    ["/kontox"],
    ["/konto/anmelden"],
    ["/konto/../admin"],
  ])("falls back to the area's home page for %s", (value) => {
    expect(safeReturnPath(value, CUSTOMER_AREA)).toBe("/konto");
  });

  it("keeps the staff area apart from the shop", () => {
    expect(safeReturnPath("/admin", STAFF_AREA)).toBe("/admin");
    expect(safeReturnPath("/konto", STAFF_AREA)).toBe("/admin");
  });
});

describe("loginPath", () => {
  it("remembers where the visitor wanted to go", () => {
    expect(loginPath(CUSTOMER_AREA, "/konto?x=1")).toBe("/konto/anmelden?weiter=%2Fkonto%3Fx%3D1");
    expect(loginPath(STAFF_AREA, "/admin")).toBe("/admin/anmelden?weiter=%2Fadmin");
  });
});

describe("protectionFor", () => {
  it.each(["/konto", "/konto/", "/konto/irgendwas"])("protects %s with the customer cookie", (path) => {
    expect(protectionFor(path)).toEqual({ cookie: "mb_session", area: CUSTOMER_AREA });
  });

  it.each(["/admin", "/admin/", "/admin/bestellungen"])("protects %s with the staff cookie", (path) => {
    expect(protectionFor(path)).toEqual({ cookie: "mb_admin", area: STAFF_AREA });
  });

  it.each([
    "/",
    "/impressum",
    "/konto/anmelden",
    "/konto/registrieren",
    "/konto/bestaetigen",
    "/konto/bestaetigung-erneut",
    "/konto/passwort-vergessen",
    "/konto/passwort-zuruecksetzen",
    "/konto/geloescht",
    "/konto/anmelden/",
    "/admin/anmelden",
    "/kontoauszug",
    "/administration",
  ])("leaves %s public", (path) => {
    expect(protectionFor(path)).toBeNull();
  });
});
