import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiProblem } from "@/lib/api/problem";
import { createQueryClient } from "@/lib/query-client";
import { createTestQueryClient, jsonResponse, problemResponse } from "@/test/render";

import { customerSessionQueryKey, useCustomerSession, useCustomerSessionCache } from "./customer";
import { accountOrNull } from "./session";

const ACCOUNT = {
  id: "0192f1c4-7a3e-7cc2-9d5e-1b2c3d4e5f60",
  email: "erika@example.de",
  display_name: "Erika Mustermann",
  email_verified: true,
  created_at: "2026-10-22T08:00:00Z",
};

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

function wrapperFor(queryClient = createTestQueryClient()) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("accountOrNull", () => {
  it("turns a missing session into null", async () => {
    const lost = new ApiProblem({ type: "t", title: "t", status: 401, detail: "d", code: "not_authenticated" });
    await expect(accountOrNull(Promise.reject(lost))).resolves.toBeNull();
  });

  it("passes other failures on", async () => {
    const down = new ApiProblem({ type: "t", title: "t", status: 503, detail: "d", code: "service_unavailable" });
    await expect(accountOrNull(Promise.reject(down))).rejects.toBe(down);
  });
});

describe("useCustomerSession", () => {
  it("is authenticated when /me answers with the account", async () => {
    fetchMock.mockResolvedValue(jsonResponse(ACCOUNT));
    const { result } = renderHook(() => useCustomerSession(), { wrapper: wrapperFor() });
    expect(result.current).toEqual({ status: "loading" });
    await waitFor(() => expect(result.current).toEqual({ status: "authenticated", account: ACCOUNT }));
    expect(String(fetchMock.mock.lastCall?.[0])).toBe("/api/v1/store/account/me");
  });

  it("is anonymous on a 401 — the cookie alone proves nothing", async () => {
    fetchMock.mockResolvedValue(problemResponse(401, "not_authenticated"));
    const { result } = renderHook(() => useCustomerSession(), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current).toEqual({ status: "anonymous" }));
  });

  it("reports other failures as errors", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 502 }));
    const { result } = renderHook(() => useCustomerSession(), { wrapper: wrapperFor() });
    await waitFor(() => expect(result.current.status).toBe("error"));
  });

  it("follows logins and logouts through the cache without asking the API", async () => {
    fetchMock.mockResolvedValue(problemResponse(401, "not_authenticated"));
    const { result } = renderHook(
      () => ({ session: useCustomerSession(), cache: useCustomerSessionCache() }),
      { wrapper: wrapperFor() },
    );
    await waitFor(() => expect(result.current.session.status).toBe("anonymous"));

    result.current.cache.store(ACCOUNT);
    await waitFor(() => expect(result.current.session).toEqual({ status: "authenticated", account: ACCOUNT }));
    result.current.cache.clear();
    await waitFor(() => expect(result.current.session).toEqual({ status: "anonymous" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("createQueryClient", () => {
  it("re-checks the sessions when a change fails because the session has ended", async () => {
    const queryClient = createQueryClient();
    fetchMock.mockResolvedValueOnce(jsonResponse(ACCOUNT));
    const { result } = renderHook(() => useCustomerSession(), { wrapper: wrapperFor(queryClient) });
    await waitFor(() => expect(result.current.status).toBe("authenticated"));

    fetchMock.mockResolvedValue(problemResponse(401, "not_authenticated"));
    const lost = new ApiProblem({ type: "t", title: "t", status: 401, detail: "d", code: "not_authenticated" });
    await queryClient
      .getMutationCache()
      .build(queryClient, { mutationFn: () => Promise.reject(lost) })
      .execute(undefined)
      .catch(() => undefined);

    await waitFor(() => expect(result.current).toEqual({ status: "anonymous" }));
    expect(queryClient.getQueryData(customerSessionQueryKey)).toBeNull();
  });

  it("does not retry client errors, but does retry server errors", () => {
    const retry = createQueryClient().getDefaultOptions().queries?.retry;
    expect(typeof retry).toBe("function");
    const shouldRetry = retry as (failureCount: number, error: unknown) => boolean;
    const problem = (status: number) =>
      new ApiProblem({ type: "t", title: "t", status, detail: "d", code: "x" });
    expect(shouldRetry(0, problem(404))).toBe(false);
    expect(shouldRetry(0, problem(503))).toBe(true);
    expect(shouldRetry(0, problem(0))).toBe(true);
    expect(shouldRetry(2, problem(503))).toBe(false);
  });
});
