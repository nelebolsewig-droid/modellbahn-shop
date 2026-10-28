/*
 * Scans that could not reach the server wait here and are sent again, oldest first,
 * with their original scan id: the server recognises a repeat and books nothing twice.
 * The queue lives in IndexedDB, so it survives reloading the page in a dead spot of the
 * workshop's Wi-Fi; where IndexedDB is missing it falls back to memory.
 */

import type { ScanIn } from "@/lib/api/generated/model";
import { ApiProblem, CLIENT_PROBLEM_CODES } from "@/lib/api/problem";

const DATABASE = "mb-scanner";
const STORE = "pending-scans";

export type QueuedScan = { scan: ScanIn; queuedAt: number };

/** Where waiting scans are kept; the browser's IndexedDB or, in tests, memory. */
export interface ScanStore {
  add(item: QueuedScan): Promise<void>;
  all(): Promise<QueuedScan[]>;
  remove(scanId: string): Promise<void>;
}

export class MemoryScanStore implements ScanStore {
  private readonly items = new Map<string, QueuedScan>();

  async add(item: QueuedScan): Promise<void> {
    this.items.set(item.scan.scan_id, item);
  }

  async all(): Promise<QueuedScan[]> {
    return [...this.items.values()].sort((a, b) => a.queuedAt - b.queuedAt);
  }

  async remove(scanId: string): Promise<void> {
    this.items.delete(scanId);
  }
}

function request<T>(open: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(open.error ?? new Error("IndexedDB request failed"));
  });
}

export class IndexedDbScanStore implements ScanStore {
  private database: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    this.database ??= new Promise((resolve, reject) => {
      const opening = indexedDB.open(DATABASE, 1);
      opening.onupgradeneeded = () => {
        opening.result.createObjectStore(STORE, { keyPath: "scan.scan_id" });
      };
      opening.onsuccess = () => resolve(opening.result);
      opening.onerror = () => reject(opening.error ?? new Error("IndexedDB unavailable"));
    });
    return this.database;
  }

  private async store(mode: IDBTransactionMode): Promise<IDBObjectStore> {
    return (await this.open()).transaction(STORE, mode).objectStore(STORE);
  }

  async add(item: QueuedScan): Promise<void> {
    await request((await this.store("readwrite")).put(item));
  }

  async all(): Promise<QueuedScan[]> {
    const items = await request((await this.store("readonly")).getAll() as IDBRequest<QueuedScan[]>);
    return items.sort((a, b) => a.queuedAt - b.queuedAt);
  }

  async remove(scanId: string): Promise<void> {
    await request((await this.store("readwrite")).delete(scanId));
  }
}

export function browserScanStore(): ScanStore {
  return typeof indexedDB === "undefined" ? new MemoryScanStore() : new IndexedDbScanStore();
}

/**
 * Sends every waiting scan once, oldest first, and stops at the first one that still
 * cannot get through. Returns how many went out.
 */
export async function flushQueue(
  store: ScanStore,
  send: (scan: ScanIn) => Promise<unknown>,
  isOffline: (error: unknown) => boolean,
): Promise<number> {
  let sent = 0;
  for (const item of await store.all()) {
    try {
      await send(item.scan);
    } catch (error) {
      if (isOffline(error)) {
        break;
      }
      // Refused for good (e.g. the order was cancelled): it must not block the rest.
    }
    await store.remove(item.scan.scan_id);
    sent += 1;
  }
  return sent;
}

/** True if the scan never reached the API (offline, or the API restarting): queue it. */
export function isUnreachable(error: unknown): boolean {
  return (
    error instanceof ApiProblem &&
    (error.code === CLIENT_PROBLEM_CODES.networkError || error.code === CLIENT_PROBLEM_CODES.serviceUnavailable)
  );
}
