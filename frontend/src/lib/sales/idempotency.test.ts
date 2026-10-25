import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useIdempotencyKeys } from "./idempotency";

describe("useIdempotencyKeys", () => {
  it("reuses the key while the same request is retried", () => {
    const { result } = renderHook(() => useIdempotencyKeys());
    const first = result.current.keyFor({ method: "succeeds" });
    expect(first).toMatch(/^[0-9a-f-]{36}$/);
    expect(result.current.keyFor({ method: "succeeds" })).toBe(first);
  });

  it("gives a changed request a new key", () => {
    const { result } = renderHook(() => useIdempotencyKeys());
    const first = result.current.keyFor({ method: "succeeds" });
    expect(result.current.keyFor({ method: "declined" })).not.toBe(first);
  });

  it("starts over after a request has settled", () => {
    const { result } = renderHook(() => useIdempotencyKeys());
    const first = result.current.keyFor({ method: "declined" });
    result.current.settle();
    expect(result.current.keyFor({ method: "declined" })).not.toBe(first);
  });
});
