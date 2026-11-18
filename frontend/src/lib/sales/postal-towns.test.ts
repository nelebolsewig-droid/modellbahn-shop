import { afterEach, describe, expect, it, vi } from "vitest";

import { clearPostalTowns, townsFor } from "@/lib/sales/postal-towns";

const chunk = { "01067": ["Dresden"], "01945": ["Tettau", "Guteborn"] };

function loader(ok = true) {
  return vi.fn(async () => new Response(JSON.stringify(chunk), { status: ok ? 200 : 404 }));
}

describe("townsFor", () => {
  afterEach(clearPostalTowns);

  it("finds the town of a German postal code in the file of its first two digits", async () => {
    const load = loader();
    expect(await townsFor("01067", load)).toEqual(["Dresden"]);
    expect(load).toHaveBeenCalledWith("/plz/01.json");
  });

  it("loads each file once", async () => {
    const load = loader();
    await townsFor("01067", load);
    expect(await townsFor("01945", load)).toEqual(["Tettau", "Guteborn"]);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("suggests nothing for an incomplete or unknown code", async () => {
    const load = loader();
    expect(await townsFor("0106", load)).toEqual([]);
    expect(await townsFor("01099", load)).toEqual([]);
  });

  it("tries again after a failed download", async () => {
    const failing = vi.fn(async () => {
      throw new TypeError("offline");
    });
    expect(await townsFor("01067", failing)).toEqual([]);
    expect(await townsFor("01067", loader())).toEqual(["Dresden"]);
  });
});
