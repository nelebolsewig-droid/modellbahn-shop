# ADR 0008: Objektspeicher und Medien-Pipeline

Status: angenommen · 24.10.2026

## Kontext

Mit Schritt 3 kommen Produktfotos ins System, mit Schritt 6 Druckdateien (STL, 3MF). Ein
Handyfoto hat 3 bis 12 MB, eine STL-Datei leicht 200 MB. Der Shop soll jedes Foto in allen
Bildschirmbreiten scharf und schnell zeigen, ohne dass zur Laufzeit gerechnet wird. Das
System läuft auf einem eigenen Server mit Docker Compose (Konzept §13, Entscheidung 1); der
Entwicklungsstand soll sich ohne Cloud-Konto vollständig starten lassen. Konzept §6 beschreibt
den Ablauf: Upload am Backend vorbei, Verarbeitung im Worker, Meldung per SSE.

## Entscheidung

- **Objektspeicher über S3.** Lokal und auf dem eigenen Server läuft **Garage** (v2.1.0) als
  einzelner Knoten im Compose-Stack, Dienst `storage`. Das Backend spricht nur S3 (boto3);
  ein Wechsel zu Hetzner Object Storage oder Cloudflare R2 ändert Einstellungen, keinen Code.
  Zwei Buckets: `mb-media-private` für Originale (nie öffentlich) und `mb-media-public` für
  die fertigen Stufen.
- **Einrichtung als Job.** `storage-init` (`python -m modellbahn.cli init-storage`) richtet
  über die Admin-API von Garage Layout, Schlüssel, Buckets und Website-Zugriff ein. Der Job ist
  idempotent und läuft bei jedem `make up`; API und Worker starten erst danach.
- **Upload direkt in den Speicher.** `POST /api/v1/admin/media/uploads` prüft Rechte, Typ,
  Größe und Dublette (SHA-256 aus dem Browser) und antwortet mit einer signierten PUT-URL,
  15 Minuten gültig. Typ und Länge sind mitsigniert. Caddy lässt nur `PUT` auf
  `/mb-media-private/incoming/*` zum Speicher durch, der Host-Header bleibt unverändert,
  damit die Signatur gilt. `POST /media/{id}/complete` prüft, dass das Objekt da ist und die
  Größe stimmt, und schreibt Zustand und Ereignis `media.asset.uploaded` in einer Transaktion.
- **Verarbeitung im Worker über die Outbox.** Der Handler liest das Original, erkennt das
  Format an den Magic Bytes, wendet die EXIF-Drehung an, verwirft alle Metadaten (GPS),
  rechnet nach sRGB und erzeugt `thumb` 256², `sm` 480, `md` 960, `lg` 1600, `xl` 2400 und
  `og` 1200 × 630 in WebP (Qualität 80) und AVIF (Qualität 60), nie größer als das Original.
  Dazu kommen ein 16-px-Platzhalter, die Dominanzfarbe und ein 64-Bit-Differenz-Hash. Pillow
  läuft in einem Thread, damit der Worker Ereignisse weiter annimmt.
- **Unveränderliche Namen.** Eine Stufe heißt `{asset}/{stufe}-{hash8}.{format}`; der Hash
  stammt aus dem Inhalt. Der Speicher liefert sie mit
  `Cache-Control: public, max-age=31536000, immutable` über Caddy unter `/medien/…` aus. Wird
  ein Bild neu verarbeitet, entstehen neue Namen; die alten Dateien werden danach gelöscht.
- **Fehler.** Eine Datei, die kein brauchbares Bild ist, scheitert sofort mit Grund
  (`unsupported_format`, `too_many_pixels` …). Andere Fehler wiederholt die Outbox mit
  wachsendem Abstand; der dritte Fehlschlag setzt das Asset auf `failed`. `POST
  /media/{id}/reprocess` stößt es neu an. Ein stündlicher Job entfernt Tickets, deren Upload
  nach 24 Stunden nicht abgeschlossen ist.
- **Bilder nur, wo Bilder hingehören.** Die Galerie verweist mit dem zusammengesetzten
  Fremdschlüssel `(asset_id, asset_kind)` auf `media.assets(id, kind)`; die Datenbank lässt
  dort nur Bilder zu. Ein Asset in einer Galerie lässt sich nicht löschen (`asset_in_use`).

## Folgen

- Die API trägt keine Dateilast; eine große STL-Datei ist in Schritt 6 kein Sonderfall. Die
  Kosten dafür: Die Signatur hängt am Host, deshalb muss der Browser den Speicher unter
  derselben Adresse erreichen, die das Backend signiert (`MB_S3_PUBLIC_ENDPOINT_URL`).
- Der Shop braucht keinen Bildoptimierer zur Laufzeit. `next/image` wird nicht verwendet;
  ein `<picture>` mit AVIF- und WebP-`srcset` und dem Platzhalter genügt.
- Ein 12-Megapixel-Foto braucht im Worker etwa 5 bis 7 Sekunden, fast alles für AVIF. Bei
  vielen gleichzeitigen Uploads wartet die Warteschlange; ein zweiter Worker-Prozess hilft,
  weil die Outbox mit `SKIP LOCKED` verteilt.
- `.env` braucht neue Werte (`GARAGE_RPC_SECRET`, `GARAGE_ADMIN_TOKEN`,
  `MB_S3_ACCESS_KEY_ID`, `MB_S3_SECRET_ACCESS_KEY`). Wer `.env` aus Schritt 2 hat, übernimmt
  den Block „Object storage“ aus `.env.example`; Compose bricht sonst mit einem Hinweis ab. In
  Produktion verweigert das Backend den Entwicklungsschlüssel.
- Sicherungen müssen künftig auch die Volumes `storage-meta` und `storage-data` erfassen,
  nicht nur die Datenbank.
- Garage läuft hier ohne Replikation. Fällt die Platte aus, sind die Originale weg; der
  Produktionsbetrieb muss das vor dem Start klären (Replikation oder externer Speicher).
