"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";

import { startFilm } from "./film-driver";

import "./scroll-film.css";

const IMAGES = "/startseite/edk6";

/** The assemblies of the EDK 6 from bottom to top, with their size in H0 and where each flies to (% of the picture, degrees). */
const PARTS = [
  { file: "drehgestell-hinten", name: "Drehgestell hinten", size: "30,9 × 34,9 × 8,7 mm", x: -7, y: 20, r: -4 },
  { file: "drehgestell-vorn", name: "Drehgestell vorn", size: "30,9 × 34,9 × 8,7 mm", x: 9, y: 24, r: 5 },
  { file: "unterwagen", name: "Unterwagen", size: "96,9 × 37,0 × 14,3 mm", x: 0, y: 10, r: 0 },
  { file: "grundplatte", name: "Grundplatte", size: "49,3 × 36,6 × 13,1 mm", x: 2, y: -2, r: 0 },
  { file: "gehaeuse", name: "Gehäuse", size: "53,0 × 41,0 × 42,2 mm", x: -9, y: -17, r: -3 },
  { file: "ausleger", name: "Knickausleger", size: "141,5 × 29,9 × 188,4 mm", x: 15, y: -13, r: 4 },
  { file: "seilklappe", name: "Seilklappe", size: "7,4 × 21,6 × 3,4 mm", x: -17, y: -33, r: -10 },
] as const;

const PROGRAMME = [
  { tone: "p-a", title: "Schienenfahrzeuge", text: "Kranwagen wie der EDK 6 und weitere Fahrzeuge für die Anlage.", href: "/katalog" },
  { tone: "p-b", title: "Autokrane", text: "Filigrane Ausleger, Stützen und Kabinen.", href: "/katalog" },
  { tone: "p-c", title: "Lkw", text: "Nutzfahrzeuge in Kleinserie, von Hand lackiert und montiert.", href: "/katalog" },
  { tone: "p-d", title: "Sonderanfertigung", text: "Dein Vorbild, vom Einzelstück bis zur Kleinserie.", href: "/sonderanfertigung" },
] as const satisfies readonly { tone: string; title: string; text: string; href: Route }[];

const CALLOUTS = [
  { side: "to-r", title: "Knickausleger", text: "141,5 mm lang", style: { left: "44%", width: "36%", top: "14%" } },
  { side: "to-r", title: "Führerhaus", text: "53,0 × 41,0 mm", style: { left: "3%", width: "25%", top: "66%" } },
  { side: "to-l", title: "Unterwagen", text: "96,9 mm · H0 1:87", style: { left: "51%", width: "34%", top: "80%" } },
] as const;

/**
 * The start page as a scroll film (ADR 0030): the EDK 6 grows, takes itself apart into
 * its seven assemblies, the programme runs past sideways and the crane shrinks from
 * gauge 0 to N beside a ruler. `actions` are the calls to action under the headline.
 *
 * The pictures are renderings of the workshop's own print files. They are decorative
 * plain <img>: the layers must stay pixel-identical to lie exactly on top of each other.
 */
export function ScrollFilm({ actions }: { actions: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => (root.current ? startFilm(root.current) : undefined), []);

  /* eslint-disable @next/next/no-img-element -- see above: layers that must not be re-encoded */
  return (
    <div ref={root} className="film">
      <div className="progress" data-film="progress" aria-hidden="true" />

      <section className="pin f-auftakt" data-film="auftakt">
        <div className="stage">
          <div className="word" data-film="word" aria-hidden="true">
            EDK 6
          </div>
          <div className="frame-marks" aria-hidden="true" />
          <div className="hero-crane" data-film="heroCrane">
            <img
              src={`${IMAGES}/szene.webp`}
              width={1000}
              height={1000}
              fetchPriority="high"
              alt="Eisenbahndrehkran EDK 6 mit mandarinfarbenem Führerhaus und dunklem Gitterausleger auf einem Stück Schottergleis"
            />
            {CALLOUTS.map((callout) => (
              <div key={callout.title} className={`call ${callout.side}`} style={callout.style} aria-hidden="true">
                <span>
                  <b>{callout.title}</b>
                  {callout.text}
                </span>
              </div>
            ))}
          </div>
          <div className="hero-copy" data-film="heroCopy">
            <p className="eyebrow">Seit 1992 · Handarbeit aus Deutschland</p>
            <h1>Kleine Serie. Großer Auftritt.</h1>
            <p>
              Fahrzeugmodelle für Sammler und Modellbahner. Lkw, Autokrane und Schienenfahrzeuge von N bis
              Spur 0.
            </p>
            {actions}
          </div>
          <div className="hint" data-film="hint" aria-hidden="true">
            <i />
            Scrollen
          </div>
        </div>
      </section>

      <section className="pin f-zerlegen" data-film="zerlegen" aria-labelledby="film-zerlegen">
        <div className="stage">
          <div className="kit" data-film="kit">
            <div className="glow" data-film="glow" aria-hidden="true" />
            <img className="base" data-film="base" src={`${IMAGES}/gleis.webp`} width={1000} height={1000} alt="" loading="lazy" />
            <img
              className="whole"
              data-film="whole"
              src={`${IMAGES}/szene.webp`}
              width={1000}
              height={1000}
              alt="Der EDK 6, der sich beim Scrollen in seine sieben Baugruppen zerlegt"
            />
            {PARTS.map((part) => (
              <img
                key={part.file}
                className="layer"
                data-x={part.x}
                data-y={part.y}
                data-r={part.r}
                src={`${IMAGES}/${part.file}.webp`}
                width={1000}
                height={1000}
                alt=""
                loading="lazy"
              />
            ))}
          </div>
          <div className="parts">
            <p className="count" data-film="count" aria-hidden="true">
              0 von 7 Baugruppen gelöst
            </p>
            <h2 id="film-zerlegen">
              Sieben Teile.
              <br />
              Ein Kran.
            </h2>
            <ol data-film="partList">
              {PARTS.map((part) => (
                <li key={part.file}>
                  <b>{part.name}</b>
                  <span>{part.size}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      <section className="pin f-seitwaerts" data-film="seitwaerts" aria-label="Unser Programm">
        <div className="stage">
          <div className="ghost" data-film="ghost" aria-hidden="true">
            Lkw · Autokrane · Schienenfahrzeuge · Sonderanfertigung
          </div>
          <div className="track" data-film="track">
            {PROGRAMME.map((entry, index) => (
              <Link key={entry.title} className={`panel ${entry.tone}`} href={entry.href}>
                <span className="no" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3>{entry.title}</h3>
                  <p>{entry.text}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="pin f-massstab" data-film="massstab" aria-labelledby="film-massstab">
        <div className="stage">
          <div className="scale-copy">
            <p className="eyebrow">Derselbe Kran, vier Baugrößen</p>
            <h2 id="film-massstab">Scroll ihn kleiner.</h2>
            <p className="ratio" data-film="ratio" aria-hidden="true">
              1:45
            </p>
            <p className="readout" aria-hidden="true">
              Auslegerhöhe <b data-film="mm">364,2 mm</b>
            </p>
            <ul className="gauge" data-film="gauge">
              <li>Spur 0 · 1:45</li>
              <li>Spur H0 · 1:87</li>
              <li>Spur TT · 1:120</li>
              <li>Spur N · 1:160</li>
            </ul>
          </div>
          <div className="bench" data-film="bench">
            <div className="ruler" data-film="ruler" aria-hidden="true" />
            <div className="mark" data-film="mark" aria-hidden="true">
              <b data-film="markLabel">364 mm</b>
            </div>
            <img
              data-film="benchCrane"
              src={`${IMAGES}/kran.webp`}
              width={1000}
              height={1028}
              alt="Der EDK 6 neben einem Lineal: von Spur 0 mit 364 mm Höhe bis Spur N mit 102 mm"
              loading="lazy"
            />
            <div className="floor" aria-hidden="true" />
          </div>
        </div>
      </section>

      <section className="f-schluss" data-film="schluss" aria-label="Zu den Modellen">
        <div className="belt" data-film="beltA" aria-hidden="true">
          Kleinserie · Handarbeit · seit 1992 · Kleinserie · Handarbeit · seit 1992 ·
        </div>
        <div className="belt out" data-film="beltB" aria-hidden="true">
          N · TT · H0 · Spur 0 · N · TT · H0 · Spur 0 · N · TT · H0 · Spur 0 ·
        </div>
        <div className="close rise">
          <p>Das war ein Kran. Die anderen Modelle warten schon, und wenn dein Vorbild fehlt, bauen wir es.</p>
          <Link className="cta" href="/katalog">
            Zu den Modellen
            <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </Link>
        </div>
      </section>
    </div>
  );
  /* eslint-enable @next/next/no-img-element */
}
