"use client";

import type { FieldErrors, FieldValues, Path, UseFormRegister } from "react-hook-form";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SHIPPING_COUNTRY_LIST } from "@/lib/sales/countries";
import type { AddressValues } from "@/lib/validation/checkout";

type AddressFieldsProps<T extends FieldValues & AddressValues> = {
  register: UseFormRegister<T>;
  errors: FieldErrors<T>;
};

/** Name, street, postal code, city and country of a shipping address. */
export function AddressFields<T extends FieldValues & AddressValues>({
  register,
  errors,
}: AddressFieldsProps<T>) {
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
      <FormField label="Ort" error={message("city")} className="sm:col-span-4">
        {(control) => <Input {...control} {...register(field("city"))} autoComplete="shipping address-level2" />}
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
