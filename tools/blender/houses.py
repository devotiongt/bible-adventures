"""Adobe houses and objects of Noah's village (docs/DESIGN_CHAPTER1.md), exported to glTF.

Usage (without opening Blender):
    blender --background --factory-startup --python tools/blender/houses.py -- assets/village/village.glb [renders_folder]

Each object in the file is a piece with its origin on the ground, at the center, and with its front
(the door) facing -Y, which in Godot is +Z. Measurements in meters, against Noah (1.55 m):
    NoahHouse      8 × 5 m, 2.6 m walls, yard with a low wall in front
    HouseA/B/C     5 × 4 m, 2.4 m walls (B with stairs to the roof, C with an awning)
    Well           Ø 1.4 m, 0.7 m curb, crossbar and bucket
    Oven           clay tannur, Ø 0.8 m, 0.9 m tall
    Bench, Jug, Basket, Firewood, Fence (2 m section), Stall (potter)
"""

import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

random.seed(3)

COLORS = {
    "Adobe": (0.76, 0.49, 0.31),
    "AdobeShade": (0.68, 0.43, 0.27),
    "Plinth": (0.66, 0.42, 0.27),
    "Roof": (0.84, 0.59, 0.39),
    "Wood": (0.58, 0.39, 0.24),
    "WoodDark": (0.43, 0.28, 0.17),
    "Hollow": (0.25, 0.18, 0.14),
    "Clay": (0.79, 0.56, 0.38),
    "Stone": (0.70, 0.67, 0.75),
    "ClothPink": (0.91, 0.64, 0.56),
    "ClothBlue": (0.62, 0.72, 0.79),
    "Rope": (0.62, 0.50, 0.33),
    "Wicker": (0.80, 0.66, 0.42),
    "Sack": (0.86, 0.79, 0.63),
    "ClothGreen": (0.62, 0.73, 0.52),
    "ClothOchre": (0.88, 0.70, 0.40),
    "Fire": (0.98, 0.62, 0.28),
    "Pitch": (0.20, 0.15, 0.12),
    "Water": (0.55, 0.76, 0.82),
    "ClothRed": (0.86, 0.38, 0.35),
    "ClothCream": (0.97, 0.92, 0.84),
    "ClothBlueStrong": (0.38, 0.58, 0.80),
    "StoneGray": (0.62, 0.62, 0.64),
    "StoneWell": (0.55, 0.52, 0.48),
    "StoneWellDark": (0.36, 0.34, 0.31),
    "WellSlab": (0.60, 0.56, 0.51),
    "WellWater": (0.16, 0.26, 0.32),
    "Metal": (0.40, 0.40, 0.44),
    "Cord": (0.78, 0.63, 0.40),
    "WoodCut": (0.86, 0.68, 0.47),
    "CutRing": (0.74, 0.55, 0.36),
    "Bark": (0.50, 0.31, 0.19),
    "StoneCampfire": (0.60, 0.57, 0.54),
    "StoneCampfireDark": (0.48, 0.45, 0.43),
    "Ember": (0.95, 0.42, 0.15),
    "Ash": (0.42, 0.38, 0.35),
    "Flame": (1.00, 0.78, 0.25),
    "FlameOuter": (0.98, 0.48, 0.13),
    "WickerDark": (0.63, 0.47, 0.27),
    "Apple": (0.86, 0.20, 0.17),
    "Orange": (0.98, 0.56, 0.13),
    "Pear": (0.70, 0.80, 0.26),
    "Grape": (0.52, 0.26, 0.60),
    "Leaf": (0.36, 0.62, 0.20),
    "TroughWater": (0.38, 0.52, 0.60),
    "ThreadCream": (0.93, 0.88, 0.78),
    "ClothRedLoom": (0.80, 0.33, 0.27),
    "TarpCream": (0.88, 0.79, 0.62),
    "TarpBlue": (0.43, 0.60, 0.74),
    "TarpGreen": (0.56, 0.66, 0.50),
    "TarpSage": (0.68, 0.72, 0.62),
    "TarpGray": (0.60, 0.63, 0.58),
}


def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        # The colors above are in sRGB; Blender works in linear.
        linear = tuple(c ** 2.2 for c in COLORS[name])
        bsdf.inputs["Base Color"].default_value = (*linear, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.9
        mat.diffuse_color = (*linear, 1.0)
        if name in ("Flame", "FlameOuter", "Ember"):            # Fire glows.
            bsdf.inputs["Emission Color"].default_value = (*linear, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 1.5
    return mat


# --- Basic pieces -------------------------------------------------------------

def _finish(obj, mat, bevel=0.0, segments=3, smooth=False):
    obj.data.materials.append(material(mat))
    if bevel > 0.0:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = segments
        mod.limit_method = "ANGLE"
    for p in obj.data.polygons:
        p.use_smooth = smooth
    return obj


def box(name, size, loc, mat, bevel=0.0, rot=(0, 0, 0), taper=0.0, smooth=False, segments=3):
    """Box with the center of its base at `loc`. taper: how much it narrows at the top (adobe walls)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z = (v.co.z + 0.5) * size[2]
        if taper and v.co.z > size[2] * 0.5:
            v.co.x -= math.copysign(taper, v.co.x)
            v.co.y -= math.copysign(taper, v.co.y)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    obj.rotation_euler = rot
    bpy.context.collection.objects.link(obj)
    return _finish(obj, mat, bevel, segments=segments, smooth=smooth)


def cylinder(name, radius, depth, loc, mat, verts=16, rot=(0, 0, 0), top_radius=None, bevel=0.0, smooth=True):
    """Cylinder with its base at `loc` (rises along +Z before rotating)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=radius,
                          radius2=radius if top_radius is None else top_radius, depth=depth)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, depth * 0.5))
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    obj.rotation_euler = rot
    bpy.context.collection.objects.link(obj)
    return _finish(obj, mat, bevel, smooth=smooth)


def lathe(name, profile, loc, mat, verts=20):
    """Lathe piece (jugs, oven): profile [(radius, height), ...] from bottom to top."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        ring = [bm.verts.new((r * math.cos(2 * math.pi * i / verts), r * math.sin(2 * math.pi * i / verts), z))
                for i in range(verts)]
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for i in range(verts):
            bm.faces.new((a[i], a[(i + 1) % verts], b[(i + 1) % verts], b[i]))
    bm.faces.new(list(reversed(rings[0])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    bpy.context.collection.objects.link(obj)
    return _finish(obj, mat, smooth=True)


def join(name, parts):
    """Joins the pieces (applying their modifiers) into a single object with its origin on the ground."""
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    for p in parts:
        bpy.context.view_layer.objects.active = p
        for m in list(p.modifiers):
            bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


# --- Houses -------------------------------------------------------------------

# Clay houses (references/adobe_houses.jpg and noah_house.jpg): very rounded blocks, as if
# modeled by hand, with a thick parapet, protruding beams, sunken framed windows, plank doors
# with a stone step, adobe stairs, ladders, striped awnings and low yard walls
# that hug the house.

def clay(name, w, d, h, loc, mat="Adobe"):
    """Adobe block with very rounded edges and barely sloped walls."""
    return box(name, (w, d, h), loc, mat, bevel=min(0.32, h * 0.16, w * 0.12), taper=0.05, smooth=True,
               segments=4)


def roof(name, w, d, x, y, z):
    """Thick rounded parapet around the flat roof, with the slab a bit lighter."""
    parts = [box(f"{name}_slab", (w - 0.3, d - 0.3, 0.06), (x, y, z - 0.02), "Roof", bevel=0.02)]
    for sy in (-1, 1):
        parts.append(box(f"{name}_parapetx{sy}", (w, 0.3, 0.32), (x, y + sy * (d * 0.5 - 0.15), z - 0.12), "Adobe",
                         bevel=0.13, smooth=True, segments=3))
    for sx in (-1, 1):
        parts.append(box(f"{name}_parapety{sx}", (0.3, d, 0.32), (x + sx * (w * 0.5 - 0.15), y, z - 0.12), "Adobe",
                         bevel=0.13, smooth=True, segments=3))
    return parts


def beams(name, w, d, x, y, z, sides=("front", "back")):
    """Row of wooden beams protruding under the parapet."""
    parts = []
    n = max(2, int(w / 0.95))
    for side in sides:
        if side in ("front", "back"):
            sy = -1 if side == "front" else 1
            for i in range(n):
                bx = x - w * 0.5 + (i + 0.5) * w / n
                # They start inside the wall and stick out about 35 cm.
                parts.append(cylinder(f"{name}_beam{side}{i}", 0.085, 0.5, (bx, y + sy * (d * 0.5 - 0.15), z),
                                      "WoodDark", verts=8, rot=(math.radians(-90) * sy, 0, 0)))
        else:
            sx = -1 if side == "left" else 1
            m = max(2, int(d / 0.95))
            for i in range(m):
                by = y - d * 0.5 + (i + 0.5) * d / m
                parts.append(cylinder(f"{name}_beam{side}{i}", 0.085, 0.5, (x + sx * (w * 0.5 - 0.15), by, z),
                                      "WoodDark", verts=8, rot=(0, math.radians(90) * sx, 0)))
    return parts


def window(name, x, y, z, face=-1, size=(0.55, 0.55)):
    """Small sunken window, with a wooden frame. face: -1 front (-Y), 1 back."""
    fy = y + face * 0.02
    parts = [box(f"{name}_hollow", (size[0], 0.3, size[1]), (x, fy, z), "Hollow", bevel=0.04)]
    for dz, hh in ((-0.08, 0.1), (size[1] - 0.02, 0.1)):
        parts.append(box(f"{name}_frameh{dz}", (size[0] + 0.3, 0.16, hh), (x, fy + face * 0.07, z + dz), "Wood",
                         bevel=0.025))
    for sx in (-1, 1):
        parts.append(box(f"{name}_framev{sx}", (0.1, 0.16, size[1]), (x + sx * (size[0] * 0.5 + 0.05), fy + face * 0.07, z),
                         "Wood", bevel=0.02))
    return parts


def door(name, x, y, face=-1, w=1.0, h=1.85):
    """Plank door with its frame, lintel and stone step."""
    fy = y + face * 0.02
    parts = [box(f"{name}_hollow", (w + 0.1, 0.3, h + 0.05), (x, fy, 0.1), "Hollow", bevel=0.04),
             box(f"{name}_leaf", (w - 0.08, 0.08, h - 0.08), (x, fy + face * 0.1, 0.14), "Wood", bevel=0.02)]
    for i in range(3):
        parts.append(box(f"{name}_seam{i}", (0.025, 0.09, h - 0.2), (x - w * 0.25 + i * w * 0.25, fy + face * 0.13, 0.2),
                         "WoodDark"))
    parts.append(cylinder(f"{name}_knob", 0.04, 0.06, (x + w * 0.32, fy + face * 0.15, 0.95), "WoodDark", verts=8,
                          rot=(math.radians(90) * -face, 0, 0)))
    parts.append(box(f"{name}_lintel", (w + 0.5, 0.24, 0.16), (x, fy + face * 0.09, h + 0.12), "WoodDark", bevel=0.04))
    for sx in (-1, 1):
        parts.append(box(f"{name}_jamb{sx}", (0.12, 0.2, h), (x + sx * (w * 0.5 + 0.08), fy + face * 0.08, 0.12), "Wood",
                         bevel=0.03))
    parts.append(box(f"{name}_step", (w + 0.5, 0.55, 0.14), (x, y + face * 0.32, 0), "StoneGray", bevel=0.05,
                     smooth=True))
    return parts


def stair(name, x, y0, y1, h, width=0.9, mat="AdobeShade"):
    """Adobe stairs against a wall: rises from y0 (bottom) to y1 (top) up to height h."""
    parts = []
    steps = max(4, int(h / 0.3))
    for i in range(steps):
        t = (i + 1) / steps
        sy = y0 + (y1 - y0) * (i + 0.5) / steps
        parts.append(box(f"{name}_step{i}", (width, abs(y1 - y0) / steps + 0.02, h * t), (x, sy, 0), mat, bevel=0.06,
                         smooth=True))
    # Side wall of the stairs, as a ramp (more rounded: looks hand-modeled).
    return parts


def ladder(name, x, y, z, height, lean=0.25, rot_z=0.0):
    """Leaning ladder (tilts toward +Y before rotating rot_z)."""
    parts = []
    for sx in (-1, 1):
        parts.append(cylinder(f"{name}_rail{sx}", 0.045, height, (x + sx * 0.22, y, z), "Wood", verts=6,
                              rot=(-lean, 0, rot_z)))
    steps = int(height / 0.35)
    for i in range(steps):
        zz = z + (i + 0.6) * height / steps * math.cos(lean)
        yy = y + (i + 0.6) * height / steps * math.sin(lean)
        parts.append(cylinder(f"{name}_rung{i}", 0.03, 0.48, (x - 0.24, yy, zz), "WoodDark", verts=6,
                              rot=(0, math.radians(90), rot_z)))
    return parts


def striped(name, w, d, loc, colors, tilt=0.0, stripes=6, along_x=True):
    """Striped cloth (awning): alternating bands of two colors, slightly tilted."""
    parts = []
    for i in range(stripes):
        t = (i + 0.5) / stripes - 0.5
        if along_x:
            off, size = (t * w, 0, 0), (w / stripes + 0.005, d, 0.04)
        else:
            off, size = (0, t * d, 0), (w, d / stripes + 0.005, 0.04)
        parts.append(box(f"{name}_stripe{i}", size, (loc[0] + off[0], loc[1] + off[1], loc[2]), colors[i % 2], bevel=0.01,
                         rot=(tilt, 0, 0)))
    return parts


def shade(name, w, d, x, y, z, colors=("ClothRed", "ClothCream")):
    """Striped cloth shade on four posts (on the roof)."""
    parts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(cylinder(f"{name}_post{sx}{sy}", 0.05, 1.7, (x + sx * w * 0.5, y + sy * d * 0.5, z), "Wood",
                                  verts=8))
    parts += striped(f"{name}_cloth", w + 0.2, d + 0.1, (x, y, z + 1.66), colors, stripes=7)
    return parts


def yard_wall(name, points, h=0.95, t=0.38, mat="Adobe"):
    """Low yard wall along a polyline of points (x, y): rounded sections and post joints."""
    parts = []
    for i in range(len(points) - 1):
        (ax, ay), (bx, by) = points[i], points[i + 1]
        length = math.hypot(bx - ax, by - ay)
        ang = math.atan2(by - ay, bx - ax)
        parts.append(box(f"{name}_section{i}", (length + t * 0.6, t, h), ((ax + bx) * 0.5, (ay + by) * 0.5, 0), mat,
                         bevel=0.15, smooth=True, segments=3, rot=(0, 0, ang)))
    return parts


def build_houses():
    houses = []
    # A: one block with outside stairs to the roof and a striped shade on top; a low bench at the foot.
    w, d, h = 4.6, 3.8, 2.5
    p = [clay("HouseA_block", w, d, h, (0, 0, 0))] + roof("HouseA_roof", w, d, 0, 0, h)
    p += beams("HouseA", w, d, 0, 0, h - 0.4, ("front", "back", "left"))
    p += door("HouseA_door", -0.5, -d * 0.5)
    p += window("HouseA_win1", 1.25, -d * 0.5, 1.15)
    p += window("HouseA_win2", -0.9, d * 0.5, 1.2, face=1) + window("HouseA_win3", 0.9, d * 0.5, 1.2, face=1)
    p += stair("HouseA_stairs", w * 0.5 + 0.45, -d * 0.5 + 0.2, d * 0.5 - 0.1, h)
    p.append(clay("HouseA_bench", 1.6, 0.6, 0.45, (-w * 0.5 + 0.6, -d * 0.5 - 0.3, 0), "AdobeShade"))
    p += shade("HouseA_shade", 2.6, 1.8, -0.6, 0.5, h)
    houses.append(join("HouseA", p))

    # B: two stories (upper block at the back left), a ladder and a yard with a low wall in front.
    w, d, h = 5.6, 4.2, 2.2
    p = [clay("HouseB_low", w, d, h, (0, 0, 0))] + roof("HouseB_roof", w, d, 0, 0, h)
    p += beams("HouseB", w, d, 0, 0, h - 0.38, ("front", "back"))
    p += [clay("HouseB_high", 2.8, 3.0, 1.8, (-1.2, 0.5, h))] + roof("HouseB_roof2", 2.8, 3.0, -1.2, 0.5, h + 1.8)
    p += beams("HouseB_high", 2.8, 3.0, -1.2, 0.5, h + 1.4, ("front",))
    p += window("HouseB_win_upper", -1.2, -1.0, h + 0.75)
    p += door("HouseB_door", -1.2, -d * 0.5)
    p += window("HouseB_win1", 1.6, -d * 0.5, 1.05)
    p += ladder("HouseB_stairs", 0.55, -0.6, h - 0.05, 2.1, lean=0.0, rot_z=0.0)
    p += yard_wall("HouseB_yard", [(-w * 0.5 + 0.2, -d * 0.5), (-w * 0.5 + 0.2, -d * 0.5 - 2.4), (-0.9, -d * 0.5 - 2.4)])
    p += yard_wall("HouseB_yard2", [(0.5, -d * 0.5 - 2.4), (w * 0.5 - 0.2, -d * 0.5 - 2.4), (w * 0.5 - 0.2, -d * 0.5)])
    houses.append(join("HouseB", p))

    # C: one block with a striped awning over the door, a bench with flowerpots in front and a yard behind.
    w, d, h = 4.4, 3.6, 2.4
    p = [clay("HouseC_block", w, d, h, (0, 0, 0))] + roof("HouseC_roof", w, d, 0, 0, h)
    p += beams("HouseC", w, d, 0, 0, h - 0.4, ("front", "left", "right"))
    p += door("HouseC_door", 0.0, -d * 0.5)
    p += window("HouseC_win1", 1.45, -d * 0.5, 1.15)
    p += window("HouseC_win2", 1.0, d * 0.5, 1.2, face=1)
    p += striped("HouseC_awning", 1.9, 1.0, (0.0, -d * 0.5 - 0.5, 2.25), ("ClothBlueStrong", "ClothCream"),
                 tilt=math.radians(-18), stripes=6)
    for sx in (-1, 1):
        p.append(cylinder(f"HouseC_post{sx}", 0.045, 2.15, (sx * 0.95, -d * 0.5 - 0.95, 0), "Wood", verts=8))
    p.append(clay("HouseC_bench", 4.0, 0.55, 0.42, (0, -d * 0.5 - 0.28, 0), "AdobeShade"))
    p += yard_wall("HouseC_yard", [(-w * 0.5 + 0.2, d * 0.5), (-w * 0.5 + 0.2, d * 0.5 + 2.2), (w * 0.5 - 0.2, d * 0.5 + 2.2),
                                   (w * 0.5 - 0.2, d * 0.5)])
    houses.append(join("HouseC", p))

    # Noah's house (references/noah_house.jpg): wide ground floor, set-back upper floor with a striped
    # shade, outside stairs to the ground floor's roof and another to the upper one, and a yard in front with a low wall and gate.
    w, d, h = 7.0, 5.0, 2.4
    p = [clay("NoahHouse_low", w, d, h, (0, 0, 0))] + roof("NoahHouse_roof", w, d, 0, 0, h)
    p += beams("NoahHouse", w, d, 0, 0, h - 0.4, ("front", "back", "left"))
    uw, ud, uh = 4.2, 3.2, 2.1
    p += [clay("NoahHouse_high", uw, ud, uh, (-0.8, 0.8, h))] + roof("NoahHouse_roof2", uw, ud, -0.8, 0.8, h + uh)
    p += beams("NoahHouse_high", uw, ud, -0.8, 0.8, h + uh - 0.4, ("front", "left"))
    p += door("NoahHouse_door_upper", -1.4, 0.8 - ud * 0.5, w=0.9, h=1.6)
    for part in p[-10:]:
        part.location.z += h
    p += window("NoahHouse_win_upper", 0.4, 0.8 - ud * 0.5, h + 1.0)
    p += door("NoahHouse_door", -1.6, -d * 0.5)
    p += door("NoahHouse_door2", 1.7, -d * 0.5, w=0.9, h=1.7)
    p += window("NoahHouse_win1", -3.0, -d * 0.5, 1.15) + window("NoahHouse_win2", 0.1, -d * 0.5, 1.2)
    p += window("NoahHouse_win3", 2.6, d * 0.5, 1.2, face=1)
    p += stair("NoahHouse_stairs", w * 0.5 + 0.45, -d * 0.5 + 0.3, d * 0.5 - 0.1, h)
    p += [part for part in stair("NoahHouse_stairs2", 1.75, -0.6, 2.2, uh)]
    for part in p[-max(4, int(uh / 0.3)):]:
        part.location.z += h
    p += shade("NoahHouse_shade", 2.4, 1.6, -1.2, 1.1, h + uh)
    yard = -d * 0.5 - 4.0
    p += yard_wall("NoahHouse_yard", [(-w * 0.5 + 0.1, -d * 0.5), (-w * 0.5 - 0.4, -d * 0.5), (-w * 0.5 - 0.4, yard),
                                     (-0.6, yard)])
    p += yard_wall("NoahHouse_yard2", [(0.9, yard), (w * 0.5 + 0.9, yard), (w * 0.5 + 0.9, -d * 0.5 - 0.2)])
    for sx in (-0.6, 0.9):
        p.append(clay(f"NoahHouse_pillar{sx}", 0.55, 0.55, 1.35, (sx, yard, 0), "Adobe"))
    houses.append(join("NoahHouse", p))
    return houses


# --- Objects ------------------------------------------------------------------

def build_well():
    """Plaza well (references/cutouts/well.png), piece by piece and each in its own color: base of
    rounded slabs, curb of three courses of blocks (staggered like a wall), water, two posts,
    crossbar with the rope coiled on it, the rope going down, the stave bucket with metal hoops and the crank."""
    rnd = random.Random(11)
    p = []
    # Base: ring of slabs around the curb.
    p.append(cylinder("Well_base", 1.25, 0.08, (0, 0, 0), "StoneWellDark", verts=24, bevel=0.03))
    n = 14
    for i in range(n):
        a = 2 * math.pi * (i + 0.5) / n
        r = 1.0
        p.append(box(f"Well_slab{i}", (0.42, 2 * math.pi * r / n - 0.06, 0.1), (math.cos(a) * r, math.sin(a) * r, 0.06),
                     "WellSlab", bevel=0.045, smooth=True, rot=(0, 0, a + rnd.uniform(-0.04, 0.04))))
    # Curb: three courses of blocks, each turned half a piece from the one below.
    radius, bh, blocks = 0.62, 0.22, 11
    for row in range(3):
        for i in range(blocks):
            a = 2 * math.pi * (i + 0.5 * (row % 2)) / blocks
            w = 2 * math.pi * radius / blocks - 0.035
            p.append(box(f"Well_block{row}_{i}", (0.24, w, bh - 0.03),
                         (math.cos(a) * radius, math.sin(a) * radius, 0.14 + row * bh),
                         "StoneWell", bevel=0.05, smooth=True, rot=(0, 0, a + rnd.uniform(-0.03, 0.03))))
    # Curb cap and dark filling between blocks (the joints).
    p.append(lathe("Well_joints", [(0.5, 0.14), (0.72, 0.14), (0.72, 0.8), (0.5, 0.8)], (0, 0, 0), "StoneWellDark",
                   verts=28))
    for i in range(blocks):
        a = 2 * math.pi * i / blocks
        p.append(box(f"Well_cap{i}", (0.3, 2 * math.pi * radius / blocks - 0.03, 0.09),
                     (math.cos(a) * radius, math.sin(a) * radius, 0.8), "StoneWell", bevel=0.04, smooth=True,
                     rot=(0, 0, a)))
    p.append(cylinder("Well_water", 0.5, 0.02, (0, 0, 0.45), "WellWater", verts=24))
    # Posts and crossbar.
    for side in (-1, 1):
        p.append(box(f"Well_post{side}", (0.2, 0.2, 2.05), (side * 0.9, 0, 0.06), "Wood", bevel=0.04, taper=0.015))
        p.append(box(f"Well_cap_post{side}", (0.26, 0.26, 0.08), (side * 0.9, 0, 2.08), "WoodDark", bevel=0.03))
    p.append(cylinder("Well_crossbar", 0.075, 2.25, (-1.12, 0, 1.86), "Wood", verts=10, rot=(0, math.radians(90), 0)))
    # Rope coiled at the middle of the crossbar and the one going down to the bucket.
    for i in range(5):
        p.append(cylinder(f"Well_coil{i}", 0.098, 0.05, (-0.13 + i * 0.055, 0, 1.86), "Cord", verts=12,
                          rot=(0, math.radians(90), 0)))
    p.append(cylinder("Well_cord", 0.02, 0.58, (0, 0, 1.22), "Cord", verts=6))
    # Bucket: wooden staves, two metal hoops and the handle.
    p.append(lathe("Well_bucket", [(0.0, 0.0), (0.13, 0.0), (0.15, 0.24), (0.14, 0.25), (0.0, 0.25)], (0, 0, 0.95),
                   "Wood", verts=12))
    for z in (0.99, 1.15):
        p.append(cylinder(f"Well_hoop{z}", 0.15 if z > 1 else 0.138, 0.03, (0, 0, z), "Metal", verts=16))
    p.append(torus_part("Well_handle", 0.15, 0.012, (0, 0, 1.2), "Metal"))
    # Crank on the right post.
    p.append(box("Well_crank_arm", (0.06, 0.06, 0.32), (1.06, 0, 1.7), "WoodDark", bevel=0.015))
    p.append(cylinder("Well_crank_grip", 0.03, 0.22, (1.06, 0, 1.72), "Wood", verts=8, rot=(0, math.radians(90), 0)))
    return join("Well", p)


def ball(name, r, loc, mat, scale=(1, 1, 1), segments=10):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=max(6, segments * 2 // 3), radius=r)
    bmesh.ops.scale(bm, vec=scale, verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    bpy.context.collection.objects.link(obj)
    return _finish(obj, mat, smooth=True)


def log(name, r, length, center, yaw=0.0, pitch=0.0, bark="Bark", cut="WoodCut", bevel=0.02):
    """Log: bark cylinder with the two cut faces lighter. Runs along X, rotated
    `yaw` around Z and tilted `pitch` (upward)."""
    d = Vector((math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch)))
    c = Vector(center)
    rot = (0, math.radians(90) - pitch, yaw)
    parts = [cylinder(f"{name}_bark", r, length, tuple(c - d * length / 2), bark, verts=10, rot=rot, bevel=bevel)]
    for k, sgn in enumerate((1, -1)):
        start = c + d * (length / 2) if sgn > 0 else c - d * (length / 2 + 0.012)
        parts.append(cylinder(f"{name}_cut{k}", r * 0.86, 0.012, tuple(start), cut, verts=10, rot=rot))
    return parts


def build_campfire():
    """Campfire (references/cutouts/campfire.png): ring of rounded two-tone stones, bed of
    ash with embers and logs in a tipi. No flame: the fire is separate, animated in the game."""
    rnd = random.Random(5)
    p = [lathe("Campfire_ash", [(0.0, 0.0), (0.4, 0.0), (0.33, 0.03), (0.18, 0.05), (0.0, 0.055)], (0, 0, 0),
               "Ash", verts=18)]
    n = 11
    for i in range(n):
        a = 2 * math.pi * i / n + rnd.uniform(-0.06, 0.06)
        sz = rnd.uniform(0.2, 0.26)
        p.append(box(f"Campfire_stone{i}", (sz, sz * rnd.uniform(0.8, 0.95), sz * 0.7),
                     (math.cos(a) * 0.52, math.sin(a) * 0.52, -0.02),
                     "StoneCampfire" if i % 3 else "StoneCampfireDark", bevel=sz * 0.35, smooth=True,
                     segments=3, rot=(0, rnd.uniform(-0.12, 0.12), a + rnd.uniform(-0.3, 0.3))))
    for i in range(7):
        a = rnd.uniform(0, 2 * math.pi)
        d = rnd.uniform(0.12, 0.3)
        p.append(ball(f"Campfire_ember{i}", rnd.uniform(0.025, 0.04), (math.cos(a) * d, math.sin(a) * d, 0.035),
                      "Ember", scale=(1.2, 1.0, 0.6), segments=8))
    # Logs in a tipi: resting on the ash and together at the top, over the fire.
    for i in range(5):
        a = 2 * math.pi * i / 5 + 0.3
        p += log(f"Campfire_log{i}", 0.045, 0.5, (math.cos(a) * 0.13, math.sin(a) * 0.13, 0.19),
                 yaw=a + math.pi, pitch=math.radians(50), bevel=0.012)
    return join("Campfire", p)


def build_baskets():
    """Three wicker baskets with fruit (references/cutouts/baskets.png): body, weave bands and
    rim darker, and the fruit peeking out."""
    rnd = random.Random(8)
    p = []
    fruits = (("Apple", "Orange", "Pear"), ("Pear", "Apple", "Orange"), ("Grape", "Pear", "Grape"))
    for b, (cx, cy) in enumerate(((-0.28, 0.12), (0.26, 0.2), (0.05, -0.24))):
        profile = [(0.0, 0.0), (0.15, 0.0), (0.2, 0.08), (0.23, 0.18), (0.22, 0.2)]
        p.append(lathe(f"Basket{b}_body", profile, (cx, cy, 0), "Wicker", verts=16))
        p.append(cylinder(f"Basket{b}_bottom", 0.2, 0.02, (cx, cy, 0.13), "WickerDark", verts=16))
        for z, r in ((0.07, 0.19), (0.13, 0.215)):
            p.append(torus_ring(f"Basket{b}_band{z}", r, 0.012, (cx, cy, z), "WickerDark"))
        p.append(torus_ring(f"Basket{b}_rim", 0.225, 0.022, (cx, cy, 0.2), "WickerDark"))
        # Pile of fruit: a ring of 7 by the rim and 3 on top, in the center.
        spots = [(2 * math.pi * k / 7, 0.13, 0.19) for k in range(7)] + \
                [(2 * math.pi * k / 3 + 0.5, 0.05, 0.25) for k in range(3)]
        for k, (a, d, z) in enumerate(spots):
            a += rnd.uniform(-0.2, 0.2)
            col = fruits[b][k % 3]
            r = 0.055 if col != "Grape" else 0.04
            x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
            p.append(ball(f"Basket{b}_fruit{k}", r, (x, y, z), col))
            if col in ("Apple", "Pear") and k % 2 == 0:
                p.append(cylinder(f"Basket{b}_stalk{k}", 0.008, 0.035, (x, y, z + r * 0.85), "WoodDark", verts=5))
        p.append(ball(f"Basket{b}_leaf", 0.04, (cx + 0.04, cy - 0.02, 0.31), "Leaf", scale=(1.4, 0.6, 0.25)))
    return join("Basket", p)


def build_firewood():
    """Stacked firewood (references/cutouts/firewood.png): logs in a pyramid (4, 3 and 2), with the light cut
    faces facing front and some variation in thickness and length."""
    rnd = random.Random(4)
    p = []
    for row, n in enumerate((4, 3, 2)):
        for i in range(n):
            r = rnd.uniform(0.085, 0.1)
            x = (i - (n - 1) / 2) * 0.19
            z = 0.095 + row * 0.165
            p += log(f"Firewood{row}_{i}", r, rnd.uniform(0.85, 0.95), (x, rnd.uniform(-0.04, 0.04), z),
                     yaw=math.radians(90), bevel=0.015)
    return join("Firewood", p)


def build_stump():
    """Stump to sit on by the fire: short trunk with a flared foot and roots, and the light cut face
    on top with its rings."""
    p = [cylinder("Stump_foot", 0.25, 0.12, (0, 0, 0), "Bark", verts=14, top_radius=0.2),
         cylinder("Stump_log", 0.2, 0.42, (0, 0, 0), "Bark", verts=14, top_radius=0.185, bevel=0.02),
         cylinder("Stump_cut", 0.172, 0.012, (0, 0, 0.42), "WoodCut", verts=14)]
    for z, r in ((0.432, 0.115), (0.432, 0.055)):
        p.append(torus_ring(f"Stump_ring{r}", r, 0.006, (0, 0, z), "CutRing"))
    for i, a in enumerate((0.3, 1.9, 3.3, 4.8)):
        root = ball(f"Stump_root{i}", 0.07, (math.cos(a) * 0.23, math.sin(a) * 0.23, 0.035), "Bark",
                    scale=(1.8, 0.9, 0.7), segments=8)
        root.rotation_euler = (0, 0, a)
        p.append(root)
    return join("Stump", p)


def build_log_seat():
    """Fallen log to sit on by the fire, with a branch stub at the back. Runs along X: the
    front (+Y in the game, -Y here) is the seat side."""
    p = log("LogSeat", 0.17, 1.05, (0, 0, 0.17), bevel=0.025)
    p += log("LogSeat_branch", 0.05, 0.16, (0.18, 0.2, 0.22), yaw=math.radians(70), pitch=math.radians(20),
             bevel=0.01)
    return join("LogSeat", p)


def build_canvas_stall(name, cloth, goods):
    """Canvas market stall (references/plaza_gemini.jpg): four posts, the tarp as a single slope
    (higher at the back) with a valance hanging in front, the counter with the goods and, on the ground, sacks,
    a big jug and a basket. Front toward -Y (in the game, +Z)."""
    rnd = random.Random(len(name))
    p = []
    for sx in (-1, 1):
        p.append(cylinder(f"{name}_post_back{sx}", 0.055, 2.36, (sx * 1.2, 0.85, 0), "Wood", verts=8))
        p.append(cylinder(f"{name}_post_front{sx}", 0.055, 1.98, (sx * 1.2, -0.9, 0), "Wood", verts=8))
    slope = math.atan2(0.42, 1.95)
    p.append(box(f"{name}_tarp", (2.8, 2.25, 0.05), (0, -0.05, 2.1), cloth, bevel=0.02, rot=(slope, 0, 0)))
    p.append(box(f"{name}_valance", (2.8, 0.04, 0.26), (0, -1.14, 1.72), cloth, bevel=0.015))
    for sx in (-1, 1):
        p.append(box(f"{name}_valance_side{sx}", (0.04, 2.0, 0.18), (sx * 1.4, -0.1, 1.98), cloth, bevel=0.015,
                     rot=(slope, 0, 0)))
    # Counter.
    p.append(box(f"{name}_counter", (2.2, 0.7, 0.08), (0, -0.5, 0.74), "Wood", bevel=0.02))
    p.append(box(f"{name}_front", (2.1, 0.04, 0.5), (0, -0.84, 0.25), "WoodDark", bevel=0.015))
    for sx in (-1, 1):
        p.append(box(f"{name}_leg{sx}", (0.08, 0.6, 0.74), (sx * 1.0, -0.5, 0), "WoodDark"))
    top = 0.82
    for i, g in enumerate(goods):
        x = -0.72 + i * 0.72
        if g in ("Apple", "Orange", "Pear", "Grape"):
            p.append(lathe(f"{name}_basket{i}", [(0.0, 0.0), (0.16, 0.0), (0.22, 0.09), (0.23, 0.15)], (x, -0.5, top),
                           "Wicker", verts=14))
            for k in range(7):
                a = 2 * math.pi * k / 7
                d = 0.11 if k else 0.0
                p.append(ball(f"{name}_fruit{i}{k}", 0.055 if g != "Grape" else 0.04,
                              (x + math.cos(a) * d, -0.5 + math.sin(a) * d, top + 0.15 + (0.04 if k == 0 else 0)), g))
        elif g == "Clay":
            for k, dx in enumerate((-0.14, 0.14)):
                prof = [(0.0, 0.0), (0.09, 0.0), (0.14, 0.08), (0.15, 0.18), (0.08, 0.3), (0.06, 0.34), (0.08, 0.37)]
                p.append(lathe(f"{name}_jar{i}{k}", prof, (x + dx, -0.45 - 0.08 * k, top), "Clay", verts=14))
        else:   # Folded cloths, one on top of another.
            for k in range(3):
                p.append(box(f"{name}_cloth{i}{k}", (0.5, 0.42, 0.07), (x, -0.5, top + k * 0.075), g, bevel=0.025,
                             rot=(0, 0, rnd.uniform(-0.08, 0.08))))
    # On the ground, to one side: open sacks, a big jug and a basket.
    for k, (sx, sy) in enumerate(((1.55, -0.55), (1.6, 0.05))):
        p.append(ball(f"{name}_sack{k}", 0.24, (sx, sy, 0.2), "Sack", scale=(1, 1, 1.15)))
        p.append(lathe(f"{name}_sack_mouth{k}", [(0.0, 0.0), (0.16, 0.0), (0.18, 0.06)], (sx, sy, 0.43), "Sack", verts=12))
        p.append(cylinder(f"{name}_grain{k}", 0.15, 0.03, (sx, sy, 0.47), "ClothOchre" if k else "Wicker", verts=12))
    p.append(lathe(f"{name}_jug", [(0.0, 0.0), (0.14, 0.0), (0.24, 0.16), (0.25, 0.32), (0.14, 0.52), (0.1, 0.58),
                                        (0.13, 0.62)], (-1.55, -0.4, 0), "Clay", verts=16))
    p.append(lathe(f"{name}_basket_ground", [(0.0, 0.0), (0.2, 0.0), (0.27, 0.12), (0.28, 0.22)], (-1.5, 0.3, 0), "Wicker",
                   verts=14))
    return join(name, p)


def barrel(name, center, scale=1.0):
    """Stave barrel: pot-bellied, with two dark hoops and the lid."""
    x, y = center
    h = 0.62 * scale
    prof = [(0.0, 0.0), (0.21 * scale, 0.0), (0.26 * scale, h * 0.25), (0.28 * scale, h * 0.5), (0.26 * scale, h * 0.75),
            (0.21 * scale, h), (0.0, h)]
    p = [lathe(f"{name}_body", prof, (x, y, 0), "Wood", verts=16)]
    for z, r in ((0.2, 0.27), (0.8, 0.27)):
        p.append(torus_ring(f"{name}_hoop{z}", r * scale, 0.018 * scale, (x, y, h * z), "WoodDark"))
    p.append(cylinder(f"{name}_lid", 0.19 * scale, 0.02, (x, y, h - 0.005), "WoodDark", verts=16))
    return p


def crate(name, center, size=0.55, rot=0.0, z=0.0, fruit=None):
    """Plank crate with a darker frame; open and with fruit if `fruit` is given."""
    x, y = center
    p = [box(f"{name}_box", (size, size * 0.8, size * 0.6), (x, y, z), "Wood", bevel=0.02, rot=(0, 0, rot))]
    for k in (0.33, 0.66):
        p.append(box(f"{name}_board{k}", (size + 0.01, size * 0.8 + 0.01, 0.02), (x, y, z + size * 0.6 * k), "WoodDark",
                     rot=(0, 0, rot)))
    if fruit:
        for i in range(6):
            fx, fy = (i % 3 - 1) * size * 0.27, (i // 3 - 0.5) * size * 0.3
            p.append(ball(f"{name}_fruit{i}", size * 0.12, (x + fx * math.cos(rot) - fy * math.sin(rot),
                                                            y + fx * math.sin(rot) + fy * math.cos(rot), z + size * 0.6),
                          fruit))
    return p


def build_barrels():
    """Market barrels: two together and a smaller one in front."""
    return join("Barrels", barrel("Barrel0", (0, 0)) + barrel("Barrel1", (0.56, 0.12)) +
                barrel("Barrel2", (0.3, -0.48), 0.8))


def build_crates():
    """Stacked market crates: two on the ground, one on top and another open with apples."""
    p = crate("Crate0", (0, 0)) + crate("Crate1", (0.6, 0.05), rot=0.1)
    p += crate("Crate2", (0.28, 0.02), z=0.33, rot=-0.15, size=0.5)
    p += crate("Crate3", (0.25, -0.62), rot=0.3, fruit="Apple")
    return join("Crates", p)


def build_cart():
    """Handcart of a wandering vendor: plank bed on two wheels, shafts to pull it and a
    stand in front; it carries jugs, a crate of oranges and a sack."""
    p = [box("Cart_box", (1.4, 0.9, 0.08), (0, 0, 0.5), "Wood", bevel=0.02)]
    for sy in (-1, 1):
        p.append(box(f"Cart_side{sy}", (1.4, 0.06, 0.22), (0, sy * 0.42, 0.58), "WoodDark", bevel=0.015))
        p.append(cylinder(f"Cart_wheel{sy}", 0.36, 0.08, (0.1, sy * 0.52, 0.36), "Wood", verts=16,
                          rot=(math.radians(90), 0, 0), bevel=0.02))
        p.append(cylinder(f"Cart_bucket{sy}", 0.08, 0.12, (0.1, sy * 0.55, 0.36), "WoodDark", verts=10,
                          rot=(math.radians(90), 0, 0)))
        p.append(cylinder(f"Cart_shaft{sy}", 0.035, 1.1, (-0.6, sy * 0.36, 0.52), "Wood", verts=8,
                          rot=(0, math.radians(-100), 0)))
    for sx in (-1, 1):
        p.append(box(f"Cart_front{sx}", (0.06, 0.9, 0.22), (sx * 0.67, 0, 0.58), "WoodDark", bevel=0.015))
    p.append(box("Cart_foot", (0.06, 0.06, 0.5), (-0.55, 0, 0), "WoodDark"))
    for i, (x, y) in enumerate(((0.35, -0.2), (0.45, 0.18))):
        prof = [(0.0, 0.0), (0.1, 0.0), (0.16, 0.1), (0.17, 0.22), (0.09, 0.36), (0.07, 0.4), (0.09, 0.43)]
        p.append(lathe(f"Cart_jar{i}", prof, (x, y, 0.54), "Clay", verts=14))
    p += crate("Cart_oranges", (-0.22, 0.05), size=0.5, z=0.54, rot=0.1, fruit="Orange")
    p.append(ball("Cart_sack", 0.2, (0.05, 0.22, 0.72), "Sack", scale=(1, 1, 0.8)))
    return join("Cart", p)


def build_mat(name, cloth, border, goods):
    """Blanket of a vendor sitting on the ground, with the goods on top and a stool."""
    p = [box(f"{name}_cloth", (1.5, 1.1, 0.02), (0, 0, 0), cloth, bevel=0.008)]
    for sy in (-1, 1):
        p.append(box(f"{name}_rim{sy}", (1.5, 0.12, 0.024), (0, sy * 0.45, 0), border))
    for i, g in enumerate(goods):
        x = -0.48 + i * 0.48
        if g == "Clay":
            for k, dx in enumerate((-0.1, 0.12)):
                prof = [(0.0, 0.0), (0.08, 0.0), (0.13, 0.08), (0.14, 0.17), (0.07, 0.28), (0.05, 0.31), (0.07, 0.34)]
                p.append(lathe(f"{name}_jar{i}{k}", prof, (x + dx, -0.05 + 0.12 * k, 0.02), "Clay", verts=14))
        else:
            p.append(lathe(f"{name}_basket{i}", [(0.0, 0.0), (0.15, 0.0), (0.2, 0.08), (0.21, 0.13)], (x, 0, 0.02),
                           "Wicker", verts=14))
            for k in range(6):
                a = 2 * math.pi * k / 6
                d = 0.1 if k else 0.0
                p.append(ball(f"{name}_fruit{i}{k}", 0.05, (x + math.cos(a) * d, math.sin(a) * d, 0.15), g))
    p.append(cylinder(f"{name}_stool", 0.17, 0.32, (0, 0.8, 0), "Wood", verts=12, bevel=0.02))
    return join(name, p)


def build_peak_tent(name, cloth):
    """Gabled canvas tent on four posts and a ridge pole, open in front: low counter with
    cloths and jugs, and a barrel beside it."""
    p = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(cylinder(f"{name}_post{sx}{sy}", 0.055, 1.75, (sx * 1.25, sy * 0.95, 0), "Wood", verts=8))
        p.append(cylinder(f"{name}_mast{sx}", 0.06, 2.55, (sx * 1.25, 0, 0), "Wood", verts=8))
    p.append(cylinder(f"{name}_ridge", 0.05, 2.8, (-1.4, 0, 2.5), "WoodDark", verts=8, rot=(0, math.radians(90), 0)))
    slope = math.atan2(0.8, 1.05)
    for sy in (-1, 1):
        p.append(box(f"{name}_cloth{sy}", (2.85, 1.35, 0.045), (0, sy * 0.53, 2.12), cloth, bevel=0.02,
                     rot=(-slope * sy, 0, 0)))
        p.append(box(f"{name}_valance{sy}", (2.85, 0.04, 0.24), (0, sy * 1.06, 1.62), cloth, bevel=0.015))
    p.append(box(f"{name}_counter", (2.0, 0.6, 0.07), (0, -0.45, 0.62), "Wood", bevel=0.02))
    for sx in (-1, 1):
        p.append(box(f"{name}_leg{sx}", (0.07, 0.5, 0.62), (sx * 0.9, -0.45, 0), "WoodDark"))
    for i, g in enumerate(("ClothRedLoom", "ClothOchre", "ClothCream")):
        for k in range(2):
            p.append(box(f"{name}_cloth_sale{i}{k}", (0.5, 0.4, 0.07), (-0.62 + i * 0.62, -0.45, 0.69 + k * 0.075), g,
                         bevel=0.025))
    p += barrel(f"{name}_barrel", (1.6, -0.6), 0.9)
    return join(name, p)


def build_trough():
    """Trough: hollowed log with water (references/cutouts/trough.png)."""
    parts = log("Trough", 0.3, 1.8, (0, 0, 0.3), bevel=0.04)
    cutter = box("Trough_hollow", (1.55, 0.42, 0.4), (0, 0, 0.42), "Hollow", bevel=0.1)
    mod = parts[0].modifiers.new("hollow", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter)
    parts.append(box("Trough_water", (1.5, 0.38, 0.02), (0, 0, 0.47), "TroughWater"))
    # Two chocks so it doesn't roll.
    for sx in (-1, 1):
        parts.append(box(f"Trough_chock{sx}", (0.12, 0.5, 0.08), (sx * 0.6, 0, 0), "WoodDark", bevel=0.02))
    return join("Trough", parts)


def build_loom():
    """Loom (references/cutouts/loom.png): wooden frame with support legs, cream warp threads
    and the woven cloth at the bottom, red with cream bands."""
    p = []
    h, w = 1.55, 1.1
    frame = []
    for sx in (-1, 1):
        frame.append(box(f"Loom_side{sx}", (0.08, 0.08, h), (sx * w / 2, 0, 0), "Wood", bevel=0.02))
        # Support leg at the back: from the ground (y = 0.55) up to the side, 1.25 m high.
        p.append(box(f"Loom_leg{sx}", (0.07, 0.07, 1.37), (sx * w / 2, 0.55, 0), "WoodDark", bevel=0.015,
                     rot=(math.atan2(0.55, 1.25), 0, 0)))
    for z in (0.12, h - 0.1, 0.55):
        frame.append(cylinder(f"Loom_bar{z}", 0.04, w + 0.12, (-(w + 0.12) / 2, 0, z), "WoodDark", verts=8,
                              rot=(0, math.radians(90), 0)))
    for i in range(16):
        x = -w / 2 + 0.09 + i * (w - 0.18) / 15
        frame.append(cylinder(f"Loom_thread{i}", 0.006, h - 0.75, (x, 0, 0.6), "ThreadCream", verts=4))
    frame.append(box("Loom_cloth", (w - 0.14, 0.02, 0.42), (0, 0, 0.13), "ClothRedLoom"))
    for z in (0.22, 0.38):
        frame.append(box(f"Loom_band{z}", (w - 0.14, 0.025, 0.04), (0, 0, z), "ThreadCream"))
    return join("Loom", p + frame)


def torus_ring(name, major, minor, loc, mat):
    """Horizontal ring (basket rim or band)."""
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=20, minor_segments=5,
                                     location=loc)
    obj = bpy.context.active_object
    obj.name = name
    return _finish(obj, mat, smooth=True)


def torus_part(name, major, minor, loc, mat):
    """Hoop (half turn upward, like a bucket handle)."""
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=24, minor_segments=6,
                                     location=loc, rotation=(math.radians(90), 0, 0))
    obj = bpy.context.active_object
    obj.name = name
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y < -0.01], context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    return _finish(obj, mat, smooth=True)

def build_props():
    props = []
    props.append(build_well())

    p = [lathe("Oven_body", [(0.42, 0), (0.44, 0.3), (0.4, 0.65), (0.26, 0.88), (0.2, 0.9)], (0, 0, 0), "Clay"),
         box("Oven_mouth", (0.3, 0.12, 0.28), (0, -0.4, 0.12), "Hollow", bevel=0.05)]
    props.append(join("Oven", p))

    p = [box("Bench_seat", (1.6, 0.4, 0.08), (0, 0, 0.42), "Wood", bevel=0.03)]
    for side in (-1, 1):
        p.append(box(f"Bench_leg{side}", (0.12, 0.34, 0.42), (side * 0.62, 0, 0), "WoodDark", bevel=0.02))
    props.append(join("Bench", p))

    props.append(join("Jug", [lathe("Jug_body", [(0.12, 0), (0.22, 0.12), (0.24, 0.3), (0.16, 0.5),
                                                          (0.09, 0.58), (0.11, 0.64)], (0, 0, 0), "Clay")]))
    props.append(join("Basket", [lathe("Basket_body", [(0.2, 0), (0.26, 0.12), (0.28, 0.25), (0.27, 0.27)],
                                      (0, 0, 0), "Wicker")]))
    # Firewood: stacked logs.
    p = []
    for row in range(3):
        for i in range(4 - row):
            x = (i - (3 - row) * 0.5) * 0.24
            p.append(cylinder(f"Firewood{row}{i}", 0.11, 1.1, (-0.55, x, 0.11 + row * 0.2), "Wood", verts=8,
                              rot=(0, math.radians(90), 0)))
    props.append(join("Firewood", p))
    # 2 m fence section: slightly crooked posts and two rails.
    p = []
    for i, x in enumerate((-1.0, 0.0, 1.0)):
        p.append(box(f"Fence_post{i}", (0.12, 0.12, 0.85), (x, 0, 0), "Wood", bevel=0.03,
                     rot=(random.uniform(-0.05, 0.05), random.uniform(-0.05, 0.05), 0)))
    for z in (0.35, 0.65):
        p.append(box(f"Fence_board{z}", (2.1, 0.06, 0.1), (0, 0.05, z), "WoodDark", bevel=0.02,
                     rot=(0, random.uniform(-0.03, 0.03), 0)))
    props.append(join("Fence", p))
    # Potter's stall: table with awning and jugs.
    p = [box("Stall_table", (2.0, 0.8, 0.08), (0, 0, 0.8), "Wood", bevel=0.03)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(box(f"Stall_leg{sx}{sy}", (0.08, 0.08, 0.8), (sx * 0.9, sy * 0.32, 0), "WoodDark"))
            p.append(cylinder(f"Stall_post{sx}{sy}", 0.04, 2.1, (sx * 1.0, sy * 0.4, 0), "Wood", verts=8))
    p.append(box("Stall_awning", (2.3, 1.1, 0.05), (0, 0, 2.1), "ClothBlue", bevel=0.02, rot=(math.radians(8), 0, 0)))
    for i, x in enumerate((-0.6, 0.0, 0.55)):
        s = 0.7 + 0.15 * i
        prof = [(0.12 * s, 0), (0.22 * s, 0.12 * s), (0.24 * s, 0.3 * s), (0.16 * s, 0.5 * s), (0.1 * s, 0.6 * s)]
        p.append(lathe(f"Stall_jug{i}", prof, (x, 0, 0.88), "Clay"))
    props.append(join("Stall", p))

    # --- Yards and roofs ---
    props.append(join("FlowerPot", [lathe("FlowerPot_body", [(0.13, 0), (0.17, 0.08), (0.2, 0.26), (0.22, 0.3),
                                                        (0.2, 0.32)], (0, 0, 0), "Clay")]))
    props.append(join("Sack", [lathe("Sack_body", [(0.2, 0), (0.27, 0.1), (0.28, 0.3), (0.2, 0.48), (0.08, 0.56),
                                                    (0.1, 0.62)], (0, 0, 0), "Sack")]))
    p = [box("Rug_base", (1.7, 1.0, 0.03), (0, 0, 0.0), "ClothPink", bevel=0.01)]
    for i, (y, c) in enumerate(((-0.3, "ClothBlue"), (0.0, "ClothOchre"), (0.3, "ClothBlue"))):
        p.append(box(f"Rug_stripe{i}", (1.7, 0.1, 0.035), (0, y, 0.0), c))
    props.append(join("Rug", p))
    p = []
    for side in (-1, 1):
        p.append(cylinder(f"Clothesline_post{side}", 0.05, 1.75, (side * 1.4, 0, 0), "Wood", verts=8))
    p.append(cylinder("Clothesline_rope", 0.012, 2.8, (-1.4, 0, 1.65), "Rope", verts=6, rot=(0, math.radians(90), 0)))
    for i, (x, c, hh) in enumerate(((-0.8, "ClothBlue", 0.7), (0.0, "ClothPink", 0.55), (0.75, "ClothGreen", 0.8))):
        p.append(box(f"Clothesline_cloth{i}", (0.6, 0.03, hh), (x, 0, 1.65 - hh), c, bevel=0.01,
                     rot=(math.radians(random.uniform(-6, 6)), 0, 0)))
    props.append(join("Clothesline", p))
    p = []
    for side in (-1, 1):
        p.append(box(f"Loom_side{side}", (0.08, 0.08, 1.5), (side * 0.65, 0, 0), "Wood", bevel=0.02))
    for z in (0.25, 1.4):
        p.append(cylinder(f"Loom_roller{z}", 0.05, 1.4, (-0.7, 0, z), "WoodDark", verts=8,
                          rot=(0, math.radians(90), 0)))
    p.append(box("Loom_cloth", (1.15, 0.02, 0.55), (0, 0, 0.3), "ClothPink"))
    for i in range(12):
        x = -0.55 + i * 0.1
        p.append(cylinder(f"Loom_thread{i}", 0.006, 0.55, (x, 0, 0.85), "Sack", verts=4))
    props.append(join("Loom", p))
    p = [box("Trough_box", (1.8, 0.6, 0.45), (0, 0, 0), "Wood", bevel=0.04),
         box("Trough_water", (1.6, 0.42, 0.04), (0, 0, 0.38), "Water")]
    props.append(join("Trough", p))

    # --- Ark worksite ---
    p = [box("Sawhorse_beam", (1.4, 0.14, 0.14), (0, 0, 0.75), "Wood", bevel=0.02)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(box(f"Sawhorse_leg{sx}{sy}", (0.08, 0.08, 0.85), (sx * 0.55, sy * 0.18, 0), "WoodDark",
                         rot=(math.radians(-14 * sy), 0, 0)))
    p.append(box("Sawhorse_plank", (2.4, 0.32, 0.06), (0.2, 0, 0.82), "Wood", bevel=0.01,
                 rot=(0, 0, math.radians(4))))
    props.append(join("Sawhorse", p))
    p = []
    for i in range(9):
        layer, k = divmod(i, 3)
        p.append(box(f"Planks{i}", (2.6, 0.3, 0.07), (random.uniform(-0.08, 0.08), (k - 1) * 0.32, layer * 0.075),
                     "Wood" if i % 2 else "WoodDark", bevel=0.01, rot=(0, 0, math.radians(random.uniform(-2, 2)))))
    props.append(join("Planks", p))
    p = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(cylinder(f"Scaffold_post{sx}{sy}", 0.05, 3.0, (sx * 1.2, sy * 0.45, 0), "Wood", verts=8))
    for z in (1.4, 2.7):
        p.append(box(f"Scaffold_platform{z}", (2.6, 1.0, 0.06), (0, 0, z), "Wood", bevel=0.01))
        for sy in (-1, 1):
            p.append(cylinder(f"Scaffold_crossbar{z}{sy}", 0.03, 2.4, (-1.2, sy * 0.45, z - 0.25), "WoodDark",
                              verts=6, rot=(0, math.radians(90), 0)))
    for i in range(6):
        p.append(cylinder(f"Scaffold_rung{i}", 0.025, 0.4, (-1.35, -0.2, 0.25 + i * 0.42), "WoodDark", verts=6,
                          rot=(math.radians(90), 0, 0)))
    props.append(join("Scaffold", p))
    p = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(cylinder(f"Awning_post{sx}{sy}", 0.05, 2.0 if sy < 0 else 1.6, (sx * 1.4, sy * 1.1, 0), "Wood",
                              verts=8))
    p.append(box("Awning_cloth", (3.1, 2.5, 0.04), (0, 0, 1.8), "ClothOchre", bevel=0.02, rot=(math.radians(9), 0, 0)))
    p.append(box("Awning_mat", (2.2, 1.5, 0.03), (0, 0, 0.0), "Wicker", bevel=0.01))
    props.append(join("Awning", p))
    p = []
    for i in range(3):
        a = 2 * math.pi * i / 3
        p.append(box(f"Pot_stone{i}", (0.22, 0.22, 0.2), (math.cos(a) * 0.32, math.sin(a) * 0.32, 0), "Stone",
                     bevel=0.06))
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.5
        p.append(cylinder(f"Pot_log{i}", 0.05, 0.5, (math.cos(a) * 0.25, math.sin(a) * 0.25, 0.05), "WoodDark",
                          verts=6, rot=(0, math.radians(80), a)))
        p.append(cylinder(f"Pot_flame{i}", 0.09, 0.28, (math.cos(a) * 0.1, math.sin(a) * 0.1, 0.06), "Fire",
                          verts=6, top_radius=0.0))
    p.append(lathe("Pot_body", [(0.2, 0.2), (0.3, 0.3), (0.32, 0.45), (0.28, 0.6), (0.3, 0.64)], (0, 0, 0), "Pitch"))
    props.append(join("PitchPot", p))
    p = [box("Table_top", (1.8, 0.75, 0.08), (0, 0, 0.78), "Wood", bevel=0.02)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(box(f"Table_leg{sx}{sy}", (0.09, 0.09, 0.78), (sx * 0.8, sy * 0.3, 0), "WoodDark"))
    p.append(cylinder("Table_mallet_grip", 0.025, 0.4, (-0.5, 0.1, 0.9), "Wood", verts=6, rot=(0, math.radians(90), 0.3)))
    p.append(cylinder("Table_mallet_head", 0.07, 0.2, (-0.55, 0.0, 0.86), "WoodDark", verts=8,
                      rot=(math.radians(90), 0, 0.3)))
    p.append(box("Table_saw", (0.6, 0.12, 0.015), (0.3, -0.1, 0.87), "Stone", rot=(0, 0, 0.2)))
    p.append(box("Table_saw_grip", (0.14, 0.05, 0.05), (0.62, -0.03, 0.88), "WoodDark", rot=(0, 0, 0.2)))
    for i in range(4):
        p.append(cylinder(f"Table_peg{i}", 0.02, 0.18, (0.0 + i * 0.07, 0.25, 0.86), "WoodDark", verts=5,
                          rot=(0, math.radians(90), i)))
    props.append(join("Workbench", p))

    # Low adobe wall (2 m section) to close shared yards.
    props.append(join("LowWall", [box("LowWall_body", (2.0, 0.34, 1.05), (0, 0, 0), "AdobeShade", bevel=0.12),
                                 box("LowWall_cap", (2.04, 0.4, 0.1), (0, 0, 1.0), "Adobe", bevel=0.04)]))

    # --- Plaza and market ---
    for name, cloth in (("TentPink", "ClothPink"), ("TentBlue", "ClothBlue"), ("TentGreen", "ClothGreen")):
        # Gabled market awning on four posts, with counter and goods.
        p = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                p.append(cylinder(f"{name}_post{sx}{sy}", 0.05, 1.9, (sx * 1.3, sy * 0.9, 0), "Wood", verts=8))
        p.append(cylinder(f"{name}_ridge", 0.05, 2.9, (-1.45, 0, 2.35), "WoodDark", verts=8,
                          rot=(0, math.radians(90), 0)))
        for sy in (-1, 1):
            p.append(box(f"{name}_cloth{sy}", (2.9, 1.15, 0.04), (0, sy * 0.52, 2.13), cloth, bevel=0.02,
                         rot=(math.radians(-27 * sy), 0, 0)))
        p.append(box(f"{name}_counter", (2.3, 0.6, 0.08), (0, -0.55, 0.78), "Wood", bevel=0.02))
        for sx in (-1, 1):
            p.append(box(f"{name}_leg{sx}", (0.08, 0.5, 0.78), (sx * 1.05, -0.55, 0), "WoodDark"))
        goods = {"TentPink": ["Clay", "Clay", "Clay"], "TentBlue": ["ClothPink", "ClothOchre", "ClothGreen"],
                 "TentGreen": ["ClothGreen", "ClothOchre", "Wicker"]}[name]
        for i, g in enumerate(goods):
            x = -0.75 + i * 0.75
            if g == "Clay":
                prof = [(0.1, 0), (0.18, 0.1), (0.2, 0.25), (0.13, 0.4), (0.09, 0.46)]
                p.append(lathe(f"{name}_good{i}", prof, (x, -0.55, 0.86), g))
            elif g == "Wicker":
                p.append(lathe(f"{name}_good{i}", [(0.16, 0), (0.22, 0.1), (0.23, 0.18)], (x, -0.55, 0.86), g))
                for k in range(3):
                    p.append(cylinder(f"{name}_fruit{i}{k}", 0.06, 0.1, (x - 0.06 + k * 0.06, -0.55, 0.98), "ClothOchre",
                                      verts=8))
            else:
                p.append(box(f"{name}_good{i}", (0.55, 0.45, 0.16), (x, -0.55, 0.86), g, bevel=0.04))
        p.append(lathe(f"{name}_basket", [(0.2, 0), (0.26, 0.12), (0.28, 0.25), (0.27, 0.27)], (1.6, 0.4, 0), "Wicker"))
        props.append(join(name, p))
    # Plaza campfire: ring of stones, logs and flames.
    p = []
    for i in range(9):
        a = 2 * math.pi * i / 9
        p.append(box(f"Campfire_stone{i}", (0.26, 0.22, 0.18), (math.cos(a) * 0.6, math.sin(a) * 0.6, 0), "Stone",
                     bevel=0.07, rot=(0, 0, a)))
    for i in range(4):
        a = 2 * math.pi * i / 4 + 0.4
        p.append(cylinder(f"Campfire_log{i}", 0.06, 0.65, (math.cos(a) * 0.32, math.sin(a) * 0.32, 0.04), "WoodDark",
                          verts=6, rot=(0, math.radians(70), a)))
    for i, (dx, dy, hh) in enumerate(((0, 0, 0.5), (0.12, 0.08, 0.35), (-0.1, 0.1, 0.32), (0.02, -0.12, 0.3))):
        p.append(cylinder(f"Campfire_flame{i}", 0.13 if i == 0 else 0.09, hh, (dx, dy, 0.05), "Fire", verts=6,
                          top_radius=0.0))
    props.append(join("Campfire", p))
    # Long plaza table.
    p = [box("Table_board", (2.2, 0.8, 0.08), (0, 0, 0.74), "Wood", bevel=0.02)]
    for sx in (-1, 1):
        p.append(box(f"Table_trestle{sx}", (0.1, 0.65, 0.74), (sx * 0.85, 0, 0), "WoodDark", bevel=0.02))
    p.append(lathe("Table_jar", [(0.07, 0), (0.1, 0.06), (0.1, 0.16), (0.06, 0.24), (0.07, 0.27)], (-0.5, 0.1, 0.82),
                   "Clay"))
    p.append(lathe("Table_bowl", [(0.08, 0), (0.15, 0.06), (0.16, 0.08)], (0.4, -0.1, 0.82), "Clay"))
    props.append(join("Table", p))
    # Stone and wood bridge: stone arch over the river, wooden deck and railings.
    span, width = 9.0, 2.6
    p = []
    blocks = 13
    for i in range(blocks):
        t = (i + 0.5) / blocks
        a = math.pi * t
        x = -span * 0.42 * math.cos(a)
        z = 0.15 + 1.35 * math.sin(a) - 1.45
        p.append(box(f"Bridge_voussoir{i}", (span * 0.85 / blocks + 0.05, width, 0.42), (x, 0, z), "Stone", bevel=0.06,
                     rot=(0, -(a - math.pi * 0.5) * 0.9, 0)))
    for side in (-1, 1):
        p.append(box(f"Bridge_abutment{side}", (1.4, width + 0.3, 1.7), (side * (span * 0.5 - 0.3), 0, -1.55), "Stone",
                     bevel=0.12))
    planks = 18
    for i in range(planks):
        x = -span * 0.5 + (i + 0.5) * span / planks
        lift = 0.18 * (1 - (x / (span * 0.5)) ** 2)
        p.append(box(f"Bridge_board{i}", (span / planks - 0.04, width, 0.1), (x, 0, 0.05 + lift), "Wood" if i % 3 else
                     "WoodDark", bevel=0.015))
    for sy in (-1, 1):
        for i in range(5):
            x = -span * 0.5 + 0.4 + i * (span - 0.8) / 4
            lift = 0.18 * (1 - (x / (span * 0.5)) ** 2)
            p.append(box(f"Bridge_post{sy}{i}", (0.13, 0.13, 0.85), (x, sy * (width * 0.5 - 0.08), 0.1 + lift),
                         "WoodDark", bevel=0.03))
        p.append(box(f"Bridge_railing{sy}", (span - 0.6, 0.1, 0.1), (0, sy * (width * 0.5 - 0.08), 0.95), "Wood",
                     bevel=0.02))
    props.append(join("StoneBridge", p))
    return props


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = argv[0]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objs = build_houses() + build_props()
    # The ones that mix materials are made by script (the generated ones came out badly painted).
    new_builders = {"Campfire": build_campfire, "Basket": build_baskets, "Trough": build_trough, "Loom": build_loom,
                     "Firewood": build_firewood, "Stump": build_stump, "LogSeat": build_log_seat,
                     "TarpCream": lambda: build_canvas_stall("TarpCream", "TarpCream", ["Apple", "Clay", "Orange"]),
                     "TarpBlue": lambda: build_canvas_stall("TarpBlue", "TarpBlue", ["ClothPink", "ClothOchre", "ClothCream"]),
                     "TarpGreen": lambda: build_canvas_stall("TarpGreen", "TarpGreen", ["Pear", "Grape", "Clay"]),
                     "TarpSage": lambda: build_canvas_stall("TarpSage", "TarpSage", ["Clay", "Apple", "ClothGreen"]),
                     "TarpGray": lambda: build_canvas_stall("TarpGray", "TarpGray", ["Grape", "Orange", "Clay"]),
                     "TentPeakCream": lambda: build_peak_tent("TentPeakCream", "TarpCream"),
                     "TentPeakBlue": lambda: build_peak_tent("TentPeakBlue", "TarpBlue"),
                     "Barrels": build_barrels, "Crates": build_crates, "Cart": build_cart,
                     "BlanketRed": lambda: build_mat("BlanketRed", "ClothRed", "ClothCream", ["Clay", "Apple", "Pear"]),
                     "BlanketBlue": lambda: build_mat("BlanketBlue", "ClothBlueStrong", "ClothCream", ["Orange", "Clay", "Grape"])}
    for o in [o for o in objs if o.name in new_builders]:
        objs.remove(o)
        bpy.data.objects.remove(o)
    objs += [f() for f in new_builders.values()]
    # Spread out in a row to see them well in Blender; in Godot each one is used separately.
    x = 0.0
    for o in objs:
        o.location = (x, 0, 0)
        x += o.dimensions.x + 2.0
    for o in objs:
        tris = sum(len(p.vertices) - 2 for p in o.data.polygons)
        print("piece", o.name, "size", tuple(round(v, 2) for v in o.dimensions), "triangles", tris)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True)
    print("VILLAGE OK ->", out)


main()
