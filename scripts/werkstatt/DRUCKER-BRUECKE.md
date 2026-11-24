# Drucker-Brücke einrichten (ADR 0049)

Die Brücke meldet, was die Drucker tun, an die Fertigung im Stellwerk. Sie läuft auf einem
Rechner, der im Werkstatt-WLAN ist und anbleibt (Mac oder Raspberry Pi).

1. **Schlüssel auf dem Server** (einmal):
   `echo "MB_PRINTER_BRIDGE_TOKEN=$(openssl rand -hex 32)" >> .env`, dann
   `docker compose up -d`. Den Wert aus `.env` brauchst du in Schritt 3.
2. **Drucker finden:** Drucker an, im WLAN. Auf dem Werkstatt-Rechner:
   `uv run drucker_bruecke.py suchen` zeigt IP und Namen. Am Router den Druckern feste
   IP-Adressen geben.
3. **`drucker.toml`** neben das Skript legen:
   ```toml
   server = "https://www.adp-modelle.de"
   schluessel = "…Wert aus Schritt 1…"

   [drucker]          # Code wie im Stellwerk = IP
   D01 = "192.168.178.41"
   D02 = "192.168.178.42"
   ```
4. **Probe:** `uv run drucker_bruecke.py probe drucker.toml` zeigt, was gesendet würde.
5. **Laufen lassen:** `uv run drucker_bruecke.py drucker.toml`. Auf dem Mac dauerhaft mit
   `launchd`: `de.adp-modelle.drucker-bruecke.plist` anpassen, nach `~/Library/LaunchAgents`
   kopieren, `launchctl load ~/Library/LaunchAgents/de.adp-modelle.drucker-bruecke.plist`;
   oder auf dem Pi als systemd-Dienst.

**Tipp:** Die Teilenummer gehört in den Dateinamen der Druckdatei
(`STW-ALT-DACH-H0 x4.ctb`). Dann legt die Brücke die Platte selbst an.
