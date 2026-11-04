import type { Metadata } from "next";

import { WithdrawalForm } from "@/components/shop/withdrawal-form";
import { FormPage } from "@/components/site/form-page";
import { TextLink } from "@/components/ui/text-link";

export const metadata: Metadata = {
  title: "Vertrag widerrufen",
  robots: { index: false, follow: true },
};

/** The withdrawal function (§ 356a BGB); `?bestellung=` fills in the order number. */
export default async function WithdrawalFunctionPage({ searchParams }: PageProps<"/widerruf/erklaeren">) {
  const { bestellung } = await searchParams;
  const orderNumber = typeof bestellung === "string" ? bestellung.slice(0, 40) : "";
  return (
    <FormPage
      caption="Widerrufsrecht"
      title="Vertrag widerrufen"
      intro={
        <>
          <p>
            Du kannst deine Bestellung innerhalb von 14 Tagen nach Erhalt der Ware ohne Angabe von Gründen widerrufen.
            Hier geht das in einem Schritt; eine Bestätigung bekommst du sofort per E-Mail.
          </p>
          <p className="mt-4">
            Alles Weitere steht in der <TextLink href="/widerruf">Widerrufsbelehrung</TextLink>.
          </p>
        </>
      }
    >
      <WithdrawalForm orderNumber={orderNumber} />
    </FormPage>
  );
}
