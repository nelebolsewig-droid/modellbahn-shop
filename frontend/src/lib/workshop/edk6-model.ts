import type { ExplosionModel, Solid } from "./explosion";

/*
 * The railway crane EDK 6 from the workshop's own print files: the first real model of
 * the exploded view (ADR 0030). The shapes come from public/modelle/edk6.mesh; where each
 * part sits is set in scripts/build-explosion-mesh.py. Colours are railway colours: black
 * running gear, grey steel, a red housing, a white flap. Print and handwork times are still examples, and the page says so.
 */

const mesh = (name: string): Solid => ({ kind: "mesh", name });

export const EDK6_MODEL: ExplosionModel = {
  name: "Eisenbahndrehkran EDK 6",
  scale: "TT · 1:120",
  placeholder: false,
  exampleTimes: true,
  meshUrl: "/modelle/edk6.mesh",
  handworkMinutes: 300,
  parts: [
    {
      position: 1,
      name: "Unterwagen",
      count: 1,
      printMinutes: 210,
      order: 6,
      color: "#2b2f33",
      finish: "matte-metal",
      pieces: [{ solids: [mesh("unterwagen")], direction: [0, -1, 0], distance: 8 }],
    },
    {
      position: 2,
      name: "Drehgestelle",
      count: 2,
      printMinutes: 180,
      order: 5,
      color: "#1c1e21",
      finish: "matte-metal",
      pieces: [
        { solids: [mesh("drehgestell-vorn")], direction: [0.5, -1, 0], distance: 26 },
        { solids: [mesh("drehgestell-hinten")], direction: [-0.5, -1, 0], distance: 26 },
      ],
    },
    {
      position: 3,
      name: "Grundplatte mit Drehkranz",
      count: 1,
      printMinutes: 90,
      order: 4,
      color: "#6b7075",
      finish: "matte-metal",
      pieces: [{ solids: [mesh("grundplatte")], direction: [0, 1, 0], distance: 12 }],
    },
    {
      position: 4,
      name: "Gehäuse mit Führerstand",
      count: 1,
      printMinutes: 240,
      order: 3,
      color: "#c62828",
      finish: "gloss-paint",
      pieces: [{ solids: [mesh("gehaeuse")], direction: [-0.25, 1, 0], distance: 30 }],
    },
    {
      position: 5,
      name: "Seilklappe",
      count: 1,
      printMinutes: 20,
      order: 1,
      color: "#f2f2ee",
      finish: "gloss-paint",
      pieces: [{ solids: [mesh("seilklappe")], direction: [-0.4, 1, 0], distance: 46 }],
    },
    {
      position: 6,
      name: "Knickausleger",
      count: 1,
      printMinutes: 330,
      order: 0,
      color: "#8d9399",
      finish: "matte-metal",
      pieces: [{ solids: [mesh("ausleger")], direction: [1, 0.25, 0], distance: 26 }],
    },
  ],
};

/**
 * How the crane is jointed for its motion (lib/workshop/motion.ts): which meshes turn with
 * the superstructure, which is the flap, which are the bogies. The names are those of the
 * mesh file; each joint turns about the pivot of the same name there.
 */
export const EDK6_RIG = {
  fixed: ["unterwagen"],
  bogies: ["drehgestell-vorn", "drehgestell-hinten"],
  /** Turn together about the pivot "drehkranz". */
  superstructure: ["grundplatte", "gehaeuse", "ausleger"],
  /** Part of the superstructure, and hinged about the pivot "seilklappe". */
  flap: "seilklappe",
  /** Standard gauge, metres. */
  gauge: 1.435,
} as const;
