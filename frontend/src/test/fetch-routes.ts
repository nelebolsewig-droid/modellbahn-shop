import type { Mock } from "vitest";

/** What a route sees of a request: the parsed JSON body and the headers. */
export type RouteRequest = { body: unknown; headers: Headers };
export type RouteHandler = (request: RouteRequest) => Response | Promise<Response>;

/**
 * Answers `fetch` by "METHOD /path" (query strings ignored); any other request fails
 * the test. Handlers return a new Response each time, since a body is read only once.
 */
export function routeFetch(fetchMock: Mock<typeof fetch>, routes: Readonly<Record<string, RouteHandler>>): void {
  fetchMock.mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const key = `${method} ${new URL(url, "http://shop.test").pathname}`;
    const handler = routes[key];
    if (handler === undefined) {
      throw new Error(`unexpected request: ${key}`);
    }
    const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    return handler({ body, headers: new Headers(init?.headers) });
  });
}

/** The requests sent to "METHOD /path", in order. */
export function requestsTo(fetchMock: Mock<typeof fetch>, key: string): RouteRequest[] {
  return fetchMock.mock.calls
    .filter(([input, init]) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      return `${(init?.method ?? "GET").toUpperCase()} ${new URL(url, "http://shop.test").pathname}` === key;
    })
    .map(([, init]) => ({
      body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined,
      headers: new Headers(init?.headers),
    }));
}
