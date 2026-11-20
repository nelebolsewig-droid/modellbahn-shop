import type { AdminOrderOut, PickListOut } from "@/lib/api/generated/model";

/*
 * The Bestellpult's one main action (ADR 0033): what this order needs next, said in
 * plain words, with the one button that does it. Everything else on the page stays
 * there, but nobody has to read it all to know what to do.
 */

export type NextAction = {
  /** act: someone has to do something now; wait: the order waits for someone else; done: nothing left. */
  tone: "act" | "wait" | "done";
  title: string;
  text: string;
  /** The button: a panel further down the page (#anchor) or another page. */
  action?: { label: string; href: string };
};

export const ACTION_ANCHORS = {
  transfer: "ueberweisung",
  picking: "packen",
  dispatch: "versand",
  repayment: "rueckzahlung",
} as const;

type Context = {
  order: Pick<AdminOrderOut, "status" | "channel">;
  pickList: Pick<PickListOut, "allocated" | "complete" | "items" | "picked" | "total"> | undefined;
  /** A bank transfer is announced and not booked yet. */
  awaitingTransfer: boolean;
  /** Owner and staff book transfers and allocate; packers don't. */
  mayManage: boolean;
  /** A refund of a bank transfer still has to be transferred back (ADR 0040). */
  repaymentOpen?: boolean;
};

export function nextAction({ order, pickList, awaitingTransfer, mayManage, repaymentOpen = false }: Context): NextAction {
  if (repaymentOpen && mayManage) {
    return {
      tone: "act",
      title: "Geld zurücküberweisen",
      text: "Bezahlt wurde per Überweisung. Name und IBAN aus dem Kontoauszug eintragen, den QR-Code mit der Banking-App scannen, dann „Überwiesen“.",
      action: { label: "Zur Rückzahlung", href: `#${ACTION_ANCHORS.repayment}` },
    };
  }
  switch (order.status) {
    case "pending_payment":
      if (awaitingTransfer && mayManage) {
        return {
          tone: "act",
          title: "Überweisung prüfen",
          text: "Ist das Geld auf dem Konto, hier als bezahlt verbuchen. Danach kann gepackt werden.",
          action: { label: "Zur Überweisung", href: `#${ACTION_ANCHORS.transfer}` },
        };
      }
      return {
        tone: "wait",
        title: "Wartet auf die Zahlung",
        text: "Noch nichts zu tun. Sobald bezahlt ist, erscheint die Bestellung zum Packen.",
      };
    case "paid": {
      if (pickList === undefined) {
        return { tone: "wait", title: "Wird geprüft …", text: "Die Stückliste wird geladen." };
      }
      if (!pickList.allocated) {
        return mayManage
          ? {
              tone: "act",
              title: "Stücke zuteilen",
              text: "Bezahlt, aber das Lager hat noch keine Stücke reserviert. Ein Klick erledigt das.",
              action: { label: "Zum Zuteilen", href: `#${ACTION_ANCHORS.picking}` },
            }
          : { tone: "wait", title: "Wartet aufs Zuteilen", text: "Inhaber oder Team teilen die Stücke gleich zu." };
      }
      const waiting = [...new Set(pickList.items.filter((item) => item.state === "backordered").map((item) => item.title))];
      if (waiting.length > 0) {
        return {
          tone: "wait",
          title: "Wird gefertigt",
          text: `Es fehlt noch: ${waiting.join(", ")}. Ist es gedruckt und eingebucht, geht es hier weiter.`,
          action: { label: "Zur Werkstatt", href: "/admin/fertigung" },
        };
      }
      if (!pickList.complete && pickList.picked === 0) {
        return {
          tone: "act",
          title: "Packen und versenden",
          text: `Alle ${pickList.total} Stück liegen bereit. Aus dem Regal nehmen, einpacken und den Versand melden.`,
          action: { label: "Zum Packen", href: `#${ACTION_ANCHORS.picking}` },
        };
      }
      return {
        tone: "act",
        title: "Versand melden",
        text: pickList.complete
          ? "Alles eingepackt. Jetzt Label und Sendungsnummer, dann geht die Versandmail raus."
          : `${pickList.picked} von ${pickList.total} Stück abgehakt. Fehlt nichts, kann das Paket raus.`,
        action: { label: "Zum Versand", href: `#${ACTION_ANCHORS.dispatch}` },
      };
    }
    case "shipped":
      return { tone: "done", title: "Erledigt", text: "Verschickt, der Kunde hat die Versandmail. Hier ist nichts mehr zu tun." };
    case "cancelled":
      return { tone: "done", title: "Storniert", text: "Nicht verschicken. Hier ist nichts mehr zu tun." };
    default:
      return { tone: "wait", title: "Offen", text: "" };
  }
}
