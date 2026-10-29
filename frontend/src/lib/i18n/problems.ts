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
  product_scale_not_found: "Diesen Maßstab gibt es an dem Produkt nicht mehr.",
  variant_not_found: "Diese Variante gibt es nicht mehr.",
  category_not_found: "Diese Kategorie gibt es nicht.",
  slug_taken: "Diese Adresse ist schon vergeben. Bitte wähle eine andere.",
  slug_locked: "Die Adresse eines veröffentlichten Produkts bleibt fest, weil Links darauf zeigen.",
  scale_exists: "Das Produkt gibt es schon in diesem Maßstab.",
  variant_exists: "Diese Ausführung gibt es in dem Maßstab schon, in dieser Farbe.",
  scale_not_found: "Diesen Maßstab gibt es nicht mehr.",
  scale_in_use: "Der Maßstab wird noch verwendet: Produkte gibt es in ihm, oder Fotos sind ihm zugeordnet.",
  invalid_product_state: "Das ist im aktuellen Zustand des Produkts nicht möglich.",
  product_not_deletable:
    "Nur Entwürfe, die nie im Shop waren, lassen sich löschen. Archiviere das Produkt stattdessen.",
  not_publishable: "Das Produkt erfüllt noch nicht alle Regeln für den Shop.",

  // Fairs and the fair news
  fair_not_found: "Diese Messe gibt es nicht (mehr).",
  fair_not_published: "Erst veröffentlichen, dann ankündigen: Die Mail verlinkt die Terminseite.",
  fair_past: "Die Messe ist vorbei; ankündigen lässt sich nur, was noch kommt.",
  fair_already_announced: "Diese Messe wurde schon angekündigt. Jede Messe geht nur einmal hinaus.",
  fair_news_token_invalid:
    "Dieser Link ist ungültig, abgelaufen oder wurde schon benutzt. Melde dich auf der Terminseite einfach noch einmal an.",
  precondition_failed:
    "Jemand hat das Produkt inzwischen geändert. Lade den aktuellen Stand und übernimm deine Änderung dann erneut.",
  precondition_required: "Die Änderung braucht den gelesenen Stand. Bitte lade die Seite neu.",

  // Media
  asset_not_found: "Dieses Bild gibt es nicht mehr.",
  upload_missing: "Die Datei ist nicht im Speicher angekommen. Bitte lade sie erneut hoch.",
  upload_size_mismatch: "Die Datei kam unvollständig an. Bitte lade sie erneut hoch.",
  invalid_asset_state: "Das ist im aktuellen Zustand des Bildes nicht möglich.",
  asset_in_use: "Das Bild wird noch verwendet, zum Beispiel in einer Galerie.",

  // Sales
  variant_unavailable: "Diese Ausführung ist gerade nicht erhältlich.",
  cart_full: "Mehr verschiedene Artikel passen nicht in den Warenkorb.",
  cart_empty: "Dein Warenkorb ist leer.",
  cart_items_unavailable:
    "Einige Artikel in deinem Warenkorb gibt es nicht mehr. Bitte entferne sie, dann geht es weiter.",
  price_changed:
    "Die Preise haben sich gerade geändert. Bitte sieh dir die neue Summe an und bestelle dann erneut.",
  idempotency_key_reused:
    "Diese Anfrage wurde schon mit anderen Angaben gestellt. Bitte lade die Seite neu.",
  order_not_found: "Diese Bestellung gibt es nicht.",
  order_not_payable: "Diese Bestellung wartet nicht (mehr) auf eine Zahlung.",
  invalid_order_state: "Das ist im aktuellen Zustand der Bestellung nicht möglich.",
  payment_unavailable:
    "Der Zahlungsdienst ist gerade nicht erreichbar. Es wurde nichts abgebucht; versuche es bitte gleich noch einmal.",
  address_not_found: "Diese Adresse gibt es nicht mehr.",
  address_book_full: "Dein Adressbuch ist voll. Lösche bitte zuerst eine Adresse.",
  insufficient_stock:
    "So viele haben wir gerade nicht vorrätig. Bitte verringere die Menge oder sieh später noch einmal nach.",
  order_not_picked:
    "Die Bestellung ist noch nicht vollständig kommissioniert. Scanne zuerst alle Stücke.",
  marketplace_order:
    "Diese Bestellung kam über eBay. Storniere sie auf eBay; der Shop übernimmt die Stornierung dann selbst.",

  // eBay
  ebay_off: "eBay ist auf diesem Server ausgeschaltet.",
  ebay_not_connected: "Der Shop ist nicht mit eBay verbunden. Verbinde ihn auf der eBay-Seite.",
  ebay_not_ready:
    "Für Angebote fehlt noch etwas: Prüfe auf der eBay-Seite Versand, Zahlung, Rücknahme und Versandort.",
  ebay_state_invalid: "Der Rücksprung von eBay war abgelaufen. Bitte verbinde dich erneut.",
  ebay_unavailable: "eBay ist gerade nicht erreichbar. Bitte versuche es gleich noch einmal.",
  ebay_rejected: "eBay hat die Anfrage abgelehnt.",
  listing_not_found: "Dieses Angebot (oder das Produkt in diesem Maßstab) gibt es nicht.",
  marketplace_order_not_found: "Diese eBay-Bestellung gibt es nicht.",
  test_mode_only: "Das geht nur auf dem Testmarktplatz.",

  // Inventory
  location_not_found: "Diesen Lagerplatz gibt es nicht.",
  location_code_taken: "Einen Lagerplatz mit diesem Code gibt es schon.",
  location_not_empty: "Der Lagerplatz ist nicht leer: Es liegt Ware darin oder es gibt Plätze darunter.",
  location_in_use:
    "Hier lag schon einmal Ware. Der Lagerplatz bleibt deshalb erhalten, damit seine Geschichte nachvollziehbar ist.",
  unit_not_found: "Diese Einheit gibt es nicht.",
  invalid_unit_state: "Das ist im aktuellen Zustand der Einheit nicht möglich.",
  variant_has_units:
    "Von dieser Variante gibt es Einheiten im Lager. Sie lässt sich nur noch deaktivieren, nicht löschen.",
  order_not_allocatable: "Nur bezahlte Bestellungen bekommen Ware zugeteilt.",
  scan_id_reused: "Dieser Scan wurde schon mit anderem Inhalt gesendet. Bitte scanne erneut.",
  scan_not_found: "Diesen Scan gibt es nicht.",
  scan_already_undone: "Dieser Scan ist schon rückgängig gemacht.",
  scan_too_old: "Rückgängig geht nur zehn Minuten lang. Buche die Einheit stattdessen um.",
  scan_nothing_booked: "Dieser Scan hat nichts gebucht; es gibt nichts rückgängig zu machen.",
  scan_changed_since:
    "Die Einheit wurde inzwischen weiter bewegt. Rückgängig ist deshalb nicht mehr möglich.",

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
  not_shipped: "Dorthin liefern wir leider nicht.",
  invalid_parent: "Diese Art von Lagerplatz gehört nicht an diese Stelle.",
  holds_no_goods: "In diesen Lagerplatz kommt keine Ware: nur Fächer, Boxen und Ablagen nehmen Ware auf.",
  not_colored: "Ein Bausatz kommt ohne Farbe. Farben gibt es nur beim Fertigmodell.",
  not_offered: "Diese Ausführung bieten wir nicht mehr an.",
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
  name: {
    required: "Bitte gib einen Namen ein.",
    too_long: "Der Name ist zu lang.",
    duplicate: "Diesen Namen trägt schon ein anderer Maßstab.",
  },
  code: {
    invalid: "Ein bis vier Großbuchstaben oder Ziffern, z. B. H0 oder 124.",
    duplicate: "Diesen Code gibt es schon.",
  },
  ratio_denominator: {
    invalid: "Bitte eine Zahl mit höchstens einer Nachkommastelle, z. B. 22,5.",
    out_of_range: "Bitte ein Verhältnis zwischen 1:1 und 1:1000.",
  },
  track_gauge_mm: {
    invalid: "Bitte eine Zahl mit höchstens einer Nachkommastelle, z. B. 16,5.",
    out_of_range: "Bitte eine Spurweite über 0 mm.",
  },
  postal_code: { invalid: "Bitte prüfe die Postleitzahl für das gewählte Land." },
  ends_on: {
    before_start: "Der letzte Tag liegt vor dem ersten.",
    too_long: "Eine Messe dauert hier höchstens 14 Tage.",
  },
  website_url: { invalid: "Bitte eine vollständige Adresse mit https://, z. B. https://www.messe.de." },
  consent: { required: "Bitte setz den Haken, damit wir dir die Messe-Post schicken dürfen." },
  segment: { invalid: "Ein bis acht Großbuchstaben oder Ziffern, z. B. R02 oder B12." },
  color: {
    too_long: "Die Farbe darf höchstens 40 Zeichen lang sein.",
    required: "Bitte gib eine Farbe an: Das Fertigmodell gibt es hier schon in Farben.",
    unnamed_sibling: "Gib zuerst der Variante ohne Farbe ihre Farbe; dann kann eine weitere dazukommen.",
  },
  lead_time_min_weeks: { out_of_range: "Bitte 1 bis 52 Wochen." },
  lead_time_max_weeks: { out_of_range: "Bitte nicht weniger als „von“ und höchstens 52 Wochen." },
  recipient: { required: "Bitte gib den Namen für das Paket ein." },
  street: { required: "Bitte gib Straße und Hausnummer ein." },
  city: { required: "Bitte gib den Ort ein." },
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
