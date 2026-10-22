import { defineConfig, defineTransformer, type OpenApiPathItemObject } from "orval";

const OPERATION_KEYS = ["get", "put", "post", "delete", "options", "head", "patch", "trace"] as const;

function isEventStream(operation: unknown): boolean {
  return operation !== undefined && JSON.stringify(operation).includes('"text/event-stream"');
}

/**
 * Server-Sent Events endpoints are consumed with the browser's EventSource
 * (src/lib/realtime), not with fetch, so no hook is generated for them. Removing them
 * before validation also drops `itemSchema`, an OpenAPI 3.2 keyword that FastAPI emits
 * for SSE responses and that the 3.1 validator rejects. Their payload schema
 * (RealtimeEventData) stays in components and is generated as a type.
 */
const withoutEventStreams = defineTransformer((spec) => {
  const paths: Record<string, OpenApiPathItemObject> = {};
  for (const [path, item] of Object.entries(spec.paths ?? {})) {
    const kept: OpenApiPathItemObject = { ...item };
    for (const method of OPERATION_KEYS) {
      if (isEventStream(kept[method])) {
        delete kept[method];
      }
    }
    if (OPERATION_KEYS.some((method) => kept[method] !== undefined)) {
      paths[path] = kept;
    }
  }
  return { ...spec, paths };
});

/**
 * Generates the typed API client from the backend's OpenAPI document
 * (`make openapi` exports it). Regenerate with `npm run client`; CI fails when the
 * committed output under src/lib/api/generated differs from a fresh run.
 */
export default defineConfig({
  modellbahn: {
    input: {
      target: "./openapi.json",
      override: {
        transformer: withoutEventStreams,
      },
    },
    output: {
      mode: "tags-split",
      target: "./src/lib/api/generated/endpoints.ts",
      schemas: "./src/lib/api/generated/model",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      override: {
        mutator: {
          path: "./src/lib/api/fetcher.ts",
          name: "apiFetch",
        },
        fetch: {
          // Errors are thrown as ApiProblem by the fetcher, so a hook's data is the
          // success body itself rather than a { status, data, headers } envelope.
          includeHttpResponseReturnType: false,
        },
        query: {
          signal: true,
        },
      },
    },
  },
});
