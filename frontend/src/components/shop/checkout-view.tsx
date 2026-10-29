"use client";

import { Indicator, Item } from "@radix-ui/react-radio-group";
import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useForm, useWatch, type FieldErrors, type Resolver } from "react-hook-form";

import { FormError } from "@/components/forms/form-error";
import { AddressFields } from "@/components/shop/address-fields";
import { DeliveryNote } from "@/components/shop/cart-view";
import { OrderTotals } from "@/components/shop/order-totals";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { RadioGroup } from "@/components/ui/radio-group";
import { ResponsivePicture } from "@/components/ui/responsive-picture";
import type { AccountOut, CartOut, CheckoutIn, CustomerAddressOut } from "@/lib/api/generated/model";
import {
  getListAddressesQueryKey,
  getListMyOrdersQueryKey,
  useListAddresses,
} from "@/lib/api/generated/store-account/store-account";
import { placeOrder } from "@/lib/api/generated/store-sales/store-sales";
import { isApiProblem } from "@/lib/api/problem";
import { finishLabel, formatPrice } from "@/lib/catalog/format";
import { applyProblemToForm, FORM_ERROR_KEY } from "@/lib/forms/apply-problem";
import { errorMessage } from "@/lib/i18n/problems";
import { CUSTOMER_AREA, loginPath } from "@/lib/navigation";
import { cartQueryKey, useCart } from "@/lib/sales/cart";
import { IDEMPOTENCY_HEADER, useIdempotencyKeys } from "@/lib/sales/idempotency";
import { totalsFor } from "@/lib/sales/totals";
import { useCustomerSession } from "@/lib/session/customer";
import { cn } from "@/lib/utils";
import { checkoutSchema, EMPTY_ADDRESS, type CheckoutNeeds, type CheckoutValues } from "@/lib/validation/checkout";

const NEW_ADDRESS = "new";
const CART_PROBLEMS: ReadonlySet<string> = new Set([
  "price_changed",
  "cart_items_unavailable",
  "cart_empty",
  "insufficient_stock",
]);
const FIELDS = ["email", "recipient", "street", "postal_code", "city", "country_code"] as const;

/** The checkout: contact, shipping address and the binding order. */
export function CheckoutView() {
  const cart = useCart();
  const session = useCustomerSession();
  const router = useRouter();
  const [placed, setPlaced] = useState(false);

  if (placed) {
    return <PendingNotice className="mt-10">Weiter zur Zahlung …</PendingNotice>;
  }
  if (cart.isPending || session.status === "loading") {
    return <PendingNotice className="mt-10">Die Kasse wird vorbereitet …</PendingNotice>;
  }
  if (cart.isError) {
    return (
      <Alert tone="danger" title="Der Warenkorb konnte nicht geladen werden" className="mt-10 max-w-xl">
        <p>{errorMessage(cart.error)}</p>
      </Alert>
    );
  }
  if (!cart.data.ready_for_checkout) {
    return (
      <div className="mt-10 max-w-xl space-y-6">
        <Alert tone="info" title={cart.data.lines.length === 0 ? "Dein Warenkorb ist leer" : "Bitte prüfe deinen Warenkorb"}>
          <p>
            {cart.data.lines.length === 0
              ? "Leg zuerst etwas in den Warenkorb, dann geht es hier weiter."
              : "Einige Artikel sind nicht mehr erhältlich oder nicht in dieser Menge vorrätig. Passe den Warenkorb an, dann geht es weiter."}
          </p>
        </Alert>
        <Button asChild variant="secondary">
          <Link href={cart.data.lines.length === 0 ? "/katalog" : "/warenkorb"}>
            {cart.data.lines.length === 0 ? "Zum Katalog" : "Zum Warenkorb"}
          </Link>
        </Button>
      </div>
    );
  }
  const customer = session.status === "authenticated" ? session.account : null;
  return (
    <CheckoutForm
      cart={cart.data}
      customer={customer}
      onPlaced={(token) => {
        setPlaced(true);
        router.push(`/bestellung/${token}/bezahlen` as Route);
      }}
    />
  );
}

type CheckoutFormProps = {
  cart: CartOut;
  customer: AccountOut | null;
  onPlaced: (publicToken: string) => void;
};

function CheckoutForm({ cart, customer, onPlaced }: CheckoutFormProps) {
  const queryClient = useQueryClient();
  const book = useListAddresses({ query: { enabled: customer !== null } });
  const entries = customer !== null ? (book.data ?? []) : [];
  const [chosen, setChosen] = useState<string | null>(null);
  // The default address is preselected until the customer picks something else.
  const choice = chosen ?? entries.find((entry) => entry.is_default)?.id ?? NEW_ADDRESS;
  const entry = entries.find((candidate) => candidate.id === choice);
  const { keyFor, settle } = useIdempotencyKeys();

  // What the form must check changes with the choice; the resolver gets it as context.
  const form = useForm<CheckoutValues, CheckoutNeeds>({
    defaultValues: { email: "", ...EMPTY_ADDRESS, save_address: true },
    mode: "onTouched",
    context: { email: customer === null, address: entry === undefined },
    resolver: checkoutResolver,
  });
  const {
    register,
    control,
    formState: { errors, isSubmitting },
  } = form;
  const typedCountry = useWatch({ control, name: "country_code" });
  const countryCode = entry?.country_code ?? typedCountry;
  const country = cart.countries.find((c) => c.code === countryCode) ?? cart.shipping_country;
  const totals = totalsFor(cart.totals.subtotal_cents, country);

  const onSubmit = form.handleSubmit(async (values) => {
    const body: CheckoutIn = {
      expected_total_cents: totals.total_cents,
      ...(customer === null && { email: values.email }),
      ...(entry !== undefined
        ? { address_id: entry.id }
        : {
            address: {
              recipient: values.recipient,
              street: values.street,
              postal_code: values.postal_code,
              city: values.city,
              country_code: values.country_code,
            },
            save_address: customer !== null && values.save_address,
          }),
    };
    try {
      const order = await placeOrder(body, { headers: { [IDEMPOTENCY_HEADER]: keyFor(body) } });
      settle();
      onPlaced(order.public_token);
      void queryClient.invalidateQueries({ queryKey: cartQueryKey });
      if (customer !== null) {
        // The new order heads the history; a saved address joins the book.
        void queryClient.invalidateQueries({ queryKey: getListMyOrdersQueryKey() });
        void queryClient.invalidateQueries({ queryKey: getListAddressesQueryKey() });
      }
    } catch (error) {
      if (isApiProblem(error) && CART_PROBLEMS.has(error.code)) {
        // Show today's prices and lines; the customer confirms again.
        void queryClient.invalidateQueries({ queryKey: cartQueryKey });
      }
      applyProblemToForm(error, form.setError, { fields: [...FIELDS] });
    }
  });
  const formError = errors.root?.[FORM_ERROR_KEY]?.message;

  return (
    <form noValidate onSubmit={onSubmit} className="mt-10 grid items-start gap-12 lg:grid-cols-[minmax(0,1fr)_24rem] lg:gap-14">
      <ol className="space-y-12">
        <CheckoutStep number={1} title="Kontakt">
          {customer !== null ? (
            <p className="text-ink-secondary">
              Du bestellst mit deinem Kundenkonto als <span className="font-medium text-ink">{customer.display_name}</span>.
              Die Bestellbestätigung geht an <span className="font-medium text-ink break-all">{customer.email}</span>.
            </p>
          ) : (
            <div className="max-w-lg space-y-4">
              <FormField
                label="E-Mail-Adresse"
                hint="Hierhin schicken wir die Bestellbestätigung mit dem Link zu deiner Bestellung."
                error={errors.email?.message}
              >
                {(field) => <Input {...field} {...register("email")} type="email" autoComplete="email" />}
              </FormField>
              <p className="text-hint text-ink-tertiary">
                Schon ein Kundenkonto?{" "}
                <Link href={loginPath(CUSTOMER_AREA, "/kasse")} className="font-medium text-accent underline-offset-4 hover:underline">
                  Anmelden
                </Link>
                . Als Gast bestellst du ohne Konto; legst du später eins mit derselben Adresse an, erscheint die Bestellung dort.
              </p>
            </div>
          )}
        </CheckoutStep>

        <CheckoutStep number={2} title="Lieferadresse">
          {entries.length > 0 ? (
            <RadioGroup
              aria-label="Lieferadresse"
              value={choice}
              onValueChange={setChosen}
              className="mb-6 grid gap-3 sm:grid-cols-2"
            >
              {entries.map((candidate) => (
                <AddressChoice key={candidate.id} value={candidate.id} title={candidate.label || candidate.recipient}>
                  <AddressLines address={candidate} />
                </AddressChoice>
              ))}
              <AddressChoice value={NEW_ADDRESS} title="Neue Adresse">
                <span className="text-ink-tertiary">An eine andere Adresse liefern</span>
              </AddressChoice>
            </RadioGroup>
          ) : null}
          {entry === undefined ? (
            <div className="max-w-lg space-y-5">
              <AddressFields register={register} errors={errors} />
              {customer !== null ? (
                <label className="flex items-center gap-3 text-small">
                  <input type="checkbox" {...register("save_address")} className="size-4 accent-[var(--selected)]" />
                  Im Adressbuch speichern
                </label>
              ) : null}
            </div>
          ) : null}
        </CheckoutStep>
      </ol>

      <aside aria-label="Bestellübersicht" className="rounded-lg bg-surface p-6 sm:p-8 lg:sticky lg:top-8">
        <h2 className="text-heading">Deine Bestellung</h2>
        <ul className="mt-6 space-y-4">
          {cart.lines.map((line) => (
            <li key={line.variant_id} className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-center gap-4">
              <span className="relative aspect-square rounded-sm bg-stage p-1">
                {line.image ? <ResponsivePicture image={line.image} alt="" sizes="56px" variant="thumb" /> : null}
              </span>
              <span className="min-w-0 text-small">
                <span className="block truncate font-medium">{line.product_name}</span>
                <span className="block text-ink-tertiary">
                  {line.quantity} × {line.scale_name} · {finishLabel(line.finish_name, line.color)}
                </span>
              </span>
              <span className="text-small tabular-nums">{formatPrice(line.line_total_cents)}</span>
            </li>
          ))}
        </ul>
        <OrderTotals totals={totals} countryName={country.name} className="mt-6 border-t border-line pt-6" />
        {/* The delivery time belongs on the page before the binding order. */}
        <DeliveryNote cart={cart} className="mt-6" />
        <FormError message={formError} className="mt-6" />
        <Button type="submit" className="mt-6 w-full" disabled={isSubmitting} aria-busy={isSubmitting || undefined}>
          {isSubmitting ? "Bestellung wird angelegt …" : "Zahlungspflichtig bestellen"}
        </Button>
        <p className="mt-4 text-hint text-ink-tertiary">
          Mit der Bestellung akzeptierst du unsere{" "}
          <Link href="/agb" className="underline underline-offset-4 hover:text-ink">AGB</Link>; die{" "}
          <Link href="/widerruf" className="underline underline-offset-4 hover:text-ink">Widerrufsbelehrung</Link> gilt.
          Im nächsten Schritt bezahlst du.
        </p>
      </aside>
    </form>
  );
}

/** Validates with the checkout schema for what the form currently needs. */
const checkoutResolver: Resolver<CheckoutValues, CheckoutNeeds> = (values, needs) => {
  const result = checkoutSchema(needs ?? { email: true, address: true }).safeParse(values);
  if (result.success) {
    return { values: result.data, errors: {} };
  }
  const errors: FieldErrors<CheckoutValues> = {};
  for (const issue of result.error.issues) {
    const name = issue.path[0] as keyof CheckoutValues;
    errors[name] ??= { type: issue.code, message: issue.message };
  }
  return { values: {}, errors };
};

function CheckoutStep({ number, title, children }: { number: number; title: string; children: ReactNode }) {
  return (
    <li className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-5">
      <span
        aria-hidden="true"
        className="grid size-10 place-items-center rounded-full border border-selected font-mono text-small"
      >
        {number}
      </span>
      <h2 className="self-center text-heading">{title}</h2>
      {/* The line between the stations of the checkout. */}
      <span aria-hidden="true" className="mx-auto mt-2 w-px bg-line-strong" />
      <div className="mt-5">{children}</div>
    </li>
  );
}

function AddressChoice({ value, title, children }: { value: string; title: string; children: ReactNode }) {
  return (
    <Item
      value={value}
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-md border border-line-strong bg-surface p-4 text-left",
        "transition-[border-color,box-shadow] duration-150 hover:border-ink-secondary",
        "data-[state=checked]:border-selected data-[state=checked]:shadow-[inset_0_0_0_1px_var(--selected)]",
      )}
    >
      <span className="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border border-line-control">
        <Indicator className="size-2 rounded-full bg-selected" />
      </span>
      <span className="min-w-0 text-small">
        <span className="block font-medium">{title}</span>
        <span className="mt-1 block">{children}</span>
      </span>
    </Item>
  );
}

function AddressLines({ address }: { address: CustomerAddressOut }) {
  return (
    <span className="block text-ink-secondary">
      {address.recipient}
      <br />
      {address.street}
      <br />
      {address.postal_code} {address.city}, {address.country_name}
    </span>
  );
}
