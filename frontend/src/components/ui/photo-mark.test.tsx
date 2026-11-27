import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PhotoMark, finishName } from "./photo-mark";

describe("PhotoMark", () => {
  it("names both finishes when a model comes as kit and finished model", () => {
    render(<PhotoMark finishes={["unpainted", "painted"].map(finishName)} />);
    expect(screen.getByLabelText("adp-Modelle")).toBeInTheDocument();
    expect(screen.getByText("Bausatz · Fertigmodell")).toBeInTheDocument();
  });

  it("shows only the wordmark without a finish", () => {
    const { container } = render(<PhotoMark finishes={[]} />);
    expect(container.textContent).toBe("adp-Modelle");
  });
});
