import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { InvoiceOut } from "@/lib/api/generated/model";

import { InvoiceDocuments } from "./invoice-documents";

const INVOICE: InvoiceOut = {
  id: "inv-1",
  kind: "invoice",
  number: "RE-2026-00001",
  issued_at: "2026-11-19T10:00:00Z",
  total_cents: 5580,
  filename: "Rechnung-RE-2026-00001.pdf",
};

const CORRECTION: InvoiceOut = {
  id: "inv-2",
  kind: "correction",
  number: "RK-2026-00001",
  issued_at: "2026-11-24T10:00:00Z",
  total_cents: -1190,
  filename: "Rechnungskorrektur-RK-2026-00001.pdf",
};

describe("InvoiceDocuments", () => {
  it("lists each document with its number, amount and the PDF to open or save", () => {
    render(<InvoiceDocuments invoices={[INVOICE, CORRECTION]} urlOf={(invoice) => `/pdf/${invoice.id}`} />);
    const [invoice, correction] = screen.getAllByRole("listitem");

    expect(invoice).toHaveTextContent("Rechnung");
    expect(invoice).toHaveTextContent("RE-2026-00001");
    expect(invoice).toHaveTextContent("55,80");
    expect(invoice).toHaveTextContent("19. November 2026");
    expect(within(invoice!).getByRole("link", { name: "Ansehen" })).toHaveAttribute("href", "/pdf/inv-1");
    expect(within(invoice!).getByRole("link", { name: "Als PDF speichern" })).toHaveAttribute(
      "download",
      "Rechnung-RE-2026-00001.pdf",
    );

    expect(correction).toHaveTextContent("Rechnungskorrektur");
    expect(correction).toHaveTextContent("RK-2026-00001");
    expect(correction).toHaveTextContent("11,90");
  });
});
