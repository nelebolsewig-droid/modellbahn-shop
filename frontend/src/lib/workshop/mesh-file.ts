/**
 * Reads the display mesh of a real model (public/modelle/*.mesh, written by
 * scripts/build-explosion-mesh.py from the workshop's print files): one small file with
 * every part, thinned out and quantised. Pure parsing, no three.js.
 *
 * Layout, little endian: "ADPM", uint32 header length, JSON header, then per part its
 * vertices (int16 triples; × `scale` gives the scene's millimetres) and uint16 triangles.
 */

export type PartMesh = { positions: Float32Array; indices: Uint16Array };

type Point = readonly [number, number, number];

/** The parts by name, and the points the moving parts turn about (scene millimetres). */
export type MeshFile = {
  parts: Map<string, PartMesh>;
  pivots: Readonly<Record<string, Point>>;
  /** Scene millimetres per metre of the original. */
  unitsPerMetre: number;
};

type Header = {
  scale: number;
  unitsPerMetre?: number;
  pivots?: Record<string, Point>;
  parts: { name: string; vertices: number; vertexOffset: number; triangles: number; indexOffset: number }[];
};

const MAGIC = "ADPM";

export function parseMeshFile(buffer: ArrayBuffer): MeshFile {
  const view = new DataView(buffer);
  const magic = String.fromCharCode(...new Uint8Array(buffer, 0, 4));
  if (buffer.byteLength < 8 || magic !== MAGIC) {
    throw new Error("not a model mesh file");
  }
  const headerLength = view.getUint32(4, true);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 8, headerLength))) as Header;
  const body = 8 + headerLength;
  const meshes = new Map<string, PartMesh>();
  for (const part of header.parts) {
    // Copies, so the offsets need no alignment and the file's buffer can be dropped.
    const raw = new Int16Array(buffer.slice(body + part.vertexOffset, body + part.vertexOffset + part.vertices * 6));
    const positions = new Float32Array(raw.length);
    for (let index = 0; index < raw.length; index++) {
      positions[index] = (raw[index] ?? 0) * header.scale;
    }
    const indices = new Uint16Array(buffer.slice(body + part.indexOffset, body + part.indexOffset + part.triangles * 6));
    meshes.set(part.name, { positions, indices });
  }
  return { parts: meshes, pivots: header.pivots ?? {}, unitsPerMetre: header.unitsPerMetre ?? 1 };
}

export async function loadMeshFile(url: string, signal?: AbortSignal): Promise<MeshFile> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`mesh file ${url}: ${response.status}`);
  }
  return parseMeshFile(await response.arrayBuffer());
}
