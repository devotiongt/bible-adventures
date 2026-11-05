"""Generates Noah's ark in Blender and exports it to glTF for Godot.

Usage (without opening Blender):
    blender --background --factory-startup --python tools/blender/ark.py -- assets/ark/ark.glb [renders_folder]

The ark is split into 5 objects, one per construction stage (see data/ark.json):
    Stage1  keel, stems, ribs and support blocks
    Stage2  hull of curved planks and gunwale
    Stage3  (empty: sealing with pitch is a material change in Godot)
    Stage4  deck, rooms (walls) and posts
    Stage5  roof, window, side door and ramp

Axes in Blender: X = length, Y = width, Z = up. The door is on the -Y side,
which in Godot is +Z (the side facing where Noah appears).
"""

import math
import random
import sys

import bmesh
import bpy
from mathutils import Vector

random.seed(7)

# --- Measurements (meters) ---------------------------------------------------
LENGTH = 22.0          # From bow to stern.
BEAM = 2.9             # Maximum half beam.
KEEL_Z = 0.55          # Keel height at the center (it sits on blocks).
GUNWALE_Z = 3.75       # Gunwale height at the center.
SHEER = 1.1            # How much bow and stern rise.
ROCKER = 0.9           # How much the keel rises toward the ends.
PLANKS = 9             # Plank strakes per side.
PLANK_THICK = 0.07
DECK_Z = GUNWALE_Z - 0.12
CABIN = (12.5, 3.5, 2.0)   # Length, width and height of the rooms.
ROOF_RISE = 1.25
DOOR_X = 3.0

# Base colors per material (in Godot they are replaced by the wood shader).
MATERIALS = {
    "Hull": (0.64, 0.44, 0.28),
    "Beam": (0.43, 0.27, 0.16),
    "Deck": (0.75, 0.54, 0.35),
    "Wall": (0.66, 0.47, 0.30),
    "Roof": (0.48, 0.29, 0.16),
    "Door": (0.37, 0.23, 0.13),
    "Window": (0.10, 0.07, 0.05),
    "Stone": (0.56, 0.55, 0.53),
}


# --- Hull shape ---------------------------------------------------------------

def keel_z(u):
    return KEEL_Z + ROCKER * abs(u) ** 3


def gunwale_z(u):
    return GUNWALE_Z + SHEER * abs(u) ** 2.2


def half_beam(u):
    return BEAM * max(0.0, 1.0 - abs(u) ** 2.6) ** 0.5


def hull_point(u, v, side):
    """u in [-1, 1] lengthwise; v in [0, 1] from keel to gunwale; side = ±1."""
    theta = v * math.pi * 0.5
    depth = gunwale_z(u) - keel_z(u)
    return Vector((u * LENGTH * 0.5,
                   side * half_beam(u) * math.sin(theta),
                   keel_z(u) + depth * (1.0 - math.cos(theta))))


def hull_normal(u, v, side):
    e = 1e-3
    du = hull_point(min(u + e, 1.0), v, side) - hull_point(max(u - e, -1.0), v, side)
    dv = hull_point(u, min(v + e, 1.0), side) - hull_point(u, max(v - e, 0.0), side)
    n = du.cross(dv)
    if n.length < 1e-9:
        return Vector((0, side, 0))
    n.normalize()
    return n if n.y * side >= 0 else -n


# --- Mesh utilities -------------------------------------------------------------

def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*MATERIALS[name], 1.0)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*MATERIALS[name], 1.0)
        bsdf.inputs["Roughness"].default_value = 0.85
        # The vertex color (per-plank variation) multiplies the base color.
        attr = mat.node_tree.nodes.new("ShaderNodeVertexColor")
        attr.layer_name = "Col"
        mix = mat.node_tree.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs["A"].default_value = (*MATERIALS[name], 1.0)
        mat.node_tree.links.new(attr.outputs["Color"], mix.inputs["B"])
        mat.node_tree.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    return mat


def new_object(name, verts, faces, mat_name, collection, tint=1.0):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.validate()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material(mat_name))
    color = mesh.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
    for item in color.data:
        item.color = (tint, tint, tint, 1.0)
    return obj


def strip(rows, close_ends=True):
    """rows: list of rings (each a list of 4 vertices in order) -> verts, faces."""
    verts, faces = [], []
    ring = len(rows[0])
    for r in rows:
        verts.extend(r)
    for i in range(len(rows) - 1):
        for k in range(ring):
            a = i * ring + k
            b = i * ring + (k + 1) % ring
            faces.append((a, b, b + ring, a + ring))
    if close_ends:
        faces.append(tuple(range(ring))[::-1])
        last = (len(rows) - 1) * ring
        faces.append(tuple(range(last, last + ring)))
    return verts, faces


def box(name, center, size, mat_name, collection, rot=(0, 0, 0), tint=1.0):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location = center
    obj.rotation_euler = rot
    obj.data.materials.append(material(mat_name))
    color = mesh.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
    for item in color.data:
        item.color = (tint, tint, tint, 1.0)
    return obj


def beam_along(name, points, size, mat_name, collection, up=Vector((0, 0, 1)), tint=1.0):
    """Beam with a rectangular cross-section that follows a list of points."""
    rows = []
    for i, p in enumerate(points):
        a = points[max(i - 1, 0)]
        b = points[min(i + 1, len(points) - 1)]
        t = (b - a).normalized()
        side = t.cross(up)
        if side.length < 1e-6:
            side = t.cross(Vector((1, 0, 0)))
        side.normalize()
        n = side.cross(t).normalized()
        w, h = size[0] * 0.5, size[1] * 0.5
        rows.append([p + side * w + n * h, p - side * w + n * h, p - side * w - n * h, p + side * w - n * h])
    verts, faces = strip(rows)
    return new_object(name, verts, faces, mat_name, collection, tint)


def plank_tint():
    return random.uniform(0.8, 1.0)


# --- Stage 1: keel, stems, ribs and supports -----------------------------------

def build_keel(col):
    samples = [i / 40.0 * 2.0 - 1.0 for i in range(41)]
    keel = [Vector((u * LENGTH * 0.5, 0, keel_z(u) - 0.12)) for u in samples]
    beam_along("Keel", keel, (0.32, 0.28), "Beam", col, up=Vector((0, 0, 1)))
    # Stems: curved beams at bow and stern, from the keel to the gunwale.
    for sign in (1, -1):
        u = sign * 0.985
        stem = [hull_point(u, v / 12.0, 1) * Vector((1, 0, 1)) + Vector((sign * 0.12, 0, 0)) for v in range(13)]
        stem.append(stem[-1] + Vector((sign * 0.25, 0, 0.35)))
        beam_along("Stem", stem, (0.26, 0.26), "Beam", col, up=Vector((0, 1, 0)))
    # Ribs (frames) inside the hull.
    for i in range(13):
        u = -0.8 + i * (1.6 / 12)
        pts = []
        for k in range(25):
            v = abs(k - 12) / 12.0
            side = 1 if k >= 12 else -1
            p = hull_point(u, v, side)
            pts.append(p - hull_normal(u, v, side) * 0.16)
        beam_along("Rib", pts, (0.16, 0.14), "Beam", col, up=Vector((1, 0, 0)), tint=plank_tint())
    # Stone blocks under the keel.
    for i in range(6):
        u = -0.8 + i * 0.32
        top = keel_z(u) - 0.24
        box("Support", (u * LENGTH * 0.5, 0, top * 0.5), (0.9, 1.2, top), "Stone", col, tint=random.uniform(0.85, 1.0))


# --- Stage 2: plank hull -------------------------------------------------------

def build_hull(col):
    gap_v = 0.004
    for side in (1, -1):
        for k in range(PLANKS):
            v0 = k / PLANKS + gap_v
            v1 = (k + 1) / PLANKS - gap_v
            # Each strake is split into 3 planks with staggered joints.
            cuts = sorted([-1.0, 1.0] + [random.uniform(-0.55, -0.2), random.uniform(0.15, 0.5)])
            for j in range(len(cuts) - 1):
                ua = cuts[j] + (0.004 if j > 0 else 0.0)
                ub = cuts[j + 1] - (0.004 if j < len(cuts) - 2 else 0.0)
                rows = []
                steps = max(4, int((ub - ua) * 30))
                for s in range(steps + 1):
                    u = ua + (ub - ua) * s / steps
                    u = max(-0.999, min(0.999, u))
                    p0 = hull_point(u, v0, side)
                    p1 = hull_point(u, v1, side)
                    n0 = hull_normal(u, v0, side)
                    n1 = hull_normal(u, v1, side)
                    rows.append([p0, p1, p1 - n1 * PLANK_THICK, p0 - n0 * PLANK_THICK])
                verts, faces = strip(rows)
                new_object("Plank", verts, faces, "Hull", col, tint=plank_tint())
        # Gunwale: beam that caps the top edge.
        top = [hull_point(-0.99 + i * (1.98 / 50), 1.0, side) + Vector((0, 0, 0.05)) for i in range(51)]
        beam_along("Gunwale", top, (0.2, 0.14), "Beam", col)


# --- Stage 4: deck, rooms and posts --------------------------------------------

def build_deck_and_cabin(col):
    # Deck: lengthwise planks, trimmed by the hull shape.
    width = 0.3
    y = -BEAM + width
    while y < BEAM - width * 0.5:
        frac = abs(y) / BEAM
        u_max = max(0.0, 1.0 - frac ** 2) ** (1 / 2.6) * 0.97
        x_max = u_max * LENGTH * 0.5
        if x_max > 0.6:
            x = -x_max
            while x < x_max - 0.1:
                seg = min(random.uniform(2.5, 4.5), x_max - x)
                box("DeckPlank", (x + seg * 0.5, y, DECK_Z), (seg - 0.03, width - 0.025, 0.08),
                    "Deck", col, tint=plank_tint())
                x += seg
        y += width

    # Rooms: walls of horizontal planks; the top row is the window.
    length, wide, height = CABIN
    base = DECK_Z + 0.04
    rows = 8
    row_h = height / rows
    for r in range(rows):
        z = base + (r + 0.5) * row_h
        if r == rows - 1:
            continue  # Opening for the window running around (Genesis 6:16).
        for sy in (1, -1):
            box("LongWall", (0, sy * wide * 0.5, z), (length, 0.1, row_h - 0.03), "Wall", col, tint=plank_tint())
        for sx in (1, -1):
            box("ShortWall", (sx * length * 0.5, 0, z), (0.1, wide, row_h - 0.03), "Wall", col, tint=plank_tint())
    # Posts at the corners and along the sides, which also hold up the roof by the window.
    for i in range(7):
        x = -length * 0.5 + i * length / 6
        for sy in (1, -1):
            box("Post", (x, sy * wide * 0.5, base + height * 0.5), (0.18, 0.18, height), "Beam", col)
    # Railing of short posts on the gunwale.
    for side in (1, -1):
        for i in range(17):
            u = -0.82 + i * (1.64 / 16)
            p = hull_point(u, 1.0, side)
            box("RailPost", (p.x, p.y - side * 0.05, p.z + 0.35), (0.1, 0.1, 0.6), "Beam", col)
        rail = [hull_point(-0.84 + i * (1.68 / 40), 1.0, side) + Vector((0, -side * 0.05, 0.66)) for i in range(41)]
        beam_along("Railing", rail, (0.1, 0.08), "Beam", col)


# --- Stage 5: roof, window, door and ramp --------------------------------------

def build_roof_door(col):
    length, wide, height = CABIN
    eave_z = DECK_Z + 0.04 + height
    ridge_z = eave_z + ROOF_RISE
    over = 0.45
    half_w = wide * 0.5 + over
    slope_len = math.hypot(half_w, ROOF_RISE)
    angle = math.atan2(ROOF_RISE, half_w)
    rows = 7
    for sy in (1, -1):
        for r in range(rows):
            t = (r + 0.5) / rows
            y = sy * half_w * (1 - t)
            z = eave_z - 0.05 + ROOF_RISE * t
            x = -(length * 0.5 + over)
            while x < length * 0.5 + over - 0.1:
                seg = min(random.uniform(1.5, 3.0), length * 0.5 + over - x)
                box("Shingle", (x + seg * 0.5, y, z + 0.04), (seg - 0.04, slope_len / rows + 0.08, 0.07),
                    "Roof", col, rot=(-sy * angle, 0, 0), tint=plank_tint())
                x += seg
    # Ridge beam.
    box("RidgeBeam", (0, 0, ridge_z + 0.06), (length + over * 2 + 0.1, 0.24, 0.2), "Beam", col)
    # Gables: triangles of vertical planks that close the roof.
    for sx in (1, -1):
        n = 9
        for i in range(n):
            y = -wide * 0.5 + (i + 0.5) * wide / n
            h = ROOF_RISE * (1 - abs(y) / (wide * 0.5 + over)) - 0.05
            box("Gable", (sx * length * 0.5, y, eave_z + h * 0.5), (0.08, wide / n - 0.02, h), "Wall", col,
                tint=plank_tint())
    # Window: dark frame in the opening of the top row.
    win_z = DECK_Z + 0.04 + height - height / 16
    for sy in (1, -1):
        box("Window", (0, sy * (wide * 0.5 - 0.02), win_z), (length - 0.2, 0.05, height / 8 - 0.02), "Window", col)
    for sx in (1, -1):
        box("Window", (sx * (length * 0.5 - 0.02), 0, win_z), (0.05, wide - 0.2, height / 8 - 0.02), "Window", col)

    # Door in the side (-Y side), tilted like the hull at that point.
    u = DOOR_X / (LENGTH * 0.5)
    v_mid = 0.8
    p = hull_point(u, v_mid, -1)
    n = hull_normal(u, v_mid, -1)
    tilt = math.atan2(-n.z, -n.y)
    door_h, door_w = 1.7, 1.5
    box("Door", p + n * 0.06, (door_w, 0.1, door_h), "Door", col, rot=(tilt, 0, 0))
    for dx in (-1, 1):
        box("DoorFrame", p + n * 0.09 + Vector((dx * (door_w * 0.5 + 0.06), 0, 0)), (0.12, 0.12, door_h + 0.15), "Beam",
            col, rot=(tilt, 0, 0))
    box("DoorFrame", p + n * 0.09 + Vector((0, 0, door_h * 0.5 + 0.03)), (door_w + 0.3, 0.12, 0.12), "Beam", col,
        rot=(tilt, 0, 0))

    # Ramp from the door sill to the ground.
    sill = p + n * 0.1 - Vector((0, 0, door_h * 0.45))
    ground = Vector((DOOR_X, sill.y - 4.6, 0.02))
    ramp = ground - sill
    ramp_len = ramp.length
    ramp_angle = math.atan2(ramp.z, -ramp.y)
    steps = 12
    for i in range(steps):
        t = (i + 0.5) / steps
        c = sill + ramp * t
        box("Ramp", c, (1.6, ramp_len / steps - 0.04, 0.08), "Deck", col, rot=(-ramp_angle, 0, 0), tint=plank_tint())
    for dx in (-1, 1):
        box("RampStringer", sill + ramp * 0.5 + Vector((dx * 0.85, 0, -0.05)), (0.14, ramp_len, 0.16), "Beam", col,
            rot=(-ramp_angle, 0, 0))


# --- Scene, test render and export ---------------------------------------------

def join(col, name):
    objs = list(col.objects)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    bpy.ops.object.shade_flat()
    return obj


def render_previews(stages, folder):
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    world = bpy.data.worlds.new("Sky")
    world.color = (0.55, 0.7, 0.85)
    scene.world = world
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 4.0
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    scene.collection.objects.link(sun)
    ground = bpy.data.meshes.new("Ground")
    ground.from_pydata([(-40, -40, 0), (40, -40, 0), (40, 40, 0), (-40, 40, 0)], [], [(0, 1, 2, 3)])
    gobj = bpy.data.objects.new("Ground", ground)
    gmat = bpy.data.materials.new("Ground")
    gmat.diffuse_color = (0.45, 0.6, 0.3, 1)
    gmat.use_nodes = True
    gmat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.58, 0.28, 1)
    gobj.data.materials.append(gmat)
    scene.collection.objects.link(gobj)
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 35
    cam = bpy.data.objects.new("Camera", cam_data)
    cam.location = (17, -21, 11)
    direction = Vector((0, 0, 2.6)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(cam)
    scene.camera = cam
    for i in range(len(stages)):
        for j, obj in enumerate(stages):
            if obj is not None:
                obj.hide_render = j > i
        scene.render.filepath = f"{folder}/ark_stage{i + 1}.png"
        bpy.ops.render.render(write_still=True)
    for o in (sun, gobj, cam):
        bpy.data.objects.remove(o)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = argv[0] if argv else "ark.glb"
    renders = argv[1] if len(argv) > 1 else None

    bpy.ops.wm.read_factory_settings(use_empty=True)
    builders = [build_keel, build_hull, None, build_deck_and_cabin, build_roof_door]
    stages = []
    for i, builder in enumerate(builders):
        name = f"Stage{i + 1}"
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
        if builder is None:
            stages.append(None)
            continue
        builder(col)
        stages.append(join(col, name))
    # Stage 3 (pitch) is an empty node so Godot finds all 5 stages.
    empty = bpy.data.objects.new("Stage3", None)
    bpy.context.scene.collection.objects.link(empty)

    if renders:
        render_previews(stages, renders)

    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", export_yup=True,
                              export_apply=True, export_vertex_color="ACTIVE")
    tris = sum(len(o.data.polygons) for o in stages if o is not None)
    print(f"ARK OK -> {out_path} ({tris} faces)")


main()
