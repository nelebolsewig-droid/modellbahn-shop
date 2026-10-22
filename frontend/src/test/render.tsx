import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";

/** A query client like the app's, but without retries, so failures surface at once. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

export function renderWithQueryClient(
  ui: ReactElement,
  queryClient: QueryClient = createTestQueryClient(),
): RenderResult & { queryClient: QueryClient } {
  return {
    queryClient,
    ...render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>),
  };
}

/** A fetch Response with a JSON body. */
export function jsonResponse(
  body: unknown,
  status = 200,
  contentType = "application/json",
): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": contentType } });
}

/** An RFC 9457 problem response as the backend sends it. */
export function problemResponse(
  status: number,
  code: string,
  errors?: { field: string; code: string; message: string }[],
): Response {
  return jsonResponse(
    {
      type: `/problems/${code.replaceAll("_", "-")}`,
      title: "Problem",
      status,
      detail: "English detail that is never shown.",
      code,
      ...(errors && { errors }),
    },
    status,
    "application/problem+json",
  );
}
