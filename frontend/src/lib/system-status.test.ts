import { describe, expect, it } from "vitest";

import { ApiProblem } from "@/lib/api/problem";

import { systemStatusFrom } from "./system-status";

function problem(status: number, code: string): ApiProblem {
  return new ApiProblem({ type: "t", title: "t", status, detail: "d", code });
}

describe("systemStatusFrom", () => {
  it("knows nothing before the first answer", () => {
    expect(systemStatusFrom({ status: "pending", error: null })).toEqual({
      api: "unknown",
      database: "unknown",
    });
  });

  it("reports both up when /readyz answers 200", () => {
    expect(systemStatusFrom({ status: "success", error: null })).toEqual({ api: "up", database: "up" });
  });

  it("tells a database outage from an API outage", () => {
    expect(systemStatusFrom({ status: "error", error: problem(503, "database_unavailable") })).toEqual({
      api: "up",
      database: "down",
    });
    expect(systemStatusFrom({ status: "error", error: problem(502, "service_unavailable") })).toEqual({
      api: "down",
      database: "unknown",
    });
    expect(systemStatusFrom({ status: "error", error: problem(0, "network_error") })).toEqual({
      api: "down",
      database: "unknown",
    });
  });
});
