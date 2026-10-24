import { isApiProblem } from "@/lib/api/problem";

type Messages = Readonly<Record<string, string>>;

const INVALID_LINK =
  "Dieser Link ist ungültig, abgelaufen oder wurde schon benutzt. Fordere bitte einen neuen an.";

/**
 * German texts for the backend's problem codes (`code` of every RFC 9457 response,
 * listed per route in openapi.json) and for the codes the client assigns itself
 * (src/lib/api/problem.ts). The backend's English `detail` is never shown.
 */
export const PROBLEM_MESSAGES: Messages = {
  // Identity
  invalid_credentials: "E-Mail-Adresse oder Passwort ist falsch.",
  email_not_verified:
    "Bitte bestätige zuerst deine E-Mail-Adresse. Den Link dazu haben wir dir per E-Mail geschickt.",
  invalid_token: INVALID_LINK,
  invalid_password: "Das Passwort ist nicht richtig.",
  not_authenticated: "Du bist nicht mehr angemeldet. Bitte melde dich erneut an.",

  // Roles
  insufficient_role: "Deine Rolle erlaubt das nicht. Bitte wende dich an den Inhaber.",

  // Catalogue
  product_not_found: "Dieses Produkt gibt es nicht (mehr).",
  product_scale_not_found: "Diese Spurweite gibt es an dem Produkt nicht mehr.",
  variant_not_found: "Diese Variante gibt es nicht mehr.",
  category_not_found: "Diese Kategorie gibt es nicht.",
  slug_taken: "Diese Adresse ist schon vergeben. Bitte wähle eine andere.",
  slug_locked: "Die Adresse eines veröffentlichten Produkts bleibt fest, weil Links darauf zeigen.",
  scale_exists: "Das Produkt gibt es schon in dieser Spurweite.",
  variant_exists: "Diese Ausführung gibt es in der Spurweite schon.",
  invalid_product_state: "Das ist im aktuellen Zustand des Produkts nicht möglich.",
  product_not_deletable:
    "Nur Entwürfe, die nie im Shop waren, lassen sich löschen. Archiviere das Produkt stattdessen.",
  not_publishable: "Das Produkt erfüllt noch nicht alle Regeln für den Shop.",
  precondition_failed:
    "Jemand hat das Produkt inzwischen geändert. Lade den aktuellen Stand und übernimm deine Änderung dann erneut.",
  precondition_required: "Die Änderung braucht den gelesenen Stand. Bitte lade die Seite neu.",

  // Media
  asset_not_found: "Dieses Bild gibt es nicht mehr.",
  upload_missing: "Die Datei ist nicht im Speicher angekommen. Bitte lade sie erneut hoch.",
  upload_size_mismatch: "Die Datei kam unvollständig an. Bitte lade sie erneut hoch.",
  invalid_asset_state: "Das ist im aktuellen Zustand des Bildes nicht möglich.",
  asset_in_use: "Das Bild wird noch verwendet, zum Beispiel in einer Galerie.",

  // Platform
  validation_failed: "Bitte prüfe deine Eingaben.",
  csrf_header_missing:
    "Die Anfrage wurde aus Sicherheitsgründen abgelehnt. Bitte lade die Seite neu und versuche es noch einmal.",
  unsupported_media_type:
    "Die Anfrage hatte ein unerwartetes Format. Bitte lade die Seite neu und versuche es noch einmal.",
  bad_request: "Die Anfrage konnte nicht verarbeitet werden.",
  forbidden: "Dafür fehlt dir die Berechtigung.",
  not_found: "Die angefragte Adresse gibt es nicht.",
  method_not_allowed: "Diese Aktion ist an dieser Stelle nicht möglich.",
  conflict: "Die Daten wurden inzwischen geändert. Bitte lade die Seite neu.",
  too_many_requests:
    "Zu viele Versuche in kurzer Zeit. Bitte warte ein paar Minuten und versuche es dann noch einmal.",
  database_unavailable:
    "Die Datenbank ist gerade nicht erreichbar. Bitte versuche es gleich noch einmal.",
  service_unavailable:
    "Der Dienst ist gerade nicht erreichbar. Bitte versuche es gleich noch einmal.",
  internal_error:
    "Auf dem Server ist ein unerwarteter Fehler aufgetreten. Bitte versuche es später noch einmal.",

  // Assigned by the client
  network_error: "Keine Verbindung zum Server. Bitte prüfe deine Internetverbindung.",
  unexpected_response:
    "Der Server hat unerwartet geantwortet. Bitte versuche es später noch einmal.",
};

export const FALLBACK_PROBLEM_MESSAGE =
  "Das hat leider nicht geklappt. Bitte versuche es später noch einmal.";

/**
 * Field-level codes of a 422 `validation_failed` problem (`errors[].code`): the
 * backend reduces Pydantic's and the password policy's errors to these.
 */
export const FIELD_MESSAGES: Messages = {
  required: "Bitte fülle dieses Feld aus.",
  too_short: "Die Eingabe ist zu kurz.",
  too_long: "Die Eingabe ist zu lang.",
  invalid_type: "Die Eingabe hat ein ungültiges Format.",
  invalid: "Die Eingabe ist ungültig.",
  invalid_json: "Die Anfrage war fehlerhaft. Bitte lade die Seite neu.",
  unknown_field: "Die Anfrage enthielt ein unbekanntes Feld. Bitte lade die Seite neu.",
  equals_email: "Das Passwort darf nicht deine E-Mail-Adresse sein.",
  unknown: "Diesen Eintrag gibt es nicht.",
  out_of_range: "Der Wert liegt außerhalb des erlaubten Bereichs.",
  duplicate: "Dieser Eintrag ist doppelt.",
  cycle: "Eine Kategorie kann nicht unter sich selbst liegen.",
  not_above_price: "Der frühere Preis muss über dem Preis liegen.",
  not_uploaded: "Das Bild ist noch nicht vollständig hochgeladen.",
  gallery_full: "Die Galerie ist voll (höchstens 40 Bilder).",
  unsupported_type: "Bilder bitte als JPEG, PNG, WebP, AVIF oder HEIC.",
  too_large: "Die Datei ist größer als 50 MB.",
  invalid_filename: "Der Dateiname ist leer oder zu lang.",
};

const PASSWORD_MESSAGES: Messages = {
  too_short: "Das Passwort muss mindestens 10 Zeichen lang sein.",
  too_long: "Das Passwort darf höchstens 256 Zeichen lang sein.",
};

/** Messages that depend on the field as well as on the code. */
const FIELD_SPECIFIC_MESSAGES: Readonly<Record<string, Messages>> = {
  email: {
    invalid: "Bitte gib eine gültige E-Mail-Adresse ein.",
    invalid_type: "Bitte gib eine gültige E-Mail-Adresse ein.",
  },
  display_name: {
    too_short: "Bitte gib einen Namen ein.",
    too_long: "Der Name darf höchstens 80 Zeichen lang sein.",
    invalid: "Der Name enthält unzulässige Zeichen.",
  },
  password: PASSWORD_MESSAGES,
  new_password: PASSWORD_MESSAGES,
  token: { too_short: INVALID_LINK, too_long: INVALID_LINK, invalid: INVALID_LINK },
  slug: {
    invalid: "Nur Kleinbuchstaben, Ziffern und einzelne Bindestriche, z. B. stellwerk-altenau.",
    too_long: "Die Adresse darf höchstens 80 Zeichen lang sein.",
  },
  name: { required: "Bitte gib einen Namen ein.", too_long: "Der Name ist zu lang." },
};

function lookup(messages: Messages | undefined, key: string): string | undefined {
  return messages !== undefined && Object.hasOwn(messages, key) ? messages[key] : undefined;
}

/** The German sentence for a problem code; unknown codes get a neutral fallback. */
export function problemMessage(code: string): string {
  return lookup(PROBLEM_MESSAGES, code) ?? FALLBACK_PROBLEM_MESSAGE;
}

/** The German sentence for anything a request or mutation may have thrown. */
export function errorMessage(error: unknown): string {
  return isApiProblem(error) ? problemMessage(error.code) : FALLBACK_PROBLEM_MESSAGE;
}

/** The German message for one entry of a validation problem's `errors`. */
export function fieldErrorMessage(field: string, code: string): string {
  const specific = Object.hasOwn(FIELD_SPECIFIC_MESSAGES, field)
    ? FIELD_SPECIFIC_MESSAGES[field]
    : undefined;
  return (
    lookup(specific, code) ??
    lookup(FIELD_MESSAGES, code) ??
    lookup(FIELD_MESSAGES, "invalid") ??
    FALLBACK_PROBLEM_MESSAGE
  );
}
