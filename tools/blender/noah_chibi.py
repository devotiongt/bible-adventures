"""Noah in chibi style (big head, round shapes, flat colors), made in Blender.

Usage (without opening Blender):
    blender --background --factory-startup --python tools/blender/noah_chibi.py -- assets/characters/noah_chibi.glb [renders_folder]
Live, with Blender open:
    python3 tools/blender/live.py noah_chibi step_clear step_body step_head step_arms step_feet

The character has no bones: it's a hierarchy of pieces with their pivot, meant to be animated
by code in Godot (bounce when walking, arm swing, little steps, blinking):
    Noah
    ├─ Body            tunic, mantle, sash and knot (pivot at the hip)
    │  ├─ HeadMesh     face, hair, beard, brows     (pivot at the neck)
    │  │  ├─ EyeL / EyeR                            (for blinking)
    │  ├─ ArmL / ArmR  sleeve and hand              (pivot at the shoulder)
    ├─ FootL / FootR   foot with sandal             (pivot at the ankle)
Blender axes: Z up, Noah faces -Y (in Godot, toward the model's +Z).
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = globals().get("PROJECT_ROOT", os.getcwd())

COLORS = {
    "Skin": (0.91, 0.70, 0.56),
    "Tunic": (0.93, 0.87, 0.74),
    "Mantle": (0.55, 0.36, 0.22),
    "Sash": (0.73, 0.26, 0.19),
    "GrayHair": (0.97, 0.96, 0.93),
    "Leather": (0.45, 0.28, 0.16),
    "Eye": (0.16, 0.11, 0.08),
    "Glint": (1.0, 1.0, 1.0),
    "Blush": (0.95, 0.6, 0.52),
    "Trim": (0.62, 0.43, 0.27),
}

HEAD_CENTER = Vector((0, 0, 0.93))
HEAD_R = 0.27


# --- Utilities ------------------------------------------------------------------

def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        rgb = tuple(c ** 2.2 for c in COLORS[name])  # Colors thought out in sRGB.
        bsdf.inputs["Base Color"].default_value = (*rgb, 1)
        bsdf.inputs["Roughness"].default_value = 0.35 if name in ("Eye", "Glint") else 0.75
        mat.diffuse_color = (*rgb, 1)
    return mat


def finish(obj, mat_name, subdiv=1, smooth=True):
    obj.data.materials.clear()
    obj.data.materials.append(material(mat_name))
    if smooth:
        for p in obj.data.polygons:
            p.use_smooth = True
    if subdiv:
        mod = obj.modifiers.new("Smooth", "SUBSURF")
        mod.levels = subdiv
        mod.render_levels = subdiv
    return obj


def sphere(name, center, scale, mat_name, segments=24, rings=12, subdiv=1):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1.0, location=center)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(obj, mat_name, subdiv)


def lathe(name, profile, mat_name, segments=40, wave=None, cap_top=True, cap_bottom=True, subdiv=1):
    """Surface of revolution. profile: [(z, radius), ...] from bottom to top.
    wave(a, t) returns a factor that multiplies the radius (folds)."""
    bm = bmesh.new()
    rings = []
    for i, (z, r) in enumerate(profile):
        t = i / (len(profile) - 1)
        ring = []
        for s in range(segments):
            a = math.tau * s / segments
            k = wave(a, t) if wave else 1.0
            ring.append(bm.verts.new((math.cos(a) * r * k, math.sin(a) * r * k, z)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            bm.faces.new((rings[i][s], rings[i][s2], rings[i + 1][s2], rings[i + 1][s]))
    if cap_bottom:
        bm.faces.new(list(reversed(rings[0])))
    if cap_top:
        bm.faces.new(rings[-1])
    bm.normal_update()
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return finish(obj, mat_name, subdiv)


def on_head(x, z, out=0.0):
    """Point of the front surface of the head at that x, z (plus 'out' outward)."""
    d = Vector((x, 0, z)) - HEAD_CENTER
    y = -math.sqrt(max(HEAD_R ** 2 - d.x ** 2 - d.z ** 2, 0.0))
    p = HEAD_CENTER + Vector((d.x, y, d.z))
    return p + (p - HEAD_CENTER).normalized() * out


def pivot(name, location, parent=None):
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_size = 0.08
    empty.location = location
    bpy.context.scene.collection.objects.link(empty)
    if parent:
        attach(empty, parent)
    return empty


def attach(child, parent):
    bpy.context.view_layer.update()
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


def obj(name):
    return bpy.data.objects[name]


# --- Steps ----------------------------------------------------------------------

def step_clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures, bpy.data.images, bpy.data.lights,
                 bpy.data.cameras):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)
    root = pivot("Noah", (0, 0, 0))
    pivot("Body", (0, 0, 0.32), root)
    _view()


def step_body():
    body = obj("Body")

    def folds(a, t):
        # Soft folds that fade out going up.
        return 1.0 + 0.045 * (1 - t) ** 2 * math.sin(9 * a + 0.6)

    robe = lathe("Tunic", [(0.09, 0.27), (0.14, 0.265), (0.28, 0.225), (0.42, 0.2), (0.53, 0.185),
                           (0.6, 0.16), (0.65, 0.115), (0.68, 0.05)], "Tunic", wave=folds)
    hem = lathe("Trim", [(0.085, 0.276), (0.13, 0.272)], "Trim", wave=folds, cap_top=False, cap_bottom=False)
    mantle = lathe("Mantle", [(0.47, 0.215), (0.53, 0.212), (0.6, 0.19), (0.655, 0.14), (0.69, 0.07)], "Mantle",
                    wave=lambda a, t: 1.0 + 0.03 * (1 - t) * math.sin(7 * a), cap_bottom=False)
    sash = lathe("Sash", [(0.29, 0.222), (0.3, 0.232), (0.35, 0.226), (0.36, 0.214)], "Sash",
                 cap_top=False, cap_bottom=False)
    knot = sphere("Knot", (0.05, -0.225, 0.325), (0.045, 0.03, 0.04), "Sash")
    tails = []
    for i, (dx, length, tilt) in enumerate(((0.035, 0.14, 0.15), (0.07, 0.11, -0.1))):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(dx, -0.228, 0.305 - length * 0.5))
        tail = bpy.context.active_object
        tail.name = f"Ribbon{i}"
        tail.scale = (0.035, 0.012, length)
        tail.rotation_euler = (0.12, tilt, 0)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        finish(tail, "Sash", subdiv=1)
        tails.append(tail)
    for part in [robe, hem, mantle, sash, knot] + tails:
        attach(part, body)


def step_head():
    head = pivot("HeadMesh", (0, 0, 0.68), obj("Body"))
    parts = [sphere("Face", HEAD_CENTER, (HEAD_R, HEAD_R * 0.97, HEAD_R * 0.95), "Skin", 32, 16)]
    # Ears and nose.
    for sx in (1, -1):
        parts.append(sphere(f"Ear{'L' if sx > 0 else 'R'}", HEAD_CENTER + Vector((sx * 0.262, 0.01, -0.01)),
                            (0.04, 0.03, 0.055), "Skin"))
    parts.append(sphere("Nose", on_head(0, 0.885, 0.012), (0.04, 0.035, 0.035), "Skin"))
    # Blush on the cheeks.
    for sx in (1, -1):
        p = on_head(sx * 0.14, 0.87, -0.004)
        parts.append(sphere(f"Blush{'L' if sx > 0 else 'R'}", p, (0.045, 0.012, 0.03), "Blush", subdiv=0))
    # Gray hair: a horseshoe of fluffy tufts from ear to ear around the nape, stuck
    # to the skull (bald on top, like a grandfather). Three rows of overlapping little balls.
    for row, (dz, count, size) in enumerate(((-0.02, 12, 0.05), (-0.08, 12, 0.056), (-0.14, 10, 0.05))):
        ring_r = math.sqrt(HEAD_R ** 2 - dz ** 2)
        for i in range(count):
            ang = -0.12 + (math.pi + 0.24) * i / (count - 1)   # Left side -> nape -> right.
            wobble = 1.0 + 0.15 * math.sin(i * 2.3 + row * 1.7)
            out = ring_r + size * 0.05
            pos = HEAD_CENTER + Vector((math.cos(ang) * out, math.sin(ang) * out + 0.005, dz))
            parts.append(sphere(f"Hair{row}_{i}", pos, (size * wobble, size * wobble, size * 0.85 * wobble),
                                "GrayHair", 16, 8))
    # Big rounded beard, shaped like a drop.
    beard = sphere("Beard", on_head(0, 0.78, -0.05) + Vector((0, -0.02, -0.06)), (0.2, 0.13, 0.2), "GrayHair", 32, 16)
    for v in beard.data.vertices:
        if v.co.z < 0:
            v.co.x *= 1.0 + v.co.z * 2.2   # It narrows toward the tip.
        v.co.z *= 1.15 if v.co.z < 0 else 0.8
    parts.append(beard)
    # Mustache and bushy brows.
    for sx in (1, -1):
        m = sphere(f"Mustache{'L' if sx > 0 else 'R'}", on_head(sx * 0.055, 0.845, 0.01), (0.07, 0.035, 0.03), "GrayHair")
        m.rotation_euler = (0, sx * -0.35, 0)
        parts.append(m)
        b = sphere(f"Brow{'L' if sx > 0 else 'R'}", on_head(sx * 0.1, 1.005, 0.008), (0.055, 0.025, 0.022), "GrayHair")
        b.rotation_euler = (0, sx * 0.2, 0)
        parts.append(b)
    for part in parts:
        attach(part, head)
    # Eyes (their own pieces so they can blink).
    for sx, side in ((1, "L"), (-1, "R")):
        center = on_head(sx * 0.095, 0.935, 0.0)
        eye = pivot(f"Eye{side}", center, head)
        e = sphere(f"Pupil{side}", center, (0.03, 0.015, 0.045), "Eye", subdiv=0)
        g = sphere(f"Glint{side}", center + Vector((sx * -0.008, -0.012, 0.016)), (0.009, 0.005, 0.011), "Glint",
                   12, 6, subdiv=0)
        attach(e, eye)
        attach(g, eye)


def step_arms():
    body = obj("Body")
    for sx, side in ((1, "L"), (-1, "R")):
        shoulder = Vector((sx * 0.15, 0, 0.6))
        arm = pivot(f"Arm{side}", shoulder, body)
        # Sleeve flaring downward and a bit outward.
        sleeve = lathe(f"Sleeve{side}", [(-0.25, 0.085), (-0.2, 0.08), (-0.1, 0.07), (0.0, 0.06), (0.04, 0.03)],
                       "Tunic", segments=24, cap_bottom=False,
                       wave=lambda a, t: 1.0 + 0.06 * (1 - t) * math.sin(6 * a))
        sleeve.location = shoulder
        sleeve.rotation_euler = (0, -sx * 0.32, 0)
        hand_pos = shoulder + Vector((sx * math.sin(0.32) * 0.28, -0.01, -math.cos(0.32) * 0.28))
        hand = sphere(f"Hand{side}", hand_pos, (0.055, 0.05, 0.06), "Skin")
        for part in (sleeve, hand):
            attach(part, arm)


def step_feet():
    root = obj("Noah")
    for sx, side in ((1, "L"), (-1, "R")):
        ankle = Vector((sx * 0.09, -0.11, 0.07))
        foot = pivot(f"Foot{side}", ankle, root)
        skin = sphere(f"Toes{side}", ankle + Vector((0, -0.045, -0.025)), (0.06, 0.09, 0.045), "Skin")
        sole = sphere(f"Sole{side}", ankle + Vector((0, -0.04, -0.06)), (0.07, 0.105, 0.016), "Leather", subdiv=1)
        strap = lathe(f"Strap{side}", [(-0.01, 0.062), (0.012, 0.064)], "Leather", segments=20,
                       cap_top=False, cap_bottom=False)
        strap.location = ankle + Vector((0, -0.06, -0.035))
        strap.scale = (1.0, 0.8, 1.0)
        strap.rotation_euler = (1.25, 0, 0)
        for part in (skin, sole, strap):
            attach(part, foot)
    _view()


def _view():
    wm = bpy.context.window_manager
    if not wm or not wm.windows:
        return
    from mathutils import Euler
    for area in wm.windows[0].screen.areas:
        if area.type == "VIEW_3D":
            space = area.spaces.active
            space.shading.type = "MATERIAL"
            space.overlay.show_relationship_lines = False
            r3d = space.region_3d
            r3d.view_location = Vector((0, 0, 0.6))
            r3d.view_distance = 2.4
            r3d.view_rotation = Euler((math.radians(78), 0, math.radians(-28))).to_quaternion()


def step_render(folder):
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
    except TypeError:
        scene.view_settings.view_transform = "Filmic"
    world = bpy.data.worlds.get("Sky") or bpy.data.worlds.new("Sky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.78, 0.9, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    scene.world = world
    added = []
    key = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    key.data.energy = 3.2
    key.data.angle = math.radians(8)
    key.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    fill = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", "AREA"))
    fill.data.energy = 120
    fill.data.size = 2
    fill.location = (-1.5, -1.5, 1.5)
    fill.rotation_euler = (math.radians(55), 0, math.radians(-135))
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.8, depth=0.08, location=(0, 0, -0.04))
    ground = bpy.context.active_object
    ground.name = "Lawn"
    gmat = bpy.data.materials.new("Lawn")
    gmat.use_nodes = True
    gmat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.24, 0.45, 0.12, 1)
    ground.data.materials.append(gmat)
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    cam.data.lens = 70
    added += [key, fill, cam]
    for o in (key, fill, cam):
        scene.collection.objects.link(o)
    added.append(ground)
    scene.camera = cam
    shots = (("front", (1.3, -2.9, 1.25)), ("side", (2.9, -0.7, 1.1)), ("back", (-1.2, 2.9, 1.3)))
    for label, pos in shots:
        cam.location = pos
        cam.rotation_euler = (Vector((0, 0, 0.6)) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(folder, f"noah_chibi_{label}.png")
        bpy.ops.render.render(write_still=True)
    for o in added:
        bpy.data.objects.remove(o)


def step_export(out_path):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True, export_animations=False)
    print(f"NOAH OK -> {out_path}")


STEPS = [step_clear, step_body, step_head, step_arms, step_feet]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = argv[0] if argv else "noah_chibi.glb"
    renders = argv[1] if len(argv) > 1 else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for step in STEPS:
        step()
    if renders:
        step_render(renders)
    step_export(out_path)


if not globals().get("LIVE"):
    main()
