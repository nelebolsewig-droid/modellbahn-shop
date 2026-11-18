import { describe, expect, it } from "vitest";

import { switchedMessage } from "./studio-for-all";

describe("switchedMessage", () => {
  it("says when nothing was left to switch", () => {
    expect(switchedMessage(0)).toBe("Alle Fotos stehen schon im Fotostudio.");
  });

  it("counts one photo and many", () => {
    expect(switchedMessage(1)).toBe("1 Foto wird jetzt neu gerechnet.");
    expect(switchedMessage(12)).toContain("12 Fotos werden jetzt neu gerechnet");
  });
});
