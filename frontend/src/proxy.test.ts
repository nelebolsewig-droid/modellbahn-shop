// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { config, proxy } from "./proxy";

function request(path: string, cookie?: string): NextRequest {
  return new NextRequest(`https://shop.example${path}`, cookie ? { headers: { cookie } } : undefined);
}

describe("proxy", () => {
  it("sends a visitor without a customer cookie to the shop login, with the way back", () => {
    const response = proxy(request("/konto?tab=1"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe(
      "https://shop.example/konto/anmelden?weiter=%2Fkonto%3Ftab%3D1",
    );
  });

  it("sends a visitor without a staff cookie to the admin login", () => {
    const response = proxy(request("/admin"));
    expect(response.headers.get("location")).toBe("https://shop.example/admin/anmelden?weiter=%2Fadmin");
  });

  it("lets a request with the matching cookie through", () => {
    expect(proxy(request("/konto", "mb_session=abc")).headers.get("x-middleware-next")).toBe("1");
    expect(proxy(request("/admin", "mb_admin=abc")).headers.get("x-middleware-next")).toBe("1");
  });

  it("does not accept the other area's cookie", () => {
    expect(proxy(request("/admin", "mb_session=abc")).status).toBe(307);
    expect(proxy(request("/konto", "mb_admin=abc")).status).toBe(307);
  });

  it("lets the public account pages through without a cookie", () => {
    expect(proxy(request("/konto/anmelden")).headers.get("x-middleware-next")).toBe("1");
    expect(proxy(request("/admin/anmelden")).headers.get("x-middleware-next")).toBe("1");
  });

  it("only runs for the account and admin areas", () => {
    expect(config.matcher).toEqual(["/konto/:path*", "/admin/:path*"]);
  });
});
