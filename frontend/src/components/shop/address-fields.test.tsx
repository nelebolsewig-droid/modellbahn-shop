import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCallback } from "react";
import { useForm, useWatch } from "react-hook-form";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearPostalTowns } from "@/lib/sales/postal-towns";
import type { AddressValues } from "@/lib/validation/checkout";

import { routeFetch } from "@/test/fetch-routes";
import { jsonResponse } from "@/test/render";

import { AddressFields } from "./address-fields";

const fetchMock = vi.fn<typeof fetch>();

function Address() {
  const form = useForm<AddressValues>({
    defaultValues: {
      recipient: "",
      street: "",
      postal_code: "",
      city: "",
      country_code: "DE",
    },
  });
  const [postalCode, city, countryCode] = useWatch({
    control: form.control,
    name: ["postal_code", "city", "country_code"],
  });
  const setCity = useCallback((town: string) => form.setValue("city", town), [form]);
  return (
    <AddressFields
      register={form.register}
      errors={form.formState.errors}
      town={{ postalCode, city, countryCode, setCity }}
    />
  );
}

describe("AddressFields: postal code fills in the town", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    routeFetch(fetchMock, {
      "GET /plz/01.json": () => jsonResponse({ "01067": ["Dresden"], "01945": ["Tettau", "Guteborn"] }),
      "GET /plz/10.json": () => jsonResponse({ "10115": ["Berlin"] }),
    });
  });
  afterEach(clearPostalTowns);

  it("fills in the one town of a German postal code", async () => {
    render(<Address />);
    await userEvent.type(screen.getByLabelText("Postleitzahl"), "01067");
    await waitFor(() => expect(screen.getByLabelText("Ort")).toHaveValue("Dresden"));
  });

  it("follows a new postal code while the town is still the one it filled in", async () => {
    render(<Address />);
    const postalCode = screen.getByLabelText("Postleitzahl");
    await userEvent.type(postalCode, "01067");
    await waitFor(() => expect(screen.getByLabelText("Ort")).toHaveValue("Dresden"));
    await userEvent.clear(postalCode);
    await userEvent.type(postalCode, "10115");
    await waitFor(() => expect(screen.getByLabelText("Ort")).toHaveValue("Berlin"));
  });

  it("keeps a town the customer typed", async () => {
    render(<Address />);
    await userEvent.type(screen.getByLabelText("Ort"), "Dresden-Neustadt");
    await userEvent.type(screen.getByLabelText("Postleitzahl"), "01067");
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.getByLabelText("Ort")).toHaveValue("Dresden-Neustadt");
  });

  it("suggests the towns of a postal code shared by several", async () => {
    render(<Address />);
    await userEvent.type(screen.getByLabelText("Postleitzahl"), "01945");
    await waitFor(() => expect(screen.getByText(/mehrere Orte/)).toBeInTheDocument());
    expect(screen.getByLabelText("Ort")).toHaveValue("");
    const options = [...document.querySelectorAll("datalist option")].map((option) => option.getAttribute("value"));
    expect(options).toEqual(["Tettau", "Guteborn"]);
  });
});
