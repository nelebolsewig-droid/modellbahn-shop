import type { ExplosionModel, Piece, Solid } from "./explosion";

/*
 * A fire engine in H0 built from simple solids, standing in until the workshop's own model
 * (its print files, simplified) replaces it. Parts, counts and times are examples; the page
 * says so while `placeholder` is set. Millimetres, x along the length (front at -x).
 */

const box = (w: number, h: number, d: number, x: number, y: number, z: number): Solid => ({
  kind: "box",
  size: [w, h, d],
  at: [x, y, z],
});

const cylinder = (
  radius: number,
  length: number,
  axis: "x" | "y" | "z",
  x: number,
  y: number,
  z: number,
  segments?: number,
): Solid => ({ kind: "cylinder", radius, length, axis, at: [x, y, z], segments });

const frame: Solid[] = [box(92, 3, 2.4, 0, 8.5, 7), box(92, 3, 2.4, 0, 8.5, -7)];
for (const x of [-38, -12, 14, 40]) frame.push(box(2, 2.4, 11.6, x, 8.5, 0));

const running: Piece[] = [];
for (const x of [-27, 24]) {
  running.push({ solids: [cylinder(1.1, 21, "z", x, 5.2, 0)], direction: [0, -1, 0], distance: 30 });
  for (const side of [-1, 1]) {
    running.push({
      solids: [cylinder(5.2, 3.4, "z", x, 5.2, side * 11.6), cylinder(2.6, 3.6, "z", x, 5.2, side * 11.6, 20)],
      direction: [0, -0.7, side],
      distance: 30,
    });
  }
}

function shutters(side: -1 | 1): Piece {
  const z = side * 12.9;
  const solids: Solid[] = [];
  for (const x of [-12, 9, 30]) {
    solids.push(box(19, 19, 0.8, x, 22.5, z));
    for (let slat = 0; slat < 6; slat++) solids.push(box(18, 0.3, 0.4, x, 15.5 + slat * 2.8, z + side * 0.55));
  }
  return { solids, direction: [0, 0, side], distance: 24 };
}

const ladder: Solid[] = [box(60, 1, 0.8, 11, 35.4, 3.4), box(60, 1, 0.8, 11, 35.4, -3.4)];
for (let x = -17; x <= 39; x += 4) ladder.push(cylinder(0.35, 6.8, "z", x, 35.4, 0, 8));

export const PLACEHOLDER_MODEL: ExplosionModel = {
  name: "Löschgruppenfahrzeug",
  scale: "H0 · 1:87",
  placeholder: true,
  handworkMinutes: 360,
  parts: [
    {
      position: 1,
      name: "Fahrgestellrahmen",
      count: 1,
      printMinutes: 160,
      order: 10,
      pieces: [{ solids: frame, direction: [0, -1, 0], distance: 20 }],
    },
    { position: 2, name: "Achsen und Räder", count: 6, printMinutes: 110, order: 9, pieces: running },
    {
      position: 3,
      name: "Fahrerhaus",
      count: 1,
      printMinutes: 250,
      order: 8,
      pieces: [
        {
          solids: [
            box(22, 20, 25, -35, 20, 0),
            box(0.6, 7.5, 21, -46.3, 24.5, 0),
            box(0.6, 4, 14, -46.3, 14, 0),
            box(10, 6, 0.6, -37, 24.5, 12.8),
            box(10, 6, 0.6, -37, 24.5, -12.8),
          ],
          direction: [-1, 0.12, 0],
          distance: 30,
        },
      ],
    },
    {
      position: 4,
      name: "Dach mit Blaulichtbalken",
      count: 1,
      printMinutes: 80,
      order: 2,
      pieces: [
        {
          solids: [
            box(21, 1.6, 24, -35, 30.8, 0),
            box(3, 1.8, 16, -42, 32.5, 0),
            cylinder(1.1, 1.8, "y", -42, 34.2, 5.5, 16),
            cylinder(1.1, 1.8, "y", -42, 34.2, -5.5, 16),
          ],
          direction: [-0.35, 1, 0],
          distance: 30,
        },
      ],
    },
    {
      position: 5,
      name: "Geräteaufbau",
      count: 1,
      printMinutes: 450,
      order: 7,
      pieces: [{ solids: [box(67, 24, 25, 10.5, 22.5, 0)], direction: [0.2, 1, 0], distance: 16 }],
    },
    { position: 6, name: "Rollläden links", count: 3, printMinutes: 85, order: 5, pieces: [shutters(-1)] },
    { position: 7, name: "Rollläden rechts", count: 3, printMinutes: 85, order: 5, pieces: [shutters(1)] },
    {
      position: 8,
      name: "Steckleiter",
      count: 1,
      printMinutes: 110,
      order: 0,
      pieces: [{ solids: ladder, direction: [0, 1, 0], distance: 46 }],
    },
    {
      position: 9,
      name: "Saugschläuche",
      count: 2,
      printMinutes: 60,
      order: 1,
      pieces: [
        { solids: [cylinder(1.6, 40, "x", 12, 35.7, 9)], direction: [0, 0.6, 1], distance: 34 },
        { solids: [cylinder(1.6, 40, "x", 12, 35.7, -9)], direction: [0, 0.6, -1], distance: 34 },
      ],
    },
    {
      position: 10,
      name: "Heck mit Pumpe",
      count: 1,
      printMinutes: 130,
      order: 6,
      pieces: [
        {
          solids: [
            box(2.4, 22, 25, 45.2, 21.5, 0),
            box(0.6, 10, 16, 46.6, 18, 0),
            cylinder(1.6, 1.2, "x", 47.2, 18, 5, 16),
            cylinder(1.6, 1.2, "x", 47.2, 18, -5, 16),
          ],
          direction: [1, 0, 0],
          distance: 26,
        },
      ],
    },
    {
      position: 11,
      name: "Stoßstange mit Scheinwerfern",
      count: 1,
      printMinutes: 50,
      order: 4,
      pieces: [
        {
          solids: [box(3, 3.5, 26, -47.6, 9.5, 0), box(0.8, 2, 4, -49.3, 10, 8.5), box(0.8, 2, 4, -49.3, 10, -8.5)],
          direction: [-1, -0.25, 0],
          distance: 36,
        },
      ],
    },
    {
      position: 12,
      name: "Außenspiegel",
      count: 2,
      printMinutes: 30,
      order: 3,
      pieces: ([-1, 1] as const).map((side) => ({
        solids: [box(0.6, 0.6, 3, -44.5, 26, side * 14), box(1.2, 4.2, 2.4, -44.5, 24.5, side * 16.2)],
        direction: [-0.4, 0, side] as const,
        distance: 22,
      })),
    },
  ],
};
