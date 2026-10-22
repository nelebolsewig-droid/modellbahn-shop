"use client";

import { useEffect } from "react";

// Replaces the root layout when that fails, so neither globals.css nor the fonts are
// available: the few styles are inline.

export default function GlobalError({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="de">
      <body
        style={{
          margin: 0,
          minHeight: "100dvh",
          display: "grid",
          placeItems: "center",
          background: "#e8e7de",
          color: "#1b211f",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <title>Fehler</title>
        <main style={{ maxWidth: "32rem", padding: "2rem" }}>
          <h1 style={{ textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Etwas ist schiefgegangen
          </h1>
          <p style={{ lineHeight: 1.6 }}>
            Die Seite konnte nicht geladen werden. Bitte versuche es gleich noch einmal.
          </p>
          <button
            type="button"
            onClick={retry}
            style={{
              marginTop: "1rem",
              padding: "0.75rem 1.25rem",
              border: "1.5px solid #1b211f",
              borderRadius: "4px",
              background: "#1b211f",
              color: "#f4f3ee",
              font: "inherit",
              cursor: "pointer",
            }}
          >
            Erneut versuchen
          </button>
        </main>
      </body>
    </html>
  );
}
