"""Builds the campfire from its two separately generated pieces (references/campfire_parts.png, processed with
process_generated.py into tools/blender/objects/campfire_parts/): the ring of stones with its ash and
the logs in a tipi in the center. No flame: the fire is separate, animated in the game.

Usage (without opening Blender):
    blender --background --factory-startup --python tools/blender/build_campfire.py

The ash comes out of the generator the same color as the stones: it is painted separately, by position (whatever
is low and inside the ring). Saves tools/blender/objects/campfire.blend; then it is exported with export_objects.py.
"""

import os

import bpy
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OBJ = os.path.join(ROOT, "tools/blender/objects")
STONE = (0.62, 0.58, 0.53)         # sRGB: the warm gray of the well (the generated one comes out almost white).
ASH = (0.46, 0.43, 0.40)           # A bit darker than the stones.
ASH_HEIGHT = 0.07                  # Meters: whatever is below this, inside the ring, is ash.
ASH_RADIUS = 0.62                  # Fraction of the ring's radius.


def load(name):
    with bpy.data.libraries.load(os.path.join(OBJ, "campfire_parts", name + ".blend")) as (src, dst):
        dst.objects = list(src.objects)
    obj = next(o for o in dst.objects if o is not None and o.type == "MESH")
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (0, 0, 0)
    return obj


def _linear(color):
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color]


def paint_ring(ring):
    """Stones in a warm gray and, inside the ring and low down, the ash."""
    me = ring.data
    co = np.array([v.co for v in me.vertices])
    radius = np.abs(co[:, :2]).max()
    stone, ash = _linear(STONE), _linear(ASH)
    attr = me.color_attributes["Color"]
    painted = 0
    for poly in me.polygons:
        c = poly.center
        is_ash = c.z < ASH_HEIGHT and np.hypot(c.x, c.y) < radius * ASH_RADIUS
        col = ash if is_ash else stone
        for li in poly.loop_indices:
            attr.data[li].color = (col[0], col[1], col[2], attr.data[li].color[3])
        painted += is_ash
    return painted


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ring = load("campfire_stones")
    logs = load("campfire_logs")
    print("ASH faces", paint_ring(ring))
    # The logs, sunk a little into the ash so they don't float.
    logs.location = (0, 0, 0.02)
    bpy.ops.object.select_all(action="DESELECT")
    logs.select_set(True)
    ring.select_set(True)
    bpy.context.view_layer.objects.active = ring
    bpy.ops.object.join()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ring.name = ring.data.name = "campfire"
    print("CAMPFIRE size", tuple(round(v, 2) for v in ring.dimensions))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OBJ, "campfire.blend"), copy=True)


main()
