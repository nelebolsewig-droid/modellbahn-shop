"use client";

import { useCallback, useRef } from "react";

/**
 * Idempotency keys for one kind of request (checkout, payment): retrying the same
 * request reuses its key, so the backend answers with the first result instead of
 * ordering or charging twice; a changed request gets a new key, and so does the next
 * request after a success (``settle``).
 */
export function useIdempotencyKeys() {
  const current = useRef<{ key: string; request: string } | null>(null);

  const keyFor = useCallback((request: unknown): string => {
    const serialised = JSON.stringify(request);
    if (current.current?.request !== serialised) {
      current.current = { key: crypto.randomUUID(), request: serialised };
    }
    return current.current.key;
  }, []);

  const settle = useCallback(() => {
    current.current = null;
  }, []);

  return { keyFor, settle };
}

export const IDEMPOTENCY_HEADER = "Idempotency-Key";
