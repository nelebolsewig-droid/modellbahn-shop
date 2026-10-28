import { describe, expect, it, vi } from "vitest";

import type { ScanIn } from "@/lib/api/generated/model";

import { flushQueue, MemoryScanStore } from "./scan-queue";

function scan(id: string): ScanIn {
  return { scan_id: id, raw: "R01-F01", mode: "lookup", source: "scanner", context: {} };
}

const OFFLINE = new Error("offline");

describe("flushQueue", () => {
  it("sends the waiting scans oldest first with their own ids", async () => {
    const store = new MemoryScanStore();
    await store.add({ scan: scan("b"), queuedAt: 2 });
    await store.add({ scan: scan("a"), queuedAt: 1 });
    const send = vi.fn().mockResolvedValue(undefined);
    expect(await flushQueue(store, send, () => false)).toBe(2);
    expect(send.mock.calls.map(([sent]) => (sent as ScanIn).scan_id)).toEqual(["a", "b"]);
    expect(await store.all()).toEqual([]);
  });

  it("stops while the connection is still down and keeps the rest", async () => {
    const store = new MemoryScanStore();
    await store.add({ scan: scan("a"), queuedAt: 1 });
    await store.add({ scan: scan("b"), queuedAt: 2 });
    const send = vi.fn().mockRejectedValue(OFFLINE);
    expect(await flushQueue(store, send, (error) => error === OFFLINE)).toBe(0);
    expect((await store.all()).map((item) => item.scan.scan_id)).toEqual(["a", "b"]);
  });

  it("drops a scan the server refuses, so it does not block the others", async () => {
    const store = new MemoryScanStore();
    await store.add({ scan: scan("a"), queuedAt: 1 });
    await store.add({ scan: scan("b"), queuedAt: 2 });
    const send = vi.fn().mockRejectedValueOnce(new Error("refused")).mockResolvedValueOnce(undefined);
    expect(await flushQueue(store, send, (error) => error === OFFLINE)).toBe(2);
    expect(await store.all()).toEqual([]);
  });
});
