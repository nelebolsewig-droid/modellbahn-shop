import { describe, expect, it } from "vitest";

import { cn } from "./utils";

describe("cn", () => {
  it("keeps a size of the type scale next to a colour", () => {
    expect(cn("text-hint font-medium", "text-success")).toBe("text-hint font-medium text-success");
  });

  it("lets a later size of the type scale win", () => {
    expect(cn("text-hint", "text-small")).toBe("text-small");
    expect(cn("text-ink-secondary", "text-accent")).toBe("text-accent");
  });
});
