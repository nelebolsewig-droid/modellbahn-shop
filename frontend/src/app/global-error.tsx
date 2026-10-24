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
          background: "#f4f4f1",
          color: "#1e2124",
          fontFamily: "\"Helvetica Neue\", Arial, sans-serif",
        }}
      >
        <title>Fehler</title>
        <main style={{ maxWidth: "32rem", padding: "2rem" }}>
          <h1 style={{ fontWeight: 300, letterSpacing: "-0.02em" }}>
            Etwas ist schiefgegangen
          </h1>
          <p style={{ lineHeight: 1.6, color: "#4e5357" }}>
            Die Seite konnte nicht geladen werden. Bitte versuche es gleich noch einmal.
          </p>
          <button
            type="button"
            onClick={retry}
            style={{
              marginTop: "1rem",
              padding: "0.875rem 1.5rem",
              border: 0,
              borderRadius: "999px",
              background: "#1e2124",
              color: "#ffffff",
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
