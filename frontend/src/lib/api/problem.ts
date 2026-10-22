import { z } from "zod";

/**
 * Problem codes the frontend assigns itself when there is no usable problem body:
 * the request never reached the API, or something other than the API answered
 * (e.g. Caddy with a 502 while the API restarts).
 */
export const CLIENT_PROBLEM_CODES = {
  networkError: "network_error",
  unexpectedResponse: "unexpected_response",
  serviceUnavailable: "service_unavailable",
  internalError: "internal_error",
} as const;

const fieldErrorSchema = z.object({
  field: z.string(),
  code: z.string(),
  message: z.string(),
});

/** RFC 9457 body as the backend sends it (see backend/src/modellbahn/platform/errors.py). */
const problemBodySchema = z.object({
  type: z.string(),
  title: z.string(),
  status: z.number().int(),
  detail: z.string(),
  code: z.string().min(1),
  errors: z.array(fieldErrorSchema).optional(),
});

export type ProblemFieldError = z.infer<typeof fieldErrorSchema>;
type ProblemBody = z.infer<typeof problemBodySchema>;

/**
 * A failed API call. `code` is the stable, machine-readable part that
 * `src/lib/i18n/problems.ts` translates; `title` and `detail` are the backend's
 * English texts and are never shown to users.
 */
export class ApiProblem extends Error {
  override readonly name = "ApiProblem";
  readonly status: number;
  readonly code: string;
  readonly type: string;
  readonly title: string;
  readonly detail: string;
  readonly fieldErrors: readonly ProblemFieldError[];

  constructor(body: ProblemBody, options?: { cause?: unknown }) {
    super(`${body.status} ${body.code}: ${body.detail}`, options);
    this.status = body.status;
    this.code = body.code;
    this.type = body.type;
    this.title = body.title;
    this.detail = body.detail;
    this.fieldErrors = body.errors ?? [];
  }

  /** Builds the problem from a non-2xx response, with or without a problem body. */
  static async fromResponse(response: Response): Promise<ApiProblem> {
    const body = await readJson(response);
    const parsed = problemBodySchema.safeParse(body);
    if (parsed.success) {
      return new ApiProblem(parsed.data);
    }
    const code =
      response.status === 502 || response.status === 503 || response.status === 504
        ? CLIENT_PROBLEM_CODES.serviceUnavailable
        : response.status >= 500
          ? CLIENT_PROBLEM_CODES.internalError
          : CLIENT_PROBLEM_CODES.unexpectedResponse;
    return new ApiProblem({
      type: "about:blank",
      title: response.statusText || "Unexpected response",
      status: response.status,
      detail: `The server answered ${response.status} without a problem body.`,
      code,
    });
  }

  /** The request did not reach the server (offline, DNS, connection refused). */
  static network(cause: unknown): ApiProblem {
    return new ApiProblem(
      {
        type: "about:blank",
        title: "Network error",
        status: 0,
        detail: "The request did not reach the server.",
        code: CLIENT_PROBLEM_CODES.networkError,
      },
      { cause },
    );
  }

  /** A response the client cannot interpret, e.g. a 200 with a body that is not JSON. */
  static malformed(response: Response, cause: unknown): ApiProblem {
    return new ApiProblem(
      {
        type: "about:blank",
        title: "Malformed response",
        status: response.status,
        detail: "The response body could not be read as JSON.",
        code: CLIENT_PROBLEM_CODES.unexpectedResponse,
      },
      { cause },
    );
  }
}

export function isApiProblem(error: unknown): error is ApiProblem {
  return error instanceof ApiProblem;
}

/** True for "no valid session": the caller should treat the visitor as logged out. */
export function isUnauthenticated(error: unknown): boolean {
  return isApiProblem(error) && error.status === 401;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}
