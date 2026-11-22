# ADR 0044: Ein Foto je Messe

Status: angenommen · 22.11.2026

## Kontext

Zu jeder Messe soll ein Bild hinterlegt werden können, etwa ein Foto vom Stand, gern
direkt mit dem Handy aufgenommen. Bilder gibt es schon im Medienmodul (Upload, Größen
im Worker, Fotostudio für Modellfotos). Der Server hat wenig Arbeitsspeicher.

## Entscheidung

- `site.fairs.image_asset_id` (Migration 0031) zeigt auf ein Bild des Medienmoduls,
  `ON DELETE SET NULL`: wird das Bild gelöscht, verliert die Messe nur das Foto.
- Hochgeladen wird wie bei Modellfotos (`POST /admin/media/uploads`), aber mit
  `studio: false`: ein Standfoto bleibt, wie es aufgenommen ist; das Fotostudio (etwa
  1 GB RAM je Foto) läuft dafür nicht. Danach `PUT /admin/fairs/{id}/image`
  (`asset_id` oder `null`).
- Stellwerk, „Messen“: links an jeder Messe ein Rahmen; antippen wählt ein Foto oder
  nimmt eins mit der Kamera auf. Solange der Worker die Größen rechnet, steht
  „Wird vorbereitet …“ darauf und die Liste fragt alle 4 s nach.
- Shop, „Termine“: kommende Messen zeigen das Foto groß in der Karte, vergangene klein
  im Rückblick. Der Shop bekommt nur fertige Fotos.

## Folgen

- Keine neue Abhängigkeit, kein neuer Dienst, keine neue `.env`-Zeile.
- „Alle Fotos umstellen“ in der Galerie schaltet das Fotostudio auch für Messefotos ein;
  wer das nutzt, nimmt den Haken bei Standfotos danach wieder heraus.
