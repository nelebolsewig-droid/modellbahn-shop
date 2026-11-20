"""Build the display meshes of the EDK 6 for "So entsteht ein Modell" from its print files.

The STL files stay private (they are the workshop's property); this writes thinned-out,
quantised display meshes that cannot be printed back. Usage:

    uv run --with fast-simplification --with numpy-stl python scripts/werkstatt/build_edk6_mesh.py <Druckdatei-Ordner>

STL units are metres of the prototype, +x front (boom), z up. Output: one file per part in
frontend/public/werkstatt/edk6/, scaled by SCALE into the scene's units, y up, z across.
Format: "EDKM" magic, uint32 vertex count, uint32 index count, float32 quantum,
int16 xyz per vertex, uint32 indices.
"""

import math
import struct
import sys
from pathlib import Path

import fast_simplification
import numpy as np
from stl import mesh as stlmesh

SCALE = 6.0  # scene units per metre of the prototype
QUANTUM = 0.005
OUT = Path(__file__).resolve().parents[2] / "frontend/public/werkstatt/edk6"

# name: (file, shift in metres, mirrored, rotation about y in degrees, triangle budget)
PARTS = {
    "unterwagen": ("edk6_unterwagen.stl", (0, 0, 0), False, 0, 9000),
    "drehgestell-vorn": ("edk6_drehgest.stl", (0, 0, 0), False, 0, 5000),
    "drehgestell-hinten": ("edk6_drehgest.stl", (0.12, 0, 0), True, 0, 5000),
    "grundplatte": ("edk6_oberwagen_grundplatte.stl", (-0.54, 0.80, 1.59), False, 180, 2500),
    "gehaeuse": ("edk6_oberwagen_geh.stl", (0, 0, 1.59), False, 0, 9000),
    "seilklappe": ("edk6_seilklappe.stl", (0.03, 0, 5.04), False, -24, 1200),
    "ausleger": ("edk6_ausleger2.stl", (2.04, 0, 1.79), False, 0, 16000),
}


def load(path: Path) -> tuple[np.ndarray, np.ndarray]:
    tri = stlmesh.Mesh.from_file(str(path)).vectors.reshape(-1, 3).astype(np.float64)
    keys = np.round(tri / 1e-6).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    return tri[first], inverse.reshape(-1, 3)


def place(points: np.ndarray, shift, mirrored: bool, turn: float) -> np.ndarray:
    p = points.copy()
    if mirrored:
        p[:, 0] *= -1
    a = math.radians(turn)  # Blender rotation_euler about y
    c, s = math.cos(a), math.sin(a)
    x, z = p[:, 0].copy(), p[:, 2].copy()
    p[:, 0], p[:, 2] = c * x + s * z, -s * x + c * z
    return p + np.array(shift)


def main(folder: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (file, shift, mirrored, turn, budget) in PARTS.items():
        points, faces = load(folder / file)
        if mirrored:
            faces = faces[:, ::-1]
        if len(faces) > budget:
            points, faces = fast_simplification.simplify(
                points.astype(np.float32), faces.astype(np.int32), target_reduction=1 - budget / len(faces)
            )
        p = place(np.asarray(points, np.float64), shift, mirrored, turn) * SCALE
        scene = np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1)  # z up -> y up
        q = np.round(scene / QUANTUM).astype(np.int16)
        idx = np.asarray(faces, np.uint32).reshape(-1)
        data = b"EDKM" + struct.pack("<IIf", len(q), len(idx), QUANTUM) + q.tobytes() + idx.tobytes()
        (OUT / f"{name}.bin").write_bytes(data)
        lo, hi = scene.min(0), scene.max(0)
        print(f"{name}: {len(idx) // 3} Dreiecke, {len(data) // 1024} KiB, {lo.round(1)} .. {hi.round(1)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
