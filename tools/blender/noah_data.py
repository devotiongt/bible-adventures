"""Noah rebuilt from the references (not by eye).

Input data, generated from references/noah_turnaround.png:
    references/noah_parts.png      the turnaround sheet segmented by parts (hair, skin, mantle, sleeve…)
    references/noah_volumes.json  each volume measured by heights: width of the front half (front
                                    view), of the back half (back view) and depth (side view)

Each volume is built section by section with those measurements, and each face takes the color of the
part seen in the view it faces (projection). That way the vest, the tunic, the rope,
the sleeves, the beard and the hair end up where they are in the reference.

Usage:
    blender --background --factory-startup --python tools/blender/noah_data.py -- assets/characters/noah.glb [renders_folder]
    python3 tools/blender/live.py noah_data step_clear step_clothes step_head step_features step_arms step_feet
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = globals().get("PROJECT_ROOT", os.getcwd())
REF_SHEET = os.path.join(ROOT, "references/noah_turnaround.png")
PARTS_SHEET = os.path.join(ROOT, "references/noah_parts.png")
VOLUMES = os.path.join(ROOT, "references/noah_volumes.json")

PX = 1.55 / 478
REF_BASE_Y = 532
VIEW_X = {"front": 165.5, "side": 403.5, "back": 625.5}

# Color of each part in the segmented image -> material.
PART_COLORS = {
    "GrayHair": (235, 235, 245), "Skin": (252, 212, 183), "Nose": (235, 120, 100), "Eye": (30, 20, 15),
    "Mantle": (165, 91, 46), "Sleeve": (200, 174, 134), "Tunic": (221, 211, 192), "Rope": (94, 57, 24),
    "Sandal": (40, 30, 25),
}
# Final colors (palette from references/palette.png).
MATERIALS = {
    "GrayHair": "EFEFEF", "Skin": "FCD4B7", "Nose": "EDA88A", "Eye": "3A2418", "Mantle": "A55B2E",
    "Sleeve": "C8AE86", "Tunic": "DDD3C0", "Rope": "5E3918", "Sandal": "3F2A1D", "Glint": "FFFFFF",
}
# Section shape of each volume (2 = ellipse, more = squarer) and default part.
VOLUME_STYLE = {
    "body": (2.6, "Mantle"), "head": (2.2, "GrayHair"), "armL": (2.0, "Sleeve"), "armR": (2.0, "Sleeve"),
    "footL": (2.2, "Sandal"), "footR": (2.2, "Sandal"),
}


def srgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        rgb = tuple(c ** 2.2 for c in srgb(MATERIALS[name]))
        bsdf.inputs["Base Color"].default_value = (*rgb, 1)
        bsdf.inputs["Roughness"].default_value = 0.6
        mat.diffuse_color = (*rgb, 1)
    return mat


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


def _smooth(values, sigma=5.0):
    """Smooth fit of a measured curve: median (removes spikes) and then a Gaussian filter."""
    n = len(values)
    med = []
    for i in range(n):
        lo, hi = max(0, i - 3), min(n, i + 4)
        med.append(sorted(values[lo:hi])[(hi - lo) // 2])
    radius = int(sigma * 3)
    weights = [math.exp(-(k * k) / (2 * sigma * sigma)) for k in range(-radius, radius + 1)]
    out = []
    for i in range(n):
        acc = wsum = 0.0
        for k, w in zip(range(-radius, radius + 1), weights):
            j = min(max(i + k, 0), n - 1)
            acc += med[j] * w
            wsum += w
        out.append(acc / wsum)
    return out


def _superellipse(c, n):
    return math.copysign(abs(c) ** (2.0 / n), c)


def build_volume(name, sections, n, segments=48, smooth=True):
    """Joins the measured sections into a closed mesh. Each section blends the width of the front
    half (front view) with that of the back half (back view)."""
    sections = sorted(sections, key=lambda s: s["z"])
    sm = _smooth if smooth else (lambda v: v)
    keys = {
        "z": [s["z"] for s in sections],
        "fa": sm([s["fx"][0] for s in sections]), "fb": sm([s["fx"][1] for s in sections]),
        "ba": sm([s["bx"][0] for s in sections]), "bb": sm([s["bx"][1] for s in sections]),
        "front": sm([s["front"] for s in sections]), "back": sm([s["back"] for s in sections]),
    }
    bm = bmesh.new()
    rings = []
    for i, z in enumerate(keys["z"]):
        f_center = (keys["fa"][i] + keys["fb"][i]) / 2
        f_half = (keys["fb"][i] - keys["fa"][i]) / 2
        b_center = (keys["ba"][i] + keys["bb"][i]) / 2
        b_half = (keys["bb"][i] - keys["ba"][i]) / 2
        front, back = keys["front"][i], keys["back"][i]
        y_mid = (back - front) / 2          # Blender: front is -Y.
        depth = (front + back) / 2
        ring = []
        for s in range(segments):
            a = math.tau * s / segments
            ca, sa = math.cos(a), math.sin(a)
            t = (1 + sa) / 2                  # 0 front, 1 back.
            cx = f_center * (1 - t) + b_center * t
            half = f_half * (1 - t) + b_half * t
            ring.append(bm.verts.new((cx + half * _superellipse(ca, n), y_mid + depth * _superellipse(sa, n), z)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            bm.faces.new((rings[i][s], rings[i][s2], rings[i + 1][s2], rings[i + 1][s]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    for p in mesh.polygons:
        p.use_smooth = True
    return obj


# --- Reading the segmented image ------------------------------------------------

_parts = None


def _parts_image():
    global _parts
    if _parts is None:
        img = bpy.data.images.load(PARTS_SHEET, check_existing=True)
        w, h = img.size
        px = list(img.pixels)
        _parts = (w, h, px)
    return _parts


def _part_at(view, x, z):
    """Part seen in the given view at the point (x sideways, z height), looking at a 5x5 neighborhood."""
    w, h, px = _parts_image()
    col = VIEW_X[view] + x / PX
    row_top = REF_BASE_Y - z / PX           # Row counted from the top.
    votes = {}
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            cxp, cyp = int(round(col + dx)), int(round(row_top + dy))
            if not (0 <= cxp < w and 0 <= cyp < h):
                continue
            i = ((h - 1 - cyp) * w + cxp) * 4    # Blender stores the rows from bottom to top.
            rgb = tuple(px[i + k] * 255 for k in range(3))
            if min(rgb) > 245:
                continue
            best = min(PART_COLORS, key=lambda k: sum((rgb[j] - PART_COLORS[k][j]) ** 2 for j in range(3)))
            votes[best] = votes.get(best, 0) + 1
    return max(votes, key=votes.get) if votes else None


# --- Measurements read on the reference with the metric ruler (meters) -------------
# (Blender: front is -Y; in the side view, positive "front" becomes -Y.)
M = {
    "tunic_bottom": 0.175, "mantle_bottom": 0.32, "mantle_top": 1.12, "opening": 0.075,
    "shoulder": Vector((0.24, 0.0, 1.065)), "cuff": Vector((0.33, -0.01, 0.655)),
    "sleeve_r": (0.055, 0.074), "hand": Vector((0.35, -0.02, 0.585)), "hand_size": (0.048, 0.034, 0.069),
    "rope": (0.69, 0.725), "knot": Vector((0.012, 0.0, 0.69)), "rope_ends": (0.53, (-0.026, 0.03)),
    "eye": Vector((0.076, 0.0, 1.33)), "eye_size": (0.012, 0.009, 0.018),
    "brow": Vector((0.09, 0.0, 1.384)), "brow_size": (0.042, 0.016, 0.015),
    "nose": Vector((0.0, -0.232, 1.29)), "nose_size": (0.034, 0.036, 0.036),
    "mustache": (1.225, 0.11), "ear": Vector((0.196, -0.015, 1.32)), "ear_size": (0.022, 0.03, 0.04),
    "foot_x": 0.125, "foot_y": (0.1, -0.167), "foot_half_width": 0.065, "leg_r": 0.05,
}


# Torso outline read with the ruler on the reference:
# (height, front/back half width, depth toward the front, depth toward the back).
TORSO_RULER = [
    (0.175, 0.24, 0.175, 0.2), (0.25, 0.243, 0.178, 0.205), (0.32, 0.25, 0.18, 0.21), (0.42, 0.235, 0.177, 0.205),
    (0.52, 0.222, 0.172, 0.195), (0.62, 0.21, 0.165, 0.182), (0.7, 0.205, 0.165, 0.172), (0.8, 0.203, 0.155, 0.162),
    (0.9, 0.208, 0.15, 0.158), (1.0, 0.225, 0.145, 0.158), (1.07, 0.245, 0.14, 0.158), (1.12, 0.23, 0.12, 0.14),
    (1.15, 0.14, 0.08, 0.1), (1.17, 0.07, 0.05, 0.06),
]


def _torso_sections(step=0.01):
    """Torso sections every centimeter, interpolating the table with a smooth curve (Catmull-Rom)."""
    rows = TORSO_RULER
    out = []
    z = rows[0][0]
    while z <= rows[-1][0] + 1e-6:
        i = max(k for k in range(len(rows) - 1) if rows[k][0] <= z + 1e-9) if z < rows[-1][0] else len(rows) - 2
        p0, p1, p2, p3 = rows[max(i - 1, 0)], rows[i], rows[i + 1], rows[min(i + 2, len(rows) - 1)]
        t = (z - p1[0]) / (p2[0] - p1[0])
        vals = []
        for k in (1, 2, 3):
            a, b, c, d = p0[k], p1[k], p2[k], p3[k]
            vals.append(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (-a + 3 * b - 3 * c + d) * t ** 3))
        hw, front, back = vals
        out.append({"z": z, "fx": [-hw, hw], "bx": [-hw, hw], "front": front, "back": back})
        z += step
    return out


def _sections_fit(data, z0, z1, scale=1.0, sigma=8.0):
    """Sections of the measured volume between z0 and z1, with an even smoother fit (clean shape)."""
    secs = [s for s in data if z0 <= s["z"] <= z1]
    out = []
    keys = ("fx", "bx")
    zs = [s["z"] for s in secs]
    smooth = {}
    for k in ("fa", "fb", "ba", "bb", "front", "back"):
        if k in ("fa", "fb"):
            vals = [s["fx"][0 if k == "fa" else 1] for s in secs]
        elif k in ("ba", "bb"):
            vals = [s["bx"][0 if k == "ba" else 1] for s in secs]
        else:
            vals = [s[k] for s in secs]
        smooth[k] = _smooth(vals, sigma)
    for i, z in enumerate(zs):
        out.append({"z": z, "fx": [smooth["fa"][i] * scale, smooth["fb"][i] * scale],
                    "bx": [smooth["ba"][i] * scale, smooth["bb"][i] * scale],
                    "front": smooth["front"][i] * scale, "back": smooth["back"][i] * scale})
    return out


def _sym(secs):
    """Makes the torso symmetric from left to right (the reference is; that removes the noise)."""
    for s in secs:
        for k in ("fx", "bx"):
            half = (s[k][1] - s[k][0]) / 2
            s[k] = [-half, half]
    return secs


def _mesh_from(name, secs, n, mat, segments=56, skip=None):
    obj = build_volume(name, secs, n, segments, smooth=False)
    obj.data.materials.append(material(mat))
    if skip:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        gone = [f for f in bm.faces if skip(f.calc_center_median())]
        bmesh.ops.delete(bm, geom=gone, context="FACES")
        bm.to_mesh(obj.data)
        bm.free()
    return obj


def _subsurf(obj, level=2):
    mod = obj.modifiers.new("Smooth", "SUBSURF")
    mod.levels = level
    mod.render_levels = level


def _solidify(obj, t):
    mod = obj.modifiers.new("Thickness", "SOLIDIFY")
    mod.thickness = t
    mod.offset = 1.0
    obj.modifiers.move(len(obj.modifiers) - 1, 0)


def _sphere(name, center, size, mat, parent):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0, location=center)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(material(mat))
    for p in o.data.polygons:
        p.use_smooth = True
    attach(o, parent)
    return o


def _tube(name, pts, radii, mat, parent, segments=20):
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
        t = (b - a).normalized()
        side = t.cross(Vector((0, 1, 0))) if abs(t.y) < 0.9 else t.cross(Vector((1, 0, 0)))
        side.normalize()
        up = side.cross(t).normalized()
        rings.append([bm.verts.new(p + (side * math.cos(a2) + up * math.sin(a2)) * radii[i])
                      for a2 in [math.tau * k / segments for k in range(segments)]])
    for i in range(len(rings) - 1):
        for k in range(segments):
            k2 = (k + 1) % segments
            bm.faces.new((rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    o = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(material(mat))
    for p in o.data.polygons:
        p.use_smooth = True
    attach(o, parent)
    return o


def step_clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)
    global _parts
    _parts = None
    root = pivot("Noah", (0, 0, 0))
    pivot("Body", (0, 0, 0.7), root)
    _view()


def step_clothes():
    """Tunic, sleeveless overtunic open in front and rope, with the measured outline."""
    data = json.load(open(VOLUMES))
    body = bpy.data.objects["Body"]
    outer = _torso_sections()
    # Tunic: the measured volume, a bit inside where the mantle covers it.
    inner = [dict(s, fx=[v * (0.97 if s["z"] > M["mantle_bottom"] else 1.0) for v in s["fx"]],
                  bx=[v * (0.97 if s["z"] > M["mantle_bottom"] else 1.0) for v in s["bx"]],
                  front=s["front"] * (0.97 if s["z"] > M["mantle_bottom"] else 1.0),
                  back=s["back"] * (0.97 if s["z"] > M["mantle_bottom"] else 1.0)) for s in outer]
    tunic = _mesh_from("Tunic", inner, 2.6, "Tunic")
    _subsurf(tunic)
    attach(tunic, body)
    # Overtunic: the outer skin of the volume, from 0.32 to 1.12, with the straight front opening.
    vest_secs = [s for s in outer if s["z"] >= M["mantle_bottom"] - 0.005]
    vest = _mesh_from("Overtunic", vest_secs, 2.6, "Mantle",
                      skip=lambda c: c.y < 0 and abs(c.x) < M["opening"] or c.z < M["mantle_bottom"] + 0.001
                      or c.z > M["mantle_top"] - 0.002)
    _solidify(vest, 0.018)
    _subsurf(vest)
    attach(vest, body)
    # Rope: follows the same outline (superellipse) of the torso at waist height.
    zc = sum(M["rope"]) / 2
    sec = min(outer, key=lambda s: abs(s["z"] - zc))
    half_x = (sec["fx"][1] - sec["fx"][0]) / 2 + 0.02
    y_mid = (sec["back"] - sec["front"]) / 2
    depth = (sec["front"] + sec["back"]) / 2 + 0.02
    ring = [Vector((half_x * _superellipse(math.cos(a), 2.6), y_mid + depth * _superellipse(math.sin(a), 2.6), zc))
            for a in [math.tau * k / 96 for k in range(97)]]
    _tube("Rope", ring, [0.017] * len(ring), "Rope", body, segments=10)
    front_y = y_mid - depth
    knot = M["knot"].copy()
    knot.y = front_y - 0.01
    _sphere("Knot", knot, (0.03, 0.022, 0.028), "Rope", body)
    for dx in M["rope_ends"][1]:
        pts = [Vector((dx, front_y - 0.012, zc - 0.02 - (zc - M["rope_ends"][0]) * k / 6)) for k in range(7)]
        _tube(f"RopeEnd{dx:+.2f}", pts, [0.013] * 6 + [0.016], "Rope", body, segments=10)


def step_head():
    """Head, hair and beard: the volume comes from the silhouettes; the color, from the view each face looks at."""
    data = json.load(open(VOLUMES))
    body = bpy.data.objects["Body"]
    head_pivot = pivot("HeadMesh", (0, 0, 1.13), body)
    secs = _sections_fit(data["head"], 0.9, 1.6, sigma=3.0)
    # Round crown: above 1.40 m, each measurement follows an ellipse that reaches zero at the
    # measured height of the hair (1.555 m), starting from the real width at 1.40 m.
    top_z = 1.555
    base = min(secs, key=lambda s: abs(s["z"] - 1.40))
    secs = [s for s in secs if s["z"] <= base["z"]]
    for k in range(1, 13):
        z = base["z"] + (top_z - base["z"]) * k / 12
        f = math.sqrt(max(1.0 - ((z - base["z"]) / (top_z - base["z"])) ** 2, 0.0)) if k < 12 else 0.05
        secs.append({"z": z, "fx": [v * f for v in base["fx"]], "bx": [v * f for v in base["bx"]],
                     "front": base["front"] * f + (1 - f) * (base["front"] - base["back"]) / 2 * 0,
                     "back": base["back"] * f})
    head = build_volume("HeadHair", secs, 2.1, 64, smooth=False)
    # Colors with the measured zones: oval of the face (above the beard line), bald spot on
    # the crown and the rest hair/beard.
    head.data.materials.append(material("GrayHair"))
    head.data.materials.append(material("Skin"))
    mw = head.matrix_world
    for poly in head.data.polygons:
        c = mw @ poly.center
        nrm = (mw.to_3x3() @ poly.normal).normalized()
        in_oval = (c.x / 0.15) ** 2 + ((c.z - 1.355) / 0.125) ** 2 < 1.0
        above_beard = c.z > 1.245 + 2.8 * c.x * c.x
        face = nrm.y < -0.3 and in_oval and above_beard
        bald = nrm.y > 0.1 and c.z > 1.49 and (c.x / 0.075) ** 2 + ((c.z - 1.555) / 0.06) ** 2 < 1.0
        poly.material_index = 1 if (face or bald) else 0
    # Locks: soft vertical waves in the hair on the back and the sides.
    for v in head.data.vertices:
        p = v.co
        ang = math.atan2(p.y, p.x)
        if p.y > -0.05 and p.z < 1.48:
            k = min(1.0, (1.48 - p.z) / 0.15)
            r = Vector((p.x, p.y, 0))
            if r.length > 1e-4:
                p += r.normalized() * 0.007 * math.sin(ang * 22) * k
    _majority_faces(head, 4)
    _subsurf(head)
    attach(head, head_pivot)


def _majority_faces(obj, iterations):
    """Each face takes the material of most of its neighbors: clean color edges."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    for _ in range(iterations):
        new = {}
        for f in bm.faces:
            votes = {}
            for e in f.edges:
                for g in e.link_faces:
                    votes[g.material_index] = votes.get(g.material_index, 0) + 1
            new[f] = max(votes, key=votes.get)
        for f, m in new.items():
            f.material_index = m
    bm.to_mesh(obj.data)
    bm.free()


def _on_surface(obj, x, z, out=0.0):
    """Point of the object's front surface at (x, z), casting a ray from the front."""
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    hit, normal, _i, _d = bvh.ray_cast(Vector((x, -2.0, z)), Vector((0, 1, 0)))
    if hit is None:
        return Vector((x, -0.2, z))
    return hit + normal * out


def step_features():
    """Eyes, brows, nose, mustache and ears at the measured positions, stuck to the head."""
    head = bpy.data.objects["HeadHair"]
    pivot_head = bpy.data.objects["HeadMesh"]
    for sx, side in ((1, "L"), (-1, "R")):
        eye_center = _on_surface(head, sx * M["eye"].x, M["eye"].z, 0.0)
        eye = pivot(f"Eye{side}", eye_center, pivot_head)
        _sphere(f"Iris{side}", eye_center, M["eye_size"], "Eye", eye)
        _sphere(f"Glint{side}", eye_center + Vector((-sx * 0.004, -0.008, 0.006)), (0.004, 0.003, 0.005), "Glint",
                eye)
        brow_pts = []
        for k in range(7):
            t = k / 6
            bx = sx * (M["brow"].x - 0.038 + 0.076 * t)
            bz = M["brow"].z + 0.012 * math.sin(t * math.pi) - 0.01 * t
            brow_pts.append(_on_surface(head, bx, bz, 0.008))
        _tube(f"Brow{side}", brow_pts, [0.009, 0.014, 0.016, 0.016, 0.015, 0.012, 0.008], "GrayHair", pivot_head, 14)
        ear = M["ear"].copy()
        ear.x *= sx
        _sphere(f"Ear{side}", ear, M["ear_size"], "Skin", pivot_head)
        # Mustache: two locks from the center outward, drooping at the ends.
        z, half = M["mustache"]
        pts = []
        for k in range(7):
            t = k / 6
            x = sx * (0.012 + half * t)
            p = _on_surface(head, x, z - 0.035 * t * t, 0.006)
            pts.append(p)
        _tube(f"Mustache{side}", pts, [0.022, 0.024, 0.024, 0.022, 0.019, 0.015, 0.01], "GrayHair", pivot_head, 16)
    nose = M["nose"].copy()
    nose.y += M["nose_size"][1]
    _sphere("Nose", nose, M["nose_size"], "Nose", pivot_head)


def step_arms():
    body = bpy.data.objects["Body"]
    for sx, side in ((1, "L"), (-1, "R")):
        shoulder = Vector((sx * 0.215, 0.0, 1.05))
        cuff = M["cuff"] * Vector((sx, 1, 1))
        arm = pivot(f"Arm{side}", shoulder, body)
        axis = (cuff - shoulder).normalized()
        # Sleeve: cone that opens toward the cuff, open at the bottom and with thickness.
        pts = [shoulder + (cuff - shoulder) * (k / 10) for k in range(11)]
        r0, r1 = M["sleeve_r"]
        radii = [r0 + (r1 - r0) * (k / 10) ** 1.5 for k in range(11)]
        sleeve = _tube(f"Sleeve{side}", pts, radii, "Sleeve", arm, segments=24)
        bm = bmesh.new()
        bm.from_mesh(sleeve.data)
        lowest = min(bm.faces, key=lambda f: f.calc_center_median().z)
        bmesh.ops.delete(bm, geom=[lowest], context="FACES_ONLY")
        bm.to_mesh(sleeve.data)
        bm.free()
        _solidify(sleeve, -0.008)
        # Hand: mitten (fingers together) a bit narrower than the cuff, plus the thumb.
        hand = cuff + axis * 0.07
        palm = _sphere(f"Hand{side}", hand, (0.044, 0.03, 0.07), "Skin", arm)
        palm.rotation_euler = (0.0, -sx * math.atan2(axis.x * sx, -axis.z), 0)
        _sphere(f"Fingers{side}", hand + axis * 0.045 + Vector((0, -0.004, 0)), (0.04, 0.026, 0.035), "Skin", arm)
        _sphere(f"Thumb{side}", hand + Vector((-sx * 0.026, -0.022, 0.012)), (0.015, 0.016, 0.03), "Skin", arm)


def step_feet():
    root = bpy.data.objects["Noah"]
    heel, toe = M["foot_y"]
    for sx, side in ((1, "L"), (-1, "R")):
        x = sx * M["foot_x"]
        foot = pivot(f"Foot{side}", (x, 0.04, 0.06), root)
        # Leg and foot in a single piece: from the ankle it goes down and turns forward to the toes.
        _tube(f"LegFoot{side}", [Vector((x, 0.03, 0.2)), Vector((x, 0.03, 0.07)), Vector((x, 0.0, 0.045)),
                                  Vector((x, -0.07, 0.04)), Vector((x, toe + 0.025, 0.035))],
              [0.048, 0.05, 0.052, 0.05, 0.036], "Skin", foot, 20)
        length = heel - toe
        _sphere(f"Sole{side}", Vector((x, (heel + toe) / 2, 0.012)), (M["foot_half_width"], length / 2, 0.014),
                "Sandal", foot)
        for y_strap, h in ((toe + 0.075, 0.062), (0.0, 0.07)):
            _tube(f"Strap{side}{y_strap:+.2f}", [Vector((x - 0.058, y_strap, 0.02)), Vector((x - 0.045, y_strap, h)),
                                                 Vector((x + 0.045, y_strap, h)), Vector((x + 0.058, y_strap, 0.02))],
                  [0.011] * 4, "Sandal", foot, 12)
    for o in bpy.data.objects:
        if o.type == "MESH" and not any(m.type == "SUBSURF" for m in o.modifiers):
            _subsurf(o, 1)


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
    rim = bpy.data.objects.new("RimLight", bpy.data.lights.new("RimLight", "SUN"))
    rim.data.energy = 1.2
    rim.rotation_euler = (math.radians(60), 0, math.radians(160))
    for o in (key, rim):
        scene.collection.objects.link(o)
    return [key, rim]


def step_render(folder):
    """The 4 views at the same scale as the turnaround sheet, to put them under the reference."""
    scene = bpy.context.scene
    for engine in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x = 320
    scene.render.resolution_y = 572
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    added = _lights(scene)
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
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True, export_animations=False)
    print(f"NOAH OK -> {out_path}")


STEPS = [step_clear, step_clothes, step_head, step_features, step_arms, step_feet]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = argv[0] if argv else "noah.glb"
    renders = argv[1] if len(argv) > 1 else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for step in STEPS:
        step()
    if renders:
        step_render(renders)
    step_export(out_path)


if not globals().get("LIVE"):
    main()
