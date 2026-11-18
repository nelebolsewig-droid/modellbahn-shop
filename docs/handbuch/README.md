# Stellwerk-Handbuch

Anleitung für das Team (Inhaber, Mitarbeiter, Packer): Bestellungen, Lager, Scannen,
Fertigung, Modelle, häufige Fragen, Begriffe. Im Stellwerk unter **Hilfe** (`/admin/hilfe`),
das PDF liegt in `frontend/public/admin/hilfe/stellwerk-handbuch.pdf` und ist nur mit
Anmeldung erreichbar (`proxy.ts`).

- `handbuch.html`: der Text, A4 im Design von adp-Modelle. Hier ändern.
- `img/`: Bildschirmfotos aus einem Stellwerk mit Beispieldaten (keine echten Kunden).
- `pdf.mjs`: druckt das PDF neu: `node docs/handbuch/pdf.mjs`.

Nach Änderungen am Text stimmen Seitenzahlen im Inhalt und in `help-page.tsx` vielleicht
nicht mehr: im PDF nachsehen und angleichen.

Offen: Die Fotobearbeitung steht als „Kommt bald“ in Kapitel 10 und wird
ergänzt, sobald sie im Stellwerk ist. Der Lagerwert steht in Kapitel 07.
