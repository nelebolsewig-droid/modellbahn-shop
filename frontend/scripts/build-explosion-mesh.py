"""Turns the workshop's print files of the EDK 6 into the display mesh of the exploded view.

    uv run --with trimesh --with numpy --with fast-simplification \
        python frontend/scripts/build-explosion-mesh.py <folder with the STL files>

The print files stay in the workshop: this script reads them, places every part where it
sits on the finished crane, thins it out to a few thousand triangles and writes all parts
into one small file, frontend/public/modelle/edk6.mesh. That file is good enough to look
at and far too coarse to print from (ADR 0030).

File format, little endian: "ADPM", uint32 length of a JSON header, the header, then for
each part its vertices (int16 x, y, z; `scale` in the header turns them into the scene's
millimetres) and its triangles (uint16 indices). The header lists the parts with their
offsets. The scene's axes: x along the track, y up, z across.
"""

import json
import struct
import sys
from pathlib import Path

import fast_simplification
import numpy as np
import trimesh

OUT = Path(__file__).resolve().parent.parent / "public" / "modelle" / "edk6.mesh"

# Scene millimetres per metre of the original, and the point of the original that sits in
# the middle of the scene (the crane with its boom up is about as tall as it is long).
UNITS_PER_METRE = 5.6
CENTRE = np.array([3.6, 0.0, 5.2])

# name → (file, triangles to keep, shift in metres, mirrored along the track)
PARTS = {
    "unterwagen": ("edk6_unterwagen.stl", 5000, (0.0, 0.0, 0.0), False),
    "drehgestell-vorn": ("edk6_drehgest.stl", 4500, (0.0, 0.0, 0.0), False),
    "drehgestell-hinten": ("edk6_drehgest.stl", 4500, (0.12, 0.0, 0.0), True),
    # The slewing ring of the base plate sits over the ring of the underframe.
    "grundplatte": ("edk6_oberwagen_grundplatte.stl", 2400, (0.60, 0.80, 1.65), False),
    "gehaeuse": ("edk6_oberwagen_geh.stl", 7000, (0.06, 0.0, 1.75), False),
    "seilklappe": ("edk6_seilklappe.stl", 700, (-1.30, 0.0, 5.50), False),
    "ausleger": ("edk6_ausleger2.stl", 16000, (2.10, 0.0, 1.95), False),
}


def load(folder: Path, file: str, keep: int, shift: tuple[float, float, float], mirrored: bool):
    mesh = trimesh.load(folder / file, force="mesh")
    mesh.merge_vertices()
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    if len(faces) > keep:
        vertices, faces = fast_simplification.simplify(vertices, faces, target_reduction=1 - keep / len(faces))
    vertices = np.array(vertices, dtype=np.float64)
    faces = np.array(faces, dtype=np.int64)
    if mirrored:
        vertices[:, 0] *= -1
        faces = faces[:, ::-1]
    vertices = (vertices + np.array(shift) - CENTRE) * UNITS_PER_METRE
    # Print files have z up; the scene has y up.
    scene = np.column_stack([vertices[:, 0], vertices[:, 2], -vertices[:, 1]])
    return scene, faces


def main(folder: Path) -> None:
    meshes = {name: load(folder, *spec) for name, spec in PARTS.items()}
    reach = max(float(np.abs(vertices).max()) for vertices, _ in meshes.values())
    scale = reach / 32767
    header: dict[str, object] = {"scale": scale, "parts": []}
    body = bytearray()
    for name, (vertices, faces) in meshes.items():
        if len(vertices) > 65535:
            raise SystemExit(f"{name}: too many vertices for 16-bit indices")
        quantised = np.round(vertices / scale).astype("<i2")
        indices = faces.astype("<u2")
        if len(body) % 2:
            body.append(0)
        entry = {"name": name, "vertices": len(quantised), "vertexOffset": len(body)}
        body += quantised.tobytes()
        entry |= {"triangles": len(indices), "indexOffset": len(body)}
        body += indices.tobytes()
        header["parts"].append(entry)  # type: ignore[union-attr]
        low, high = vertices.min(0).round(1), vertices.max(0).round(1)
        print(f"{name:20} {len(indices):6} triangles  {low} … {high}")
    encoded = json.dumps(header, separators=(",", ":")).encode()
    encoded += b" " * (-(8 + len(encoded)) % 4)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(b"ADPM" + struct.pack("<I", len(encoded)) + encoded + bytes(body))
    print(f"{OUT.name}: {OUT.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
