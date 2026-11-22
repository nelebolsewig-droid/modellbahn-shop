import { describe, expect, it } from "vitest";

import type { FairImageOut } from "@/lib/api/generated/model";
import { fairImagePending, fairPicture } from "@/lib/site/fair-image";

const READY: FairImageOut = {
  asset_id: "a",
  ready: true,
  failed: false,
  width: 1200,
  height: 800,
  dominant_color: null,
  lqip: "data:image/webp;base64,AA",
  renditions: [{ name: "md", format: "webp", width: 960, height: 640, url: "/medien/a/md.webp" }],
};

describe("fair photo", () => {
  it("shows a ready photo, on the card colour until it has loaded", () => {
    expect(fairPicture(READY)?.dominant_color).toBe("#efe7dc");
    expect(fairImagePending(READY)).toBe(false);
  });

  it("waits while the worker prepares it, and gives up on a failed one", () => {
    const pending = { ...READY, ready: false, renditions: [], width: null };
    expect(fairPicture(pending)).toBeNull();
    expect(fairImagePending(pending)).toBe(true);
    expect(fairImagePending({ ...pending, failed: true })).toBe(false);
    expect(fairPicture(null)).toBeNull();
  });
});
