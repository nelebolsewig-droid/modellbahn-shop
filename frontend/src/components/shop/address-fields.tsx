"use client";

import { useEffect, useId, useRef } from "react";
import type { FieldErrors, FieldValues, Path, UseFormRegister } from "react-hook-form";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SHIPPING_COUNTRY_LIST } from "@/lib/sales/countries";
import { usePostalTowns } from "@/lib/sales/postal-towns";
import type { AddressValues } from "@/lib/validation/checkout";

type AddressFieldsProps<T extends FieldValues & AddressValues> = {
  register: UseFormRegister<T>;
  errors: FieldErrors<T>;
  /**
   * Postal code, city and country as typed, with a way to set the city: a German
   * postal code then fills in its town. Without it the fields are plain.
   */
  town?: { postalCode: string; city: string; countryCode: string; setCity: (city: string) => void };
};

/** Fills in the town of a German postal code, unless the customer typed one of their own. */
function useTownFromPostalCode(town: AddressFieldsProps<FieldValues & AddressValues>["town"]) {
  const towns = usePostalTowns(town?.postalCode ?? "", town?.countryCode ?? "");
  const filled = useRef("");
  const only = towns.length === 1 ? towns[0] : undefined;
  const city = town?.city.trim() ?? "";
  const setCity = town?.setCity;

  useEffect(() => {
    if (only === undefined || setCity === undefined) return;
    if (city === "" || city === filled.current) {
      filled.current = only;
      if (city !== only) setCity(only);
    }
    // Only a new postal code fills in; the city the customer types stays theirs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [only, setCity]);

  return towns;
}

/** Name, street, postal code, city and country of a shipping address. */
export function AddressFields<T extends FieldValues & AddressValues>({
  register,
  errors,
  town,
}: AddressFieldsProps<T>) {
  const towns = useTownFromPostalCode(town);
  const townList = useId();
  // The fields exist in every form that renders this component (AddressValues).
  const field = (name: keyof AddressValues) => name as Path<T>;
  const message = (name: keyof AddressValues) => errors[name]?.message as string | undefined;

  return (
    <div className="grid gap-5 sm:grid-cols-6">
      <FormField label="Name" error={message("recipient")} className="sm:col-span-6">
        {(control) => <Input {...control} {...register(field("recipient"))} autoComplete="shipping name" />}
      </FormField>
      <FormField label="Straße und Hausnummer" error={message("street")} className="sm:col-span-6">
        {(control) => (
          <Input {...control} {...register(field("street"))} autoComplete="shipping street-address" />
        )}
      </FormField>
      <FormField label="Postleitzahl" error={message("postal_code")} className="sm:col-span-2">
        {(control) => (
          <Input
            {...control}
            {...register(field("postal_code"))}
            autoComplete="shipping postal-code"
            autoCapitalize="characters"
          />
        )}
      </FormField>
      <FormField
        label="Ort"
        hint={towns.length > 1 ? "Unter dieser Postleitzahl liegen mehrere Orte; die Liste schlägt sie vor." : undefined}
        error={message("city")}
        className="sm:col-span-4"
      >
        {(control) => (
          <>
            <Input
              {...control}
              {...register(field("city"))}
              autoComplete="shipping address-level2"
              list={towns.length > 1 ? townList : undefined}
            />
            {towns.length > 1 ? (
              <datalist id={townList}>
                {towns.map((name) => (
                  <option key={name} value={name} />
                ))}
              </datalist>
            ) : null}
          </>
        )}
      </FormField>
      <FormField label="Land" error={message("country_code")} className="sm:col-span-6">
        {(control) => (
          <Select {...control} {...register(field("country_code"))} autoComplete="shipping country">
            {SHIPPING_COUNTRY_LIST.map((country) => (
              <option key={country.code} value={country.code}>
                {country.name}
              </option>
            ))}
          </Select>
        )}
      </FormField>
    </div>
  );
}
