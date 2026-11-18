# ADR 0033: Stellwerk – sagt, was dran ist

Status: angenommen · 18.11.2026 · ergänzt ADR 0028 (Scanner) und ADR 0030 (Gestaltung)

## Kontext

Die Bewertung der Benutzerfreundlichkeit vom 18.11.2026 fand im Stellwerk vor allem
Suchen und Deuten: „Heute“ zeigte Kacheln, aber nicht, was als Nächstes zu tun ist; der
Scanner wollte vorher wissen, wozu gescannt wird; ein neues Modell begann jedes Mal leer;
das Bestellpult zeigte alles gleich laut, mit Feldcodes (VK 11 bis VK 19) und Begriffen
aus dem Gleisbild („Wagen im Netz“, „abfahrbereit“, „Fahrstraße“).

## Entscheidung

1. **Heute ist eine Aufgabenliste.** `lib/admin/next-steps.ts` ordnet, was ansteht:
   gestörte Drucker, überfällige Druckplatten, Teile melden, Packen (älteste zuerst),
   leere Drucker mit Warteschlange, zu fertigende Modelle, Bestellungen, die seit drei
   Tagen auf Geld warten. Jede Zeile hat genau einen Knopf. Die Kacheln bleiben darunter.
2. **Ein Scanner für alles.** Der Scanner startet in „Automatisch“: Ein Lagerplatz öffnet
   den Platz (Einräumen), ein Etikett danach wird dort eingeräumt, ein Etikett ohne Platz
   wird nachgeschlagen. Die festen Modi bleiben wählbar (`lib/inventory/scan-session.ts`).
3. **„Wie ein vorhandenes Modell“.** Der Assistent für ein neues Modell bietet die
   neuesten Modelle mit Ausführungen an und eine Suche. Ein Tipp übernimmt Kategorie,
   Maßstab, Ausführungen, Farben und Preise (`lib/catalog/model-template.ts`); neu sind
   nur Name und Fotos. Fotos kommen über ein Ablagefeld oder am Handy direkt über die
   Kamera.
4. **Eine Hauptaktion je Bestellung.** Über dem Bestellpult steht, was die Bestellung als
   Nächstes braucht, in Worten und mit einem Knopf, der zum passenden Feld führt
   (`lib/sales/next-action.ts`): Überweisung prüfen, Stücke zuteilen, wird gefertigt,
   packen, Versand melden, erledigt.
5. **Klartext.** Die Feldcodes der Panels entfallen. Das Gleisbild heißt „Übersicht“;
   „Wagen im Netz“ wird „offen“, „abfahrbereit“ wird „versandfertig“. Die Bildsprache
   (Schienen, Lampen) bleibt, die Wörter sind die des Alltags.
6. **Schnellsuche.** ⌘K oder Strg+K öffnet überall im Stellwerk ein Suchfeld, das Seiten,
   Bestellungen (Nummer, E-Mail, Name) und Modelle findet. Pfeiltasten wählen, Enter
   öffnet. Packer sehen nur, was sie öffnen dürfen.

## Folgen

- Keine Änderung am Backend; alles läuft über die vorhandenen Endpunkte.
- Was „als Nächstes“ gilt, steht an einer Stelle je Seite und ist getestet; neue
  Zustände (etwa Automationen aus ADR 0034) kommen dort hinzu.
- Die Vorlage für ein neues Modell findet nur Modelle mit Ausführungen. Importierte
  Modelle ohne Ausführungen bieten nichts zum Übernehmen.
