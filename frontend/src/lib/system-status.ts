import { isApiProblem } from "@/lib/api/problem";

export type ComponentStatus = "up" | "down" | "unknown";

export type SystemStatus = {
  api: ComponentStatus;
  database: ComponentStatus;
};

type ReadinessCheck = {
  /** Status of the latest /readyz request (TanStack Query's `status`). */
  status: "pending" | "success" | "error";
  error: unknown;
};

/**
 * Reads API and database health from the latest /readyz answer. A 503 problem from
 * the API itself means the API runs but its database does not answer; anything else
 * that fails (no connection, 502/504 from the proxy) means the API is unreachable,
 * so nothing is known about the database.
 */
export function systemStatusFrom({ status, error }: ReadinessCheck): SystemStatus {
  if (status === "success") {
    return { api: "up", database: "up" };
  }
  if (status === "pending") {
    return { api: "unknown", database: "unknown" };
  }
  if (isApiProblem(error) && error.code === "database_unavailable") {
    return { api: "up", database: "down" };
  }
  return { api: "down", database: "unknown" };
}
