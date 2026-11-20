"use client";

import type { Route } from "next";
import Link from "next/link";

import { AdminShell } from "@/components/admin/admin-shell";
import type { StaffRole } from "@/lib/api/generated/model";
import { OFFICE_ROLES } from "@/lib/staff";

/** The handbook as a printable PDF, served behind the Stellwerk's login (proxy.ts). */
export const HANDBOOK_HREF = "/admin/hilfe/stellwerk-handbuch.pdf";

type Task = {
  question: string;
  steps: readonly string[];
  /** Where the task starts in the Stellwerk. */
  href: Route;
  /** The handbook's page with the whole task. */
  page: number;
  office?: true;
};

/** The day's tasks in short; the handbook has them with pictures (docs/handbuch). */
const TASKS: readonly Task[] = [
  {
    question: "Wie versende ich eine Bestellung?",
    steps: [
      "Bestellungen → Bahnhof „Versand“ → Bestellung öffnen.",
      "Die Pickliste sagt, wo jedes Stück liegt. Holen und einpacken.",
      "Paket wiegen, Gewicht in Gramm eintragen, „Versandlabel drucken“.",
    ],
    href: "/admin/bestellungen",
    page: 9,
  },
  {
    question: "Wie lagere ich Stücke per Scan ein?",
    steps: [
      "Scannen, Modus „Einlagern“, Etikett am Boden scannen.",
      "Bei „Anzahl“ die Zahl der Stücke einstellen.",
      "Etikett des Modells scannen. Vertippt? „Rückgängig“ auf der Antwortkarte.",
    ],
    href: "/admin/scanner",
    page: 21,
  },
  {
    question: "Auf der Messe verkauft: wie buche ich aus?",
    steps: [
      "Scannen, Modus „Ausbuchen“.",
      "Grund „Verkauft (Messe, Laden, privat)“ und die Anzahl wählen.",
      "Etikett des Modells scannen.",
    ],
    href: "/admin/scanner",
    page: 22,
  },
  {
    question: "Die Zahl im Regal stimmt nicht.",
    steps: [
      "Modell öffnen (oder Lager → Boden) → „Zählen“.",
      "Je Platz eintragen, was wirklich daliegt.",
      "„Zählung buchen“. Das Stellwerk bucht den Unterschied.",
    ],
    href: "/admin/lager",
    page: 19,
  },
  {
    question: "Die Überweisung einer Vorkasse ist da.",
    steps: [
      "Im Kontoauszug den Verwendungszweck MB-… suchen.",
      "Bestellungen → Liste → „Zahlung offen“ → Bestellung öffnen.",
      "Betrag vergleichen, „Überweisung eingegangen“.",
    ],
    href: "/admin/bestellungen",
    page: 11,
  },
  {
    question: "Fertig gebaut: wie kommen die Stücke zur Bestellung?",
    steps: [
      "Bestellungen → Liste → „Zu fertigen“ zeigt, was fehlt.",
      "Auf der Seite des Modells „Einbuchen“, Anzahl und Boden.",
      "Die Stücke gehen von selbst an die älteste Bestellung.",
    ],
    href: "/admin/bestellungen",
    page: 23,
    office: true,
  },
  {
    question: "Wo finde ich die Rechnung einer Bestellung?",
    steps: [
      "Der Shop schreibt sie beim Versand und schickt sie mit der Versandmail.",
      "Bestellungen → Bestellung öffnen → Feld „Rechnungen“: „Ansehen“ oder „Als PDF speichern“.",
      "Nach einer Erstattung steht dort auch die Rechnungskorrektur.",
    ],
    href: "/admin/bestellungen",
    page: 9,
    office: true,
  },
  {
    question: "Wie überweise ich Geld zurück, das per Vorkasse kam?",
    steps: [
      "Bestellungen → oben „Rückzahlungen offen“ → Bestellung öffnen.",
      "Feld „Rückzahlung“: Kontoinhaber und IBAN aus dem Kontoauszug eintragen → „QR-Code zeigen“.",
      "Den QR-Code mit der Banking-App scannen, prüfen und mit TAN freigeben.",
      "Zurück im Stellwerk „Überwiesen“ drücken.",
    ],
    href: "/admin/bestellungen",
    page: 9,
    office: true,
  },
  {
    question: "Wie lege ich ein neues Modell an?",
    steps: [
      "Modelle → „Neues Modell“: Name, Kategorie, Fotos.",
      "Maßstab, Bausatz und/oder Fertigmodell mit Preis und Farben.",
      "Bestand eintragen, Etiketten drucken, „Gleich im Shop zeigen“.",
    ],
    href: "/admin/modelle/neu",
    page: 15,
    office: true,
  },
];

export function tasksFor(role: StaffRole): readonly Task[] {
  return OFFICE_ROLES.has(role) ? TASKS : TASKS.filter((task) => !task.office);
}

export function HelpPage() {
  return (
    <AdminShell>
      {({ staff }) => (
        <>
          <p className="label-caps text-ink-tertiary">Stellwerk</p>
          <h1 className="mt-4 mb-8 text-heading sm:text-title">Hilfe</h1>
          <Handbook />
          <h2 className="mt-12 mb-5 text-body-lg font-medium">Häufige Aufgaben in Kürze</h2>
          <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {tasksFor(staff.role).map((task) => (
              <li key={task.question} className="flex flex-col border border-line bg-surface p-5">
                <h3 className="text-body font-medium">{task.question}</h3>
                <ol className="mt-3 space-y-2 text-small text-ink-secondary">
                  {task.steps.map((step, index) => (
                    <li key={step} className="flex gap-3">
                      <span
                        aria-hidden="true"
                        className="grid size-5 shrink-0 place-items-center bg-selected font-mono text-[0.6875rem] text-on-selected"
                      >
                        {index + 1}
                      </span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
                <p className="mt-auto flex justify-between gap-4 pt-4 text-small">
                  <Link href={task.href} className="font-medium text-accent hover:underline">
                    Hingehen →
                  </Link>
                  <span className="text-ink-tertiary">Handbuch S. {task.page}</span>
                </p>
              </li>
            ))}
          </ul>
          <p className="mt-10 max-w-2xl text-small text-ink-secondary">
            Etwas fehlt oder ist unklar? Sag einem der Inhaber Bescheid (Nele, Johann, Hannes); das Handbuch wächst mit dem Stellwerk. Konten, gesperrte
            Anmeldungen und neue Passwörter regelt Johann.
          </p>
        </>
      )}
    </AdminShell>
  );
}

/** The whole handbook to open, print or save. */
function Handbook() {
  return (
    <section
      aria-labelledby="handbook-heading"
      className="grid gap-6 border border-line bg-surface p-6 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:p-8"
    >
      <div>
        <p aria-hidden="true" className="font-mono text-hint text-ink-tertiary">
          HLP 01 · PDF · 29 Seiten
        </p>
        <h2 id="handbook-heading" className="mt-3 text-heading">
          Das Stellwerk-Handbuch
        </h2>
        <p className="mt-2 max-w-2xl text-small text-ink-secondary">
          Alles Schritt für Schritt mit Bildern: Bestellungen packen und versenden, Lager, Scannen, Fertigung, Modelle,
          dazu häufige Fragen und die Begriffe von A bis Z. Zum Einarbeiten und zum Nachschlagen, auch zum Ausdrucken.
        </p>
      </div>
      <a
        href={HANDBOOK_HREF}
        target="_blank"
        rel="noopener"
        className="inline-flex h-12 items-center justify-center bg-action px-6 font-semibold text-on-action shadow-hard transition-[transform,box-shadow,background-color,color] duration-150 hover:translate-[3px] hover:bg-action-hover hover:text-on-action-hover hover:shadow-hard-pressed"
      >
        Handbuch öffnen
      </a>
    </section>
  );
}
