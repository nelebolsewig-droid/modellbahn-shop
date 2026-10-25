# ADR 0010: Katalog nach Maßstab statt nach Spurweite

Status: angenommen · 25.10.2026

## Kontext

Der Inhaber hat am 25.10.2026 per Sprachnachricht beschrieben, wie er sein Sortiment ordnet.

**Ebene 1: Maßstab.**
- Für Schienenfahrzeuge: N 1:160, Z 1:220, H0 1:87, 0 und G.
- Dazu Maßstäbe für Straßenfahrzeuge um 1:24 und 1:25.

**Ebene 2: Kategorien**, zum Beispiel Schienenfahrzeuge, Straßenfahrzeuge, LKW und PKW.

**Ebene 3: Unterkategorien**, zum Beispiel Straßenbahn, oder Feuerwehr unter LKW.

Schritt 3 hatte den Katalog nach *Spurweite* aufgebaut: H0, TT und N mit Verhältnis und
Gleismaß, fest in der Migration. Daran passen vier Dinge nicht:
- Ein LKW hat einen Maßstab, aber kein Gleis.
- G wird in 1:22,5 gebaut, Spur 0 je nach Land in 1:45 oder 1:43,5. Das Verhältnis war eine
  ganze Zahl.
- Neue Maßstäbe brauchten eine Migration.
- Der Shop filterte die Spurweite nur neben der Kategorie; er begann nicht mit ihr.

## Entscheidung

- **Der Begriff heißt Maßstab.** In der Oberfläche steht „Maßstab“, angezeigt als
  „H0 · 1:87“. Ein Maßstab, der nach seinem Verhältnis heißt, steht nur einmal da: „1:24“.
  Im Code hieß er schon `Scale` und bleibt so; nur die Kommentare sagen jetzt *scale*
  statt *gauge*.
- **Das Gleis ist eine Eigenschaft, keine Pflicht.**
  - `track_gauge_mm` darf leer sein; der Shop zeigt dann „ohne Gleis“.
  - Das Verhältnis ist eine Dezimalzahl mit einer Nachkommastelle (`NUMERIC(5,1)`,
    größer als 1, höchstens 1000).
  - Die Anzeige folgt der deutschen Schreibweise: 1:22,5.
- **Maßstäbe pflegt der Shop selbst.** Im Stellwerk gibt es dafür die Seite
  `/admin/katalog/massstaebe`, an der API `/admin/scales`.
  - Owner und Mitarbeiter dürfen dort anlegen, umbenennen sowie Verhältnis und Gleis
    korrigieren.
  - Der **Code bleibt fest**: Er steht in jeder SKU (`MB-000042-H0-B`) und in den Adressen
    des Shops. Erlaubt sind ein bis vier Großbuchstaben oder Ziffern, etwa `H0` oder `124`.
  - Der Name ist eindeutig.
  - Löschen geht nur, solange kein Produkt den Maßstab anbietet und kein Foto ihm
    zugeordnet ist (409 `scale_in_use`). Die Fremdschlüssel bleiben `RESTRICT`.
- **Die Reihenfolge ergibt sich aus der Größe:** die kleinsten Modelle zuerst, also von
  Z 1:220 bis G 1:22,5. Die Spalte `position` entfällt.
- **Startdaten:** Migration 0004 ergänzt zu H0, TT und N die Maßstäbe Z (1:220, 6,5 mm),
  0 (1:45, 32 mm), G (1:22,5, 45 mm), 1:25 und 1:24 (beide ohne Gleis).
- **Der Shop beginnt mit dem Maßstab.**
  - `/katalog` fragt „Welcher Maßstab?“ und zeigt Kacheln mit der Zahl der Modelle.
    Auf jeder Kachel liegt ein Maßband: Es zeigt, wie lang ein Meter Vorbild im
    Maßstab ist, alle Bänder im selben Millimetermaß.
  - `/katalog/{maßstab}` und `/katalog/{maßstab}/{kategorie}` zeigen die Modelle.
    Daneben steht der Kategorienbaum, aber nur mit Zweigen, die in diesem Maßstab Modelle
    haben, jeweils mit Zahl.
  - Dazu kommen Epoche, Sortierung, die Suche im Maßstab und der Wechsel in einen anderen
    Maßstab. Beim Wechsel bleibt die Kategorie erhalten, wo es sie dort gibt.
  - Alte Adressen wie `/katalog?spur=H0&kategorie=lkw` leiten dauerhaft (308) auf die neue
    Adresse um. Fehlt der Maßstab, gilt der mit den meisten Modellen in der Kategorie.
- **Die Zahlen liefert die Navigation.**
  - `GET /store/navigation` nennt je Maßstab `product_count` und je Kategorie
    `product_counts` nach Maßstab, nur für die Kategorie selbst. Der Shop zählt die
    Unterkategorien hinzu.
  - Ein Produkt zählt in einem Maßstab, wenn es dort eine aktive Variante hat, nach derselben
    Regel wie der Filter der Produktliste.
  - Die Kategorien bleiben ein einziger Baum für alle Maßstäbe.

## Folgen

- Der Inhaber legt die Ordnung aus der Sprachnachricht als Daten an, ohne neuen Code:
  Kategorien und Unterkategorien im Stellwerk, Maßstäbe auf der neuen Seite.
- Ein Modell kann weiterhin in mehreren Maßstäben angeboten werden, das Stellwerk etwa in
  H0 und N. Es erscheint dann unter jedem davon, und die Produktseite öffnet sich in dem
  Maßstab, aus dessen Liste man kommt (`?massstab=h0`).
- Ein Maßstab ohne Modelle erscheint im Shop nur als Hinweis „Noch ohne Modelle“, eine
  Kategorie ohne Modelle im gewählten Maßstab gar nicht. Die Kategorie „Smoke-Test“ des
  Smoke-Tests verschwindet damit aus der Navigation.
- Die Codes sind Teil der SKU. Ein umbenannter Maßstab behält deshalb seine Artikelnummern.
  Für einen echten neuen Code legt man einen neuen Maßstab an.
- Ein Rückbau auf 0003 löscht die neuen Maßstäbe und scheitert, solange ein Produkt einen
  davon nutzt. Dabei geht nichts stillschweigend verloren.
