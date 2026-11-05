"""Noah following the reference turnaround sheet (references/noah_turnaround.png), made in Blender.

Usage (without opening Blender):
    blender --background --factory-startup --python tools/blender/noah.py -- assets/characters/noah.glb [renders_folder]
Live, with Blender open:
    python3 tools/blender/live.py noah step_clear step_references step_body step_head step_arms step_feet

The measurements come from the turnaround sheet: the figure is 478 px tall and is scaled to 1.55 m (3.24 mm per px).
The profiles (width seen from the front and depth seen from the side, height by height) are in the tables
below. The colors are those of references/palette.png.

No bones: a hierarchy of pieces with their pivot, to animate them by code in Godot:
    Noah
    ├─ Body                  tunic, overtunic, rope belt              (pivot at the hip)
    │  ├─ HeadMesh           face, hair, beard, brows               (pivot at the neck)
    │  │  ├─ EyeL / EyeR                                            (for blinking)
    │  ├─ ArmL / ArmR        sleeve and hand                        (pivot at the shoulder)
    ├─ FootL / FootR         foot, leg and sandal                   (pivot at the ankle)
Blender axes: Z up, Noah faces -Y. The center of the body is at the origin.
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = globals().get("PROJECT_ROOT", os.getcwd())
REF_SHEET = os.path.join(ROOT, "references/noah_turnaround.png")

PX = 1.55 / 478                  # Meters per pixel on the turnaround sheet.
REF_BASE_Y = 532                 # Row of the base of the feet in the image.
REF_FRONT_X = 165.5              # Center of the front figure.
REF_SIDE_X = 403.5               # Center of the body in the side figure.

# Palette (references/palette.png) and derived tones.
COLORS = {
    "Skin": "FCD4B7",
    "Nose": "EDA88A",
    "Blush": "F2A898",
    "GrayHair": "EFEFEF",
    "Tunic": "DDD3C0",
    "Sleeve": "C8AE86",
    "Mantle": "A55B2E",
    "Belt": "5E3918",
    "Sandal": "3F2A1D",
    "Eye": "3A2418",
    "Glint": "FFFFFF",
}

# Measured profiles: (z, front half width, side half depth, center in Y).
TUNIC = [(0.175, 0.24, 0.19, 0.0), (0.24, 0.237, 0.188, 0.0), (0.32, 0.23, 0.18, 0.0), (0.5, 0.2, 0.16, 0.0),
         (0.7, 0.19, 0.155, 0.0), (0.9, 0.19, 0.155, 0.0), (1.02, 0.195, 0.152, 0.0), (1.09, 0.17, 0.135, 0.0),
         (1.14, 0.11, 0.1, 0.005), (1.17, 0.06, 0.06, 0.01)]
VEST = [(0.32, 0.253, 0.197, 0.0), (0.45, 0.232, 0.19, 0.0), (0.6, 0.212, 0.176, 0.0), (0.75, 0.206, 0.168, 0.0),
        (0.9, 0.206, 0.166, 0.0), (1.0, 0.222, 0.17, 0.0), (1.07, 0.228, 0.162, 0.0), (1.12, 0.17, 0.135, 0.005),
        (1.155, 0.105, 0.095, 0.01)]
BELT_Z = 0.70
HEAD_CENTER = Vector((0, -0.03, 1.335))
SKULL = Vector((0.15, 0.155, 0.19))    # Semi-axes of the skull.
NECK_Z = 1.14
SHOULDER = Vector((0.18, 0.0, 1.035))
HAND = Vector((0.36, -0.01, 0.6))


# --- Utilities ------------------------------------------------------------------

def srgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        rgb = tuple(c ** 2.2 for c in srgb(COLORS[name]))
        bsdf.inputs["Base Color"].default_value = (*rgb, 1)
        bsdf.inputs["Roughness"].default_value = 0.3 if name in ("Eye", "Glint") else 0.65
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


def lathe(name, profile, mat_name, segments=48, wave=None, cap_top=True, cap_bottom=True, subdiv=1, skip=None):
    """Elliptical surface of revolution. profile: [(z, half width x, half depth y, center y), ...].
    wave(a, t) multiplies the radius (folds); skip(a, t) removes those faces (openings)."""
    bm = bmesh.new()
    rings = []
    for i, (z, rx, ry, cy) in enumerate(profile):
        t = i / (len(profile) - 1)
        ring = []
        for s in range(segments):
            a = math.tau * s / segments
            k = wave(a, t) if wave else 1.0
            ring.append(bm.verts.new((math.cos(a) * rx * k, cy + math.sin(a) * ry * k, z)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            a = math.tau * (s + 0.5) / segments
            if skip and skip(a, (i + 0.5) / (len(rings) - 1)):
                continue
            bm.faces.new((rings[i][s], rings[i][s2], rings[i + 1][s2], rings[i + 1][s]))
    if cap_bottom:
        bm.faces.new(list(reversed(rings[0])))
    if cap_top:
        bm.faces.new(rings[-1])
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.normal_update()
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return finish(obj, mat_name, subdiv)


def tube(name, points, radii, mat_name, segments=16, subdiv=1, twist=None):
    """Tube that follows a list of points (rope, sleeves, legs)."""
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(points):
        a = points[max(i - 1, 0)]
        b = points[min(i + 1, len(points) - 1)]
        t = (b - a).normalized()
        side = t.cross(Vector((0, 0, 1))) if abs(t.z) < 0.95 else t.cross(Vector((1, 0, 0)))
        side.normalize()
        up = side.cross(t).normalized()
        ring = []
        for s in range(segments):
            ang = math.tau * s / segments
            r = radii[i] * (twist(i, ang) if twist else 1.0)
            ring.append(bm.verts.new(p + (side * math.cos(ang) + up * math.sin(ang)) * r))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            bm.faces.new((rings[i][s], rings[i][s2], rings[i + 1][s2], rings[i + 1][s]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bm.normal_update()
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return finish(obj, mat_name, subdiv)


def solidify(obj, thickness, offset=-1):
    mod = obj.modifiers.new("Thickness", "SOLIDIFY")
    mod.thickness = thickness
    mod.offset = offset
    obj.modifiers.move(len(obj.modifiers) - 1, 0)


def on_head(x, z, out=0.0):
    """Point of the face (front part of the skull) at that x, z, plus 'out' outward."""
    d = Vector((x, 0, z)) - HEAD_CENTER
    k = 1.0 - (d.x / SKULL.x) ** 2 - (d.z / SKULL.z) ** 2
    y = -SKULL.y * math.sqrt(max(k, 0.0))
    p = HEAD_CENTER + Vector((d.x, y, d.z))
    normal = Vector((d.x / SKULL.x ** 2, y / SKULL.y ** 2, d.z / SKULL.z ** 2)).normalized()
    return p + normal * out


def pivot(name, location, parent=None):
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_size = 0.05
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


def front_angle(a):
    """Angular distance to the front (-Y), in radians."""
    return abs(math.atan2(math.sin(a + math.pi / 2), math.cos(a + math.pi / 2)))


# --- Steps ----------------------------------------------------------------------

def step_clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)
    root = pivot("Noah", (0, 0, 0))
    pivot("Body", (0, 0, BELT_Z), root)
    _view()


def step_references():
    """The turnaround sheet behind the model, to scale: front view and side view."""
    img = bpy.data.images.load(REF_SHEET, check_existing=True)
    w, h = img.size
    for label, rot, loc_x, loc_y, ref_x in (
            ("RefFront", (math.pi / 2, 0, 0), None, 0.9, REF_FRONT_X),
            ("RefSide", (math.pi / 2, 0, -math.pi / 2), 0.9, None, REF_SIDE_X)):
        ref = bpy.data.objects.new(label, None)
        ref.empty_display_type = "IMAGE"
        ref.data = img
        ref.empty_display_size = w * PX
        ref.empty_image_offset = (0, 0)
        ref.rotation_euler = rot
        # The image is placed so the reference figure sits right behind Noah.
        offset_x = -ref_x * PX
        offset_z = -(h - REF_BASE_Y) * PX
        if label == "RefFront":
            ref.location = (offset_x, loc_y, offset_z)
        else:
            ref.location = (loc_x, -offset_x, offset_z)
        ref.color[3] = 0.55
        ref.use_empty_image_alpha = True
        ref.show_empty_image_perspective = False
        bpy.context.scene.collection.objects.link(ref)


def step_body():
    body = obj("Body")
    folds = lambda a, t: 1.0 + 0.035 * (1 - t) ** 3 * math.sin(11 * a + 0.4)
    tunic = lathe("Tunic", TUNIC, "Tunic", wave=folds)

    # Sleeveless overtunic, open in front with straight edges and armholes for the arms.
    def openings(a, t):
        z = VEST[0][0] + (VEST[-1][0] - VEST[0][0]) * t
        front = front_angle(a) < (0.42 if z < 1.0 else 0.42 + (z - 1.0) * 4.0)
        side = abs(math.cos(a)) > 0.8 and 0.88 < z < 1.11 and abs(math.sin(a)) < 0.55
        return front or side

    vest = lathe("Overtunic", VEST, "Mantle", segments=64, cap_top=False, cap_bottom=False, skip=openings,
                 wave=lambda a, t: 1.0 + 0.025 * (1 - t) ** 2 * math.sin(7 * a + 1.0))
    solidify(vest, 0.022)

    # Braided rope belt with a knot and two hanging ends.
    rope_pts = []
    for i in range(65):
        a = math.tau * i / 64
        rope_pts.append(Vector((math.cos(a) * 0.218, math.sin(a) * 0.182, BELT_Z + 0.004 * math.sin(a * 3))))
    rope = tube("Rope", rope_pts, [0.016] * len(rope_pts), "Belt", segments=10,
                twist=lambda i, ang: 1.0 + 0.25 * math.sin(ang * 2 + i * 1.7))
    knot = sphere("Knot", (-0.03, -0.19, BELT_Z - 0.005), (0.032, 0.024, 0.03), "Belt")
    ends = []
    for j, (dx, length) in enumerate(((-0.045, 0.15), (-0.012, 0.13))):
        pts = [Vector((dx, -0.195 - 0.004 * k, BELT_Z - 0.02 - length * k / 6)) for k in range(7)]
        ends.append(tube(f"RopeEnd{j}", pts, [0.014] * 6 + [0.018], "Belt", segments=8,
                         twist=lambda i, ang: 1.0 + 0.2 * math.sin(ang * 2 + i * 2.1)))
    for part in [tunic, vest, rope, knot] + ends:
        attach(part, body)


def step_head():
    head = pivot("HeadMesh", (0, -0.01, NECK_Z), obj("Body"))
    parts = [sphere("Face", HEAD_CENTER, SKULL, "Skin", 32, 16)]
    for sx in (1, -1):
        side = "L" if sx > 0 else "R"
        parts.append(sphere(f"Ear{side}", HEAD_CENTER + Vector((sx * 0.148, 0.005, -0.035)), (0.022, 0.03, 0.045),
                            "Skin"))
        parts.append(sphere(f"Blush{side}", on_head(sx * 0.085, 1.275, -0.004), (0.035, 0.012, 0.022), "Blush",
                            subdiv=0))
    parts.append(sphere("Nose", on_head(0, 1.275, 0.03), (0.046, 0.042, 0.042), "Nose"))

    # Hair: a cap over the skull with the forehead uncovered.
    cap = sphere("Hair", HEAD_CENTER + Vector((0, 0.008, 0.012)), SKULL + Vector((0.018, 0.02, 0.018)), "GrayHair",
                 40, 20)
    bm = bmesh.new()
    bm.from_mesh(cap.data)
    gone = [v for v in bm.verts if v.co.y < -0.035 and v.co.z > -0.07 - 0.25 * max(0.0, abs(v.co.x) - 0.08)]
    bmesh.ops.delete(bm, geom=gone, context="VERTS")
    bm.to_mesh(cap.data)
    bm.free()
    solidify(cap, 0.025)
    parts.append(cap)
    # Bald spot on the crown (seen from behind).
    crown = HEAD_CENTER + Vector((0, 0.07, SKULL.z * 0.93))
    parts.append(sphere("BaldSpot", crown, (0.06, 0.05, 0.03), "Skin"))
    # Long hair: long locks that come out of the head and fall down the back, ending in a point.
    # Hair base under the locks, so they read as a single mass with grooves.
    base = lathe("LongHairBase", [(1.06, 0.15, 0.085, 0.09), (1.15, 0.172, 0.12, 0.065), (1.26, 0.18, 0.15, 0.035),
                                  (1.36, 0.175, 0.168, 0.005), (1.45, 0.155, 0.158, -0.01)],
                 "GrayHair", segments=40, cap_top=False, cap_bottom=False,
                 skip=lambda a, t: front_angle(a) < 0.8 + 0.4 * t)
    base.location = (0, -0.03, 0)
    solidify(base, 0.03)
    parts.append(base)
    for i in range(21):
        u = i / 20
        ang = math.radians(-20 + 220 * u)      # From one side to the other going past the nape (+Y).
        side_k = abs(math.cos(ang))            # 1 at the sides, 0 at the nape.
        top = 1.47 - 0.05 * side_k
        length = 0.42 + 0.06 * math.sin(i * 1.9) - 0.12 * side_k
        pts, radii = [], []
        for k in range(9):
            t = k / 8
            z = top - length * t
            # Stuck to the head at the top; lower down it falls a bit backward, outside the overtunic.
            r = 0.175 + 0.02 * t + 0.015 * math.sin(t * math.pi)
            back = 0.05 * t * (1 - side_k)
            p = Vector((math.cos(ang) * r, HEAD_CENTER.y + 0.02 + math.sin(ang) * r * 0.95 + back, z))
            p.x += 0.012 * math.sin(t * 5 + i)  # Wavy.
            pts.append(p)
            radii.append((0.05 - 0.036 * t ** 1.6) * (1.0 + 0.15 * math.sin(i * 2.7)))
        parts.append(tube(f"Lock{i}", pts, radii, "GrayHair", segments=10))
    # Big beard from the cheeks down to the chest, ending in a point.
    beard = sphere("Beard", (0, -0.15, 1.115), (0.165, 0.11, 0.2), "GrayHair", 40, 20)
    for v in beard.data.vertices:
        c = v.co
        if c.z < 0:
            k = -c.z / 0.2
            c.x *= 1.0 - 0.75 * k ** 1.3        # It narrows down to the tip.
            c.y = c.y * (1.0 - 0.35 * k) - 0.06 * k ** 1.5
            c.z *= 1.0 + 0.05 * k
        # Vertical locks.
        ang = math.atan2(c.y, c.x)
        r = Vector((c.x, c.y, 0))
        if r.length > 1e-4:
            bump = 0.006 * math.sin(ang * 14) * min(1.0, max(0.0, -c.z / 0.1 + 0.3))
            c.x += r.normalized().x * bump
            c.y += r.normalized().y * bump
    parts.append(beard)
    for sx in (1, -1):
        side = "L" if sx > 0 else "R"
        # Sideburns: they join the long hair with the beard in front of the ears.
        parts.append(sphere(f"Sideburn{side}", HEAD_CENTER + Vector((sx * 0.128, -0.06, -0.09)),
                            (0.045, 0.06, 0.09), "GrayHair"))
        # Wide mustache drooping to the sides.
        m = sphere(f"Mustache{side}", on_head(sx * 0.05, 1.225, 0.03), (0.06, 0.03, 0.026), "GrayHair")
        m.rotation_euler = (0, sx * -0.45, 0)
        parts.append(m)
        # Bushy brows, higher on the inside.
        b = sphere(f"Brow{side}", on_head(sx * 0.064, 1.365, 0.012), (0.052, 0.024, 0.026), "GrayHair")
        b.rotation_euler = (0, sx * 0.1, 0)
        parts.append(b)
    for part in parts:
        attach(part, head)
    # Small dark eyes with a glint (their own pieces, for blinking).
    for sx, side in ((1, "L"), (-1, "R")):
        center = on_head(sx * 0.055, 1.312, 0.002)
        eye = pivot(f"Eye{side}", center, head)
        iris = sphere(f"Iris{side}", center, (0.016, 0.009, 0.022), "Eye", subdiv=0)
        glint = sphere(f"Glint{side}", center + Vector((sx * -0.005, -0.008, 0.008)), (0.005, 0.003, 0.006),
                       "Glint", 12, 6, subdiv=0)
        for part in (iris, glint):
            attach(part, eye)


def step_arms():
    body = obj("Body")
    for sx, side in ((1, "L"), (-1, "R")):
        shoulder = SHOULDER * Vector((sx, 1, 1))
        hand = HAND * Vector((sx, 1, 1))
        arm = pivot(f"Arm{side}", shoulder, body)
        direction = (hand - shoulder).normalized()
        wrist = hand - direction * 0.04
        pts = [shoulder + (wrist - shoulder) * (k / 8) for k in range(9)]
        radii = [0.062, 0.06, 0.057, 0.055, 0.054, 0.053, 0.053, 0.054, 0.056]
        sleeve = tube(f"Sleeve{side}", pts, radii, "Sleeve", segments=20)
        shoulder_cap = sphere(f"Shoulder{side}", shoulder + Vector((-sx * 0.01, 0, -0.005)), (0.06, 0.062, 0.058),
                              "Sleeve")
        # Big relaxed hand: a single smooth piece with the thumb.
        palm = sphere(f"Hand{side}", hand + direction * 0.01, (0.04, 0.028, 0.068), "Skin")
        palm.rotation_euler = (0.1, -sx * 0.3, 0)
        thumb = sphere(f"Thumb{side}", hand + Vector((-sx * 0.014, -0.026, 0.018)), (0.015, 0.015, 0.03), "Skin")
        thumb.rotation_euler = (0, sx * 0.4, 0)
        for part in (sleeve, shoulder_cap, palm, thumb):
            attach(part, arm)


def step_feet():
    root = obj("Noah")
    for sx, side in ((1, "L"), (-1, "R")):
        ankle = Vector((sx * 0.11, 0.035, 0.065))
        foot = pivot(f"Foot{side}", ankle, root)
        leg = tube(f"Foot{side}Skin", [ankle + Vector((0, 0, 0.14)), ankle + Vector((0, 0, 0.02)),
                                       ankle + Vector((0, -0.04, -0.02)), ankle + Vector((0, -0.11, -0.03)),
                                       ankle + Vector((0, -0.15, -0.032))],
                   [0.05, 0.05, 0.05, 0.046, 0.032], "Skin", segments=16)
        sole = sphere(f"Sole{side}", ankle + Vector((0, -0.07, -0.05)), (0.068, 0.13, 0.022), "Sandal")
        strap = lathe(f"Strap{side}", [(-0.016, 0.054, 0.036, 0.0), (0.016, 0.056, 0.038, 0.0)], "Sandal",
                      segments=24, cap_top=False, cap_bottom=False)
        strap.location = ankle + Vector((0, -0.09, -0.04))
        strap.rotation_euler = (1.35, 0, 0)
        for part in (leg, sole, strap):
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
            r3d.view_location = Vector((0, 0, 0.8))
            r3d.view_distance = 3.2
            r3d.view_rotation = Euler((math.radians(82), 0, math.radians(-30))).to_quaternion()


def _lights(scene):
    world = bpy.data.worlds.get("Sky") or bpy.data.worlds.new("Sky")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
    scene.world = world
    key = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    key.data.energy = 2.0
    key.data.color = (1.0, 0.96, 0.9)
    key.data.angle = math.radians(25)
    key.rotation_euler = (math.radians(45), math.radians(8), math.radians(-30))
    scene.collection.objects.link(key)
    rim = bpy.data.objects.new("RimLight", bpy.data.lights.new("RimLight", "SUN"))
    rim.data.energy = 1.2
    rim.rotation_euler = (math.radians(60), 0, math.radians(160))
    scene.collection.objects.link(rim)
    return [key, rim]


def _engine(scene):
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            return
        except TypeError:
            continue


def step_compare(folder):
    """Orthographic renders at the same scale and framing as the turnaround sheet (front and side),
    with a transparent background, to overlay them on the reference."""
    scene = bpy.context.scene
    _engine(scene)
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 572
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    added = _lights(scene)
    for o in bpy.data.objects:
        if o.name.startswith("Ref"):
            o.hide_render = True
    cam = bpy.data.objects.new("OrthoCamera", bpy.data.cameras.new("OrthoCamera"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 1024 * PX
    scene.collection.objects.link(cam)
    scene.camera = cam
    added.append(cam)
    cz = (REF_BASE_Y - 286) * PX
    # Front: camera at -Y looking toward +Y (the right of the image is +X).
    cam.location = ((512 - REF_FRONT_X) * PX, -5, cz)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    scene.render.filepath = os.path.join(folder, "compare_front.png")
    bpy.ops.render.render(write_still=True)
    # Side: camera at -X looking toward +X (the right of the image is -Y, where Noah is facing).
    cam.location = (-5, -(512 - REF_SIDE_X) * PX, cz)
    cam.rotation_euler = (math.pi / 2, 0, -math.pi / 2)
    scene.render.filepath = os.path.join(folder, "compare_side.png")
    bpy.ops.render.render(write_still=True)
    for o in added:
        bpy.data.objects.remove(o)


def step_render(folder):
    scene = bpy.context.scene
    _engine(scene)
    # Same scale as the turnaround sheet (to put them side by side).
    scene.render.resolution_x = 320
    scene.render.resolution_y = 572
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    added = _lights(scene)
    for o in bpy.data.objects:
        if o.name.startswith("Ref"):
            o.hide_render = True
    cam = bpy.data.objects.new("OrthoCamera", bpy.data.cameras.new("OrthoCamera"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 572 * PX
    scene.collection.objects.link(cam)
    scene.camera = cam
    added.append(cam)
    cz = (REF_BASE_Y - 286) * PX
    views = (("front", (0, -5, cz), (math.pi / 2, 0, 0)),
             ("side", (-5, 0, cz), (math.pi / 2, 0, -math.pi / 2)),
             ("back", (0, 5, cz), (math.pi / 2, 0, math.pi)),
             ("three_quarters", (3.2, -3.8, cz), (math.pi / 2, 0, math.radians(40))))
    for label, loc, rot in views:
        cam.location = loc
        cam.rotation_euler = rot
        scene.render.filepath = os.path.join(folder, f"noah_{label}.png")
        bpy.ops.render.render(write_still=True)
    for o in added:
        bpy.data.objects.remove(o)


def step_export(out_path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        if not o.name.startswith("Ref"):
            o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True, export_animations=False)
    print(f"NOAH OK -> {out_path}")


STEPS = [step_clear, step_references, step_body, step_head, step_arms, step_feet]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = argv[0] if argv else "noah.glb"
    renders = argv[1] if len(argv) > 1 else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for step in STEPS:
        step()
    if renders:
        step_compare(renders)
        step_render(renders)
    step_export(out_path)


if not globals().get("LIVE"):
    main()
