// @vitest-environment node

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { EDK6_MODEL } from "./edk6-model";
import { parseMeshFile } from "./mesh-file";

const file = readFileSync(new URL("../../../public/modelle/edk6.mesh", import.meta.url));
const buffer = file.buffer.slice(file.byteOffset, file.byteOffset + file.byteLength);

describe("the mesh file of the EDK 6", () => {
  const { parts: meshes, pivots } = parseMeshFile(buffer);

  it("holds every part the model names", () => {
    const named = EDK6_MODEL.parts.flatMap((part) =>
      part.pieces.flatMap((piece) => piece.solids.flatMap((solid) => (solid.kind === "mesh" ? [solid.name] : []))),
    );
    expect(named.length).toBeGreaterThan(0);
    for (const name of named) {
      expect(meshes.has(name), name).toBe(true);
    }
  });

  it("has only triangles that point at existing vertices", () => {
    for (const [name, mesh] of meshes) {
      const vertices = mesh.positions.length / 3;
      expect(mesh.indices.length % 3, name).toBe(0);
      expect(Math.max(...mesh.indices), name).toBeLessThan(vertices);
    }
  });

  it("stays small enough for a phone and too coarse to print from", () => {
    expect(file.byteLength).toBeLessThan(400 * 1024);
    const triangles = [...meshes.values()].reduce((sum, mesh) => sum + mesh.indices.length / 3, 0);
    expect(triangles).toBeLessThan(45_000);
  });

  it("names the points the moving parts turn about", () => {
    expect(Object.keys(pivots).sort()).toEqual(["drehgestell-hinten", "drehgestell-vorn", "drehkranz", "seilklappe"]);
  });

  it("rejects other files", () => {
    expect(() => parseMeshFile(new TextEncoder().encode("solid stl").buffer)).toThrow();
  });
});
