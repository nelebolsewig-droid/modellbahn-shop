import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { renderWithQueryClient } from "@/test/render";

import { LabelPictures } from "./label-pictures";

const fetchMock = vi.fn<typeof fetch>();
const LABELS = "POST /api/v1/admin/inventory/labels";

function picture(type = "image/png"): Response {
  return new Response("bytes", {
    status: 200,
    headers: { "Content-Type": type },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  let next = 0;
  vi.stubGlobal(
    "URL",
    Object.assign(URL, {
      createObjectURL: () => `blob:${++next}`,
      revokeObjectURL: vi.fn(),
    }),
  );
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("LabelPictures", () => {
  it("makes one picture per label for the Brother app, and all of them as ZIP", async () => {
    routeFetch(fetchMock, {
      [LABELS]: ({ body }) => {
        const codes = body as {
          unit_codes: string[];
          location_codes: string[];
        };
        return codes.unit_codes.length + codes.location_codes.length > 1
          ? picture("application/zip")
          : picture();
      },
    });
    const user = userEvent.setup();
    renderWithQueryClient(
      <LabelPictures
        unitCodes={["J4WZXRT2S2", "7KQ2X9F4MZ"]}
        locationCodes={["R01-F02"]}
        partNumbers={[]}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Als Bilder für die Brother-App" }),
    );

    const shown = await screen.findByRole("region", {
      name: "Etiketten als Bilder",
    });
    expect(
      within(shown)
        .getAllByRole("img")
        .map((img) => img.getAttribute("alt")),
    ).toEqual(["Etikett J4WZXRT2S2", "Etikett 7KQ2X9F4MZ", "Etikett R01-F02"]);
    expect(
      within(shown).getAllByRole("link", { name: "Speichern" })[0],
    ).toHaveAttribute("download", "etikett-J4WZXRT2S2.png");
    expect(
      within(shown).getByRole("link", { name: "Alle Bilder als ZIP" }),
    ).toHaveAttribute("download", "etiketten.zip");
    const sent = requestsTo(fetchMock, LABELS).map((request) => request.body);
    expect(sent[0]).toEqual({
      sheet: "ql_62x29",
      format: "png",
      unit_codes: ["J4WZXRT2S2"],
      location_codes: [],
      part_numbers: [],
    });
    expect(sent).toHaveLength(4);
  });

  it("brings a single label without a ZIP", async () => {
    routeFetch(fetchMock, { [LABELS]: () => picture() });
    const user = userEvent.setup();
    renderWithQueryClient(
      <LabelPictures
        unitCodes={["J4WZXRT2S2"]}
        locationCodes={[]}
        partNumbers={[]}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: "Als Bilder für die Brother-App" }),
    );

    expect(
      await screen.findByRole("img", { name: "Etikett J4WZXRT2S2" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Alle Bilder als ZIP" }),
    ).toBeNull();
    expect(requestsTo(fetchMock, LABELS)).toHaveLength(1);
  });
});
