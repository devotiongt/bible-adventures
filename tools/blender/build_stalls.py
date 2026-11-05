"""Builds the four market stalls from the empty stall and the goods, generated separately
(references/market_parts.png, processed with process_generated.py; the pieces go in
tools/blender/objects/stall_parts/).

Usage (without opening Blender):
    blender --background --factory-startup --python tools/blender/build_stalls.py

For each stall: copies the empty stall, paints its awning (the cloth faces, alpha 0) in the stall's color
(the cream stripes are drawn by the game's shader), and places its goods on the counter.
Saves tools/blender/objects/<type>_stall.blend; then it is exported with export_objects.py.
"""

import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OBJ = os.path.join(ROOT, "tools/blender/objects")

# Awning color (sRGB) and goods: (piece, x, y, rotation in degrees, scale), as a fraction of the counter
# (x from -1 to 1 across the width, y from -1 in front to 1 behind).
STALLS = {
    "pottery_stall": ((0.86, 0.38, 0.35), [("jugs", -0.35, 0.0, 10, 0.75), ("jugs", 0.4, 0.05, 200, 0.65)]),
    "cloth_stall": ((0.38, 0.58, 0.80), [("cream_rolls", -0.42, 0.05, 0, 1.0), ("folded_cloths", 0.45, -0.05, -8, 1.0)]),
    "cloth_stall2": ((0.36, 0.70, 0.72), [("colored_rolls", -0.42, 0.05, 0, 1.0), ("folded_cloths", 0.45, -0.05, 6, 1.0)]),
    "fruit_stall": ((0.50, 0.70, 0.30), [("apple_crate", -0.48, -0.25, 2, 0.95), ("orange_crate", 0.48, -0.25, -3, 0.95),
                                         ("pear_crate", -0.48, 0.45, -2, 0.95), ("grape_crate", 0.48, 0.45, 4, 0.95)]),
}


def load(name):
    # The stall pieces are in objects/stall_parts/; the jugs, in objects/ (they're also used on their own).
    path = os.path.join(OBJ, "stall_parts", name + ".blend")
    if not os.path.exists(path):
        path = os.path.join(OBJ, name + ".blend")
    with bpy.data.libraries.load(path) as (src, dst):
        dst.objects = list(src.objects)
    obj = next(o for o in dst.objects if o is not None and o.type == "MESH")
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (0, 0, 0)
    return obj


def counter(stall):
    """Height of the counter surface, and half width and half depth of the free area between the posts."""
    co = np.array([v.co for v in stall.data.vertices])
    h0, h1 = co[:, 2].min(), co[:, 2].max()
    ups = [f.center.z for f in stall.data.polygons
           if f.normal.z > 0.85 and h0 + (h1 - h0) * 0.25 < f.center.z < h0 + (h1 - h0) * 0.55
           and abs(f.center.x) < np.abs(co[:, 0]).max() * 0.6]
    hist, edges = np.histogram(ups, bins=30)
    top = float(edges[hist.argmax()] + (edges[1] - edges[0]) / 2)
    return top, np.abs(co[:, 0]).max() * 0.72, np.abs(co[:, 1]).max() * 0.55


# New awning (the generated one came out fused with the posts). Measurements of the empty stall, in meters.
CUT = 1.2                       # Everything above this is removed (cloth and post tips).
POST_X, POST_Y, POST_R = 1.01, 0.585, 0.105
AWNING_FRONT, AWNING_BACK = 1.92, 2.18      # Awning height in front and behind (it slopes forward).
AWNING_X, AWNING_Y0, AWNING_Y1 = 1.19, -0.86, 0.78
WAVE = 0.34                     # Width of each wave of the valance: same as a stripe (shaders/props.gdshader).
WOOD = (0.62, 0.40, 0.24)


def _colored(bm_fill, color, alpha):
    me = bpy.data.meshes.new("piece")
    bm = bmesh.new()
    bm_fill(bm)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("piece", me)
    bpy.context.scene.collection.objects.link(obj)
    attr = me.color_attributes.new("Color", "BYTE_COLOR", "CORNER")
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color]
    for d in attr.data:
        d.color = (lin[0], lin[1], lin[2], alpha)
    for f in me.polygons:
        f.use_smooth = True
    return obj


def _cut_top(stall):
    bm = bmesh.new()
    bm.from_mesh(stall.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z > CUT], context="FACES")
    bm.to_mesh(stall.data)
    bm.free()


def _awning_height(y):
    t = (y - AWNING_Y0) / (AWNING_Y1 - AWNING_Y0)
    return AWNING_FRONT + (AWNING_BACK - AWNING_FRONT) * t + 0.07 * np.sin(np.pi * t)   # Slightly bulged.


def _new_top(color):
    """Post tops, beams and the awning with its wavy valance in front (alpha 0: the shader adds
    the stripes)."""
    parts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            top = _awning_height(sy * POST_Y) - 0.04

            def post(bm, sx=sx, sy=sy, top=top):
                # Starts below the cut to hide the joint with the generated post.
                bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=POST_R, radius2=POST_R * 0.85,
                                      depth=top - CUT + 0.2)
                bmesh.ops.translate(bm, vec=(sx * POST_X, sy * POST_Y, (top + CUT - 0.2) / 2), verts=bm.verts)
            parts.append(_colored(post, WOOD, 1.0))
    for sy in (-1, 1):
        def beam(bm, sy=sy):
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.055, radius2=0.055, depth=POST_X * 2 + 0.3)
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(np.pi / 2, 3, "Y"))
            bmesh.ops.translate(bm, vec=(0, sy * POST_Y, _awning_height(sy * POST_Y) - 0.07), verts=bm.verts)
        parts.append(_colored(beam, WOOD, 1.0))

    def cloth(bm):
        nx, ny = 56, 18
        xs = np.linspace(-AWNING_X, AWNING_X, nx + 1)
        ys = np.linspace(AWNING_Y0, AWNING_Y1, ny + 1)
        grid = [[bm.verts.new((x, y, _awning_height(y))) for x in xs] for y in ys]
        for j in range(ny):
            for i in range(nx):
                bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
        # Valance in front: hangs down and ends in waves (one per stripe).
        front = grid[0]
        top_z = _awning_height(AWNING_Y0)
        low = []
        for i, x in enumerate(xs):
            u = ((x + AWNING_X) / WAVE) % 1.0 * 2.0 - 1.0
            drop = 0.12 + 0.09 * np.sqrt(max(0.0, 1.0 - u * u))
            low.append(bm.verts.new((x, AWNING_Y0 - 0.01, top_z - drop)))
        for i in range(nx):
            bm.faces.new((low[i], low[i + 1], front[i + 1], front[i]))
        # Cloth thickness.
        geom = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
        bmesh.ops.translate(bm, vec=(0, 0.0, -0.03),
                            verts=[v for v in geom["geom"] if isinstance(v, bmesh.types.BMVert)])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    parts.append(_colored(cloth, color, 0.0))
    return parts


def paint_awning(obj, color):
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color]
    attr = obj.data.color_attributes["Color"]
    for d in attr.data:
        if d.color[3] < 0.35:
            d.color = (lin[0], lin[1], lin[2], d.color[3])


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for name, (awning, goods) in STALLS.items():
        stall = load("empty_stall")
        stall.data = stall.data.copy()
        top, xh, yh = counter(stall)
        _cut_top(stall)
        parts = _new_top(awning)
        for piece, fx, fy, rot, scale in goods:
            g = load(piece)
            g.data = g.data.copy()
            g.scale = (scale, scale, scale)
            g.rotation_euler = (0, 0, np.radians(rot))
            g.location = (fx * xh, fy * yh, top - 0.005)
            parts.append(g)
        bpy.ops.object.select_all(action="DESELECT")
        for o in parts:
            o.select_set(True)
        stall.select_set(True)
        bpy.context.view_layer.objects.active = stall
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        bpy.ops.object.join()
        stall.name = name
        stall.data.name = name
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OBJ, name + ".blend"), copy=True)
        print("STALL", name, "counter at", round(top, 2), "m")
        bpy.ops.wm.read_factory_settings(use_empty=True)


main()
