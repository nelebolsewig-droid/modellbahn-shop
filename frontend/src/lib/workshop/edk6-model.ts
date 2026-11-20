import type { ExplosionModel, Piece, Solid } from "./explosion";

/*
 * The EDK 6 railway crane from the workshop's own print files (thinned-out display meshes,
 * built by scripts/werkstatt/build_edk6_mesh.py). Scene units: 6 per metre of the prototype,
 * x towards the boom, y up, z across. The bogies hold bought wheelsets, drawn as cylinders.
 */

const mesh = (name: string): Solid => ({
  kind: "mesh",
  url: `/werkstatt/edk6/${name}.bin`,
});

const U = 6;
const cylinder = (
  radius: number,
  length: number,
  x: number,
  y: number,
  z: number,
  segments = 24,
): Solid => ({
  kind: "cylinder",
  radius: radius * U,
  length: length * U,
  axis: "z",
  at: [x * U, y * U, z * U],
  segments,
});

function wheelsets(axles: readonly number[]): Solid[] {
  const solids: Solid[] = [];
  for (const x of axles) {
    solids.push(cylinder(0.075, 1.4, x, 0.56, 0, 10));
    for (const side of [-1, 1])
      solids.push(cylinder(0.46, 0.12, x, 0.56, side * 0.75));
  }
  return solids;
}

const bogie = (
  name: string,
  axles: readonly number[],
  side: 1 | -1,
): Piece => ({
  solids: [mesh(name), ...wheelsets(axles)],
  direction: [side * 1.2, -2.2, 0],
  distance: 12,
});

export const EDK6_MODEL: ExplosionModel = {
  name: "Eisenbahndrehkran EDK 6",
  scale: "H0 1:87 · TT 1:120",
  placeholder: false,
  exampleTimes: true,
  handworkMinutes: 300,
  frame: { halfWidth: 100, halfHeight: 82, lift: 48 },
  parts: [
    {
      position: 1,
      name: "Unterwagen",
      count: 1,
      printMinutes: 190,
      order: 5,
      pieces: [
        { solids: [mesh("unterwagen")], direction: [0, -1, 0], distance: 0 },
      ],
    },
    {
      position: 2,
      name: "Drehgestell mit Radsätzen",
      count: 2,
      printMinutes: 150,
      order: 4,
      pieces: [
        bogie("drehgestell-vorn", [0.9, 2.95], 1),
        bogie("drehgestell-hinten", [-0.78, -2.83], -1),
      ],
    },
    {
      position: 3,
      name: "Grundplatte Oberwagen",
      count: 1,
      printMinutes: 60,
      order: 3,
      pieces: [
        { solids: [mesh("grundplatte")], direction: [0, 1, 0], distance: 9 },
      ],
    },
    {
      position: 4,
      name: "Gehäuse",
      count: 1,
      printMinutes: 210,
      order: 2,
      pieces: [
        { solids: [mesh("gehaeuse")], direction: [-1, 4.2, 0], distance: 20 },
      ],
    },
    {
      position: 5,
      name: "Seilklappe",
      count: 1,
      printMinutes: 30,
      order: 0,
      pieces: [
        {
          solids: [mesh("seilklappe")],
          direction: [-1.8, 6.6, 0],
          distance: 26,
        },
      ],
    },
    {
      position: 6,
      name: "Ausleger",
      count: 1,
      printMinutes: 240,
      order: 1,
      pieces: [
        { solids: [mesh("ausleger")], direction: [3.2, 5.2, 0], distance: 22 },
      ],
    },
  ],
};
