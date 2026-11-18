import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Wordmark } from "./wordmark";

describe("Wordmark", () => {
  it("sets the part before the hyphen in italic serif and the rest in bold sans", () => {
    render(<Wordmark name="adp-Modelle" />);
    const mark = screen.getByLabelText("adp-Modelle");
    const [head, rest] = [...mark.children];
    expect(head).toHaveTextContent("adp");
    expect(head).toHaveClass("italic", "lowercase", "text-wordmark");
    expect(rest).toHaveTextContent("-Modelle");
    expect(rest).not.toHaveClass("italic");
    expect(rest).not.toHaveClass("text-wordmark");
  });

  it("sets a name without a hyphen as one word", () => {
    render(<Wordmark name="Werkstatt" />);
    expect(screen.getByLabelText("Werkstatt").children).toHaveLength(1);
  });
});
