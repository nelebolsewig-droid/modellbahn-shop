import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, problemResponse } from "@/test/render";

import { apiFetch, CLIENT_HEADER } from "./fetcher";
import { ApiProblem, isSessionMissing } from "./problem";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

function lastRequest(): { url: string; init: RequestInit; headers: Headers } {
  const [url, init = {}] = fetchMock.mock.lastCall ?? [];
  return { url: String(url), init, headers: new Headers(init.headers) };
}

describe("apiFetch request", () => {
  it.each(["POST", "PUT", "PATCH", "DELETE", "post"])(
    "sends the CSRF header on unsafe method %s",
    async (method) => {
      fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
      await apiFetch("/api/v1/store/account/session", { method });
      expect(lastRequest().headers.get(CLIENT_HEADER)).toBe("web");
      expect(lastRequest().init.method).toBe(method.toUpperCase());
    },
  );

  it.each(["GET", "HEAD", "OPTIONS"])("does not send it on safe method %s", async (method) => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    await apiFetch("/api/v1/store/account/me", { method });
    expect(lastRequest().headers.has(CLIENT_HEADER)).toBe(false);
  });

  it("keeps the URL relative and always sends cookies", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "ok" }));
    await apiFetch("/api/v1/store/account/me");
    expect(lastRequest().url).toBe("/api/v1/store/account/me");
    expect(lastRequest().init.credentials).toBe("include");
    expect(lastRequest().headers.get("Accept")).toBe("application/json, application/problem+json");
  });

  it("keeps the caller's headers and body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "pending_verification" }, 202));
    const body = JSON.stringify({ email: "erika@example.de" });
    await apiFetch("/api/v1/store/account/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    expect(lastRequest().headers.get("Content-Type")).toBe("application/json");
    expect(lastRequest().init.body).toBe(body);
  });
});

describe("apiFetch response", () => {
  it("returns the parsed JSON body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "pending_verification" }, 202));
    await expect(apiFetch("/x", { method: "POST" })).resolves.toEqual({
      status: "pending_verification",
    });
  });

  it("returns undefined for an empty body (204)", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiFetch("/x", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("throws a typed ApiProblem parsed from an RFC 9457 body", async () => {
    fetchMock.mockResolvedValue(
      problemResponse(422, "validation_failed", [
        { field: "password", code: "too_short", message: "String should have at least 10 characters" },
      ]),
    );
    const error = await apiFetch("/x", { method: "POST" }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiProblem);
    expect(error).toMatchObject({
      status: 422,
      code: "validation_failed",
      type: "/problems/validation-failed",
      fieldErrors: [{ field: "password", code: "too_short" }],
    });
  });

  it("recognises a lost session by its code, not by the status alone", async () => {
    fetchMock.mockResolvedValueOnce(problemResponse(401, "not_authenticated"));
    const lost = await apiFetch("/me").catch((caught: unknown) => caught);
    fetchMock.mockResolvedValueOnce(problemResponse(401, "invalid_credentials"));
    const failedLogin = await apiFetch("/session", { method: "POST" }).catch((caught: unknown) => caught);
    expect(isSessionMissing(lost)).toBe(true);
    expect(isSessionMissing(failedLogin)).toBe(false);
  });

  it.each([
    [502, "service_unavailable"],
    [503, "service_unavailable"],
    [504, "service_unavailable"],
    [500, "internal_error"],
    [404, "unexpected_response"],
  ])("assigns a code when status %i comes without a problem body", async (status, code) => {
    fetchMock.mockResolvedValue(new Response("<html>Bad Gateway</html>", { status }));
    await expect(apiFetch("/x")).rejects.toMatchObject({ status, code });
  });

  it("reports a network failure as network_error", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(apiFetch("/x")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("passes an abort through unchanged, so a cancelled query is not an error", async () => {
    const controller = new AbortController();
    controller.abort();
    const abort = new DOMException("The operation was aborted.", "AbortError");
    fetchMock.mockRejectedValue(abort);
    await expect(apiFetch("/x", { signal: controller.signal })).rejects.toBe(abort);
  });

  it("reports a success body that is not JSON as unexpected_response", async () => {
    fetchMock.mockResolvedValue(new Response("not json", { status: 200 }));
    await expect(apiFetch("/x")).rejects.toMatchObject({ status: 200, code: "unexpected_response" });
  });
});
