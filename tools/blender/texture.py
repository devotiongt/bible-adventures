"""Noah's final texture (light version NoahLow1500, see polish_rodin.py).

    step_uv          new UV unwrap: few large, well-packed pieces
    step_bake        bakes from Rodin's original mesh: color, normals and ambient occlusion
    step_paint       repaints by parts with the colors of references/palette.png: flat color,
                     soft shading from the occlusion, linen weave on the tunic and sleeves, fabric on the
                     vest; the skin keeps its paint (nose, blush)
    step_export      .glb for the game

Live:
    python3 tools/blender/live.py texture step_uv step_bake step_paint "step_export('...')"
"""

import math
import os

import bpy
import numpy as np
from mathutils import Vector

ROOT = globals().get("PROJECT_ROOT", os.getcwd())
OUT_DIR = os.path.join(ROOT, "assets/characters/rodin")
LOW = "NoahLow2500"
SIZE = 1024
# Names of the UV layer and the face attributes as they are stored in noah_texture.blend.
UV_GAME = "UVGame"
PART_ATTR = "part"
SHOULDER_SEAM_ATTR = "shoulder_seam"

# Parts and their color (sRGB) according to the reference palette.
PARTS = {
    "skin": "FCD4B7", "nose": "EDA88A", "gray_hair": "EFEFEF", "tunic": "DDD3C0",
    "mantle": "A55B2E", "sleeve": "C8AE86", "rope": "5E3918", "sandal": "3F2A1D",
}
SKIN_FAMILY = ("skin", "nose")        # They keep their paint (blush, nose), they are only cleaned up.


def _hex(h):
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255


def _low():
    return bpy.data.objects[LOW]


def _select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_viewport = False
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _uv_coverage(obj, layer):
    """Fraction of the UV square covered by triangles."""
    me = obj.data
    me.calc_loop_triangles()
    uv = me.uv_layers[layer].data
    area = 0.0
    for tri in me.loop_triangles:
        a, b, c = (uv[i].uv for i in tri.loops)
        area += abs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) / 2
    return area


def _overlapping_faces(obj, size=1024):
    """Faces whose UV triangle shares pixels with another triangle."""
    me = obj.data
    me.calc_loop_triangles()
    uv = me.uv_layers[UV_GAME].data
    count = np.zeros((size, size), np.int32)
    cover = []
    for tri in me.loop_triangles:
        uvs = np.array([uv[i].uv[:] for i in tri.loops], np.float64) * size
        x0, y0 = np.floor(uvs.min(0)).astype(int)
        x1, y1 = np.ceil(uvs.max(0)).astype(int) + 1
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size), min(y1, size)
        if x1 <= x0 or y1 <= y0:
            cover.append(None)
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1) + .5, np.arange(y0, y1) + .5)
        (ax, ay), (bx, by), (cx, cy) = uvs
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            cover.append(None)
            continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
        inside = (l1 >= 0) & (l2 >= 0) & (1 - l1 - l2 >= 0)
        count[y0:y1, x0:x1] += inside
        cover.append((x0, y0, x1, y1, inside, tri.polygon_index))
    bad = set()
    for c in cover:
        if c is None:
            continue
        x0, y0, x1, y1, inside, poly = c
        if (count[y0:y1, x0:x1][inside] > 1).any():
            bad.add(poly)
    return bad


def _move_overlaps(obj, strip=0.06, attempt=0):
    """Triangles folded over each other: in those pixels one part of the body would be painted with the
    color of another. The whole unwrap is shrunk to leave a free strip at the top and on the right,
    and each overlapping face is moved to that strip (each corner has its own UV coordinate, so
    it separates from its piece without moving the neighbors)."""
    me = obj.data
    uv = me.uv_layers[UV_GAME].data
    bad = sorted(_overlapping_faces(obj))
    print("overlapping faces", len(bad))
    if not bad:
        return
    k = 1 - strip
    for d in uv:
        d.uv = d.uv * k
    # Cells in the strip: right column and top row.
    half = strip / 2
    cell = half * 0.85
    slots = [(k + half * c + half * 0.07, y * half) for c in (0, 1) for y in range(int(k / half))] + \
            [(x * half, k + half * r + half * 0.07) for r in (0, 1) for x in range(int(k / half))]
    assert len(slots) >= len(bad), (len(slots), len(bad))
    for n, f in enumerate(bad):
        loops = list(me.polygons[f].loop_indices)
        us = [uv[i].uv.copy() for i in loops]
        mn = Vector((min(u.x for u in us), min(u.y for u in us)))
        size = max(max(u.x for u in us) - mn.x, max(u.y for u in us) - mn.y, 1e-6)
        scale = min(1.0, cell / size)
        ox, oy = slots[n]
        for i, u in zip(loops, us):
            uv[i].uv = Vector((ox, oy)) + (u - mn) * scale
    left = len(_overlapping_faces(obj))
    print("after moving them", left, "overlapping")
    if left and attempt < 3:
        _move_overlaps(obj, strip, attempt + 1)


def step_uv():
    """Automatic unwrap + packing. I tried angles 45-80 and AABB/convex/concave methods:
    this combination is the one that uses the most space (~57 %); above that, seams would have to be marked by hand."""
    low = _low()
    me = low.data
    layer = me.uv_layers.get(UV_GAME) or me.uv_layers.new(name=UV_GAME)
    me.uv_layers.active = layer
    _select_only(low)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(70), island_margin=0.004, area_weight=0.6,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    _move_overlaps(low)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.object.mode_set(mode="OBJECT")
    layer.active_render = True
    print("coverage", f"{_uv_coverage(low, UV_GAME):.0%}")


def _new_image(name, data=False):
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, SIZE, SIZE, is_data=data)
    if data:
        img.colorspace_settings.name = "Non-Color"
    return img


def step_spikes():
    """Removes the spikes the polygon reduction left on the brows: each vertex in that zone
    that sticks out a lot compared to its neighbors is moved to their average."""
    import bmesh
    low = _low()
    mw = low.matrix_world
    inv = mw.inverted()
    bm = bmesh.new()
    bm.from_mesh(low.data)
    fixed = 0
    for _ in range(3):
        for v in bm.verts:
            w = mw @ v.co
            if not (1.31 < w.z < 1.42 and abs(w.x) < 0.14 and w.y < -0.08):
                continue
            nb = [e.other_vert(v).co for e in v.link_edges]
            if not nb:
                continue
            c = sum(nb, Vector()) / len(nb)
            edge = sum((n - v.co).length for n in nb) / len(nb)
            if (v.co - c).length > 0.6 * edge:
                v.co = v.co.lerp(c, 0.8)
                fixed += 1
    bm.to_mesh(low.data)
    bm.free()
    low.data.update()
    print("vertices fixed", fixed)


BROW_ZONE = (0.025, 0.14, 1.335, 1.41)     # |x| min/max, z min/max (forehead, front).


def _in_brow_zone(x, z, y):
    return BROW_ZONE[0] < abs(x) < BROW_ZONE[1] and BROW_ZONE[2] < z < BROW_ZONE[3] and y < -0.1


def step_brows():
    """Brows as their own pieces (like the eyes): with 1,500 triangles the mesh can't form such a
    small relief and it left sharp wedges. That zone of the forehead is smoothed and two
    "sausages" are added with the path and thickness measured on the original mesh (references/noah_brows.json)."""
    import json
    from mathutils.bvhtree import BVHTree
    low = _low()
    # 2. Surface of the forehead without brows: degree-2 polynomial fitted to the original mesh
    #    outside the brow strip.
    high = bpy.data.objects["model"]
    hidden = high.hide_viewport
    high.hide_viewport = False
    bpy.context.view_layer.update()
    bvh = BVHTree.FromObject(high, bpy.context.evaluated_depsgraph_get())
    hm = high.matrix_world
    hinv = hm.inverted()
    d = (hinv.to_3x3() @ Vector((0, 1, 0))).normalized()
    rows = []
    for x in np.arange(-0.15, 0.151, 0.004):
        for z in np.arange(1.30, 1.451, 0.004):
            if 1.34 < z < 1.42 or abs(x) > 0.13:
                continue
            hit, _n, _i, _d = bvh.ray_cast(hinv @ Vector((x, -2, z)), d)
            if hit is not None:
                rows.append((x, z, (hm @ hit).y))
    high.hide_viewport = hidden
    r = np.array(rows)
    A = np.stack([np.ones(len(r)), r[:, 0], r[:, 1], r[:, 0] ** 2, r[:, 1] ** 2, r[:, 0] * r[:, 1]], -1)
    coef = np.linalg.lstsq(A, r[:, 2], rcond=None)[0]
    surface = lambda x, z: float(coef @ np.array([1, x, z, x * x, z * z, x * z]))
    # 3. The vertices of the zone that stick out of that surface are moved onto it (only in Y).
    mw = low.matrix_world
    inv = mw.inverted()
    moved = 0
    for v in low.data.vertices:
        w = mw @ v.co
        if _in_brow_zone(w.x, w.z, w.y):
            target = surface(w.x, w.z)
            if w.y < target:
                w.y = target
                v.co = inv @ w
                moved += 1
    low.data.update()
    print("vertices projected onto the forehead", moved)

    data = json.load(open(os.path.join(ROOT, "references/noah_brows.json")))
    root = bpy.data.objects["RodinTurn"]
    mat = bpy.data.materials.get("NoahBrow") or bpy.data.materials.new("NoahBrow")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*[c ** 2.2 for c in _hex(PARTS["gray_hair"])], 1)
    b.inputs["Roughness"].default_value = 0.75
    for o in [o for o in bpy.data.objects if o.name.startswith("NoahBrow")]:
        bpy.data.objects.remove(o)
    import bmesh as bmm
    for key, side in (("1", "L"), ("-1", "R")):
        pts = [q for q in data[key] if q[4] > 0.006]
        pts.sort(key=lambda q: abs(q[0]))
        # Sampling every ~6 mm and smoothing of the curve.
        pts = pts[::5]
        n = len(pts)
        sm = []
        for i in range(n):
            lo, hi = max(0, i - 1), min(n, i + 2)
            sm.append([sum(q[k] for q in pts[lo:hi]) / (hi - lo) for k in range(5)])
        bm2 = bmm.new()
        rings = []
        seg = 8
        for i, (x, z, yfront, semi, sticks_out) in enumerate(sm):
            t = i / (n - 1)
            taper = math.sin(math.pi * (0.12 + 0.76 * t)) ** 0.6     # Thinner at the tips.
            rz = min(max(semi, 0.007), 0.012) * taper
            ry = 0.0085 * taper
            center = Vector((x, yfront + ry * 0.8, z))
            a = Vector(sm[max(i - 1, 0)][:2]); c = Vector(sm[min(i + 1, n - 1)][:2])
            tang = Vector((c.x - a.x, 0, c.y - a.y)).normalized()
            up = Vector((-tang.z, 0, tang.x))
            if up.z < 0:
                up = -up
            fwd = Vector((0, -1, 0))
            rings.append([bm2.verts.new(center + up * math.cos(k * math.tau / seg) * rz
                                        + fwd * math.sin(k * math.tau / seg) * ry) for k in range(seg)])
        for i in range(len(rings) - 1):
            for k in range(seg):
                k2 = (k + 1) % seg
                bm2.faces.new((rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]))
        for ring in (rings[0], rings[-1]):
            cap = bmm.ops.contextual_create(bm2, geom=ring)
        bmm.ops.recalc_face_normals(bm2, faces=bm2.faces)
        me = bpy.data.meshes.new(f"NoahBrow{side}")
        bm2.to_mesh(me)
        bm2.free()
        o = bpy.data.objects.new(f"NoahBrow{side}", me)
        bpy.context.scene.collection.objects.link(o)
        o.data.materials.append(mat)
        for poly in me.polygons:
            poly.use_smooth = True
        o.parent = root
        o.matrix_parent_inverse = root.matrix_world.inverted()
        print("brow", side, "triangles", sum(len(p.vertices) - 2 for p in me.polygons))


def step_unfold_folds(max_angle=150):
    """Flipped triangles the polygon reduction left (two neighboring faces almost opposite,
    the mesh folds over itself and a line shows). Each vertex of those edges is moved
    to the average of its neighbors until none are left."""
    import bmesh
    low = _low()
    bm = bmesh.new()
    bm.from_mesh(low.data)
    for it in range(20):
        bm.normal_update()
        bad = [e for e in bm.edges if len(e.link_faces) == 2
               and math.degrees(e.link_faces[0].normal.angle(e.link_faces[1].normal, 0)) > max_angle]
        if not bad:
            break
        verts = {v for e in bad for v in e.verts}
        for v in verts:
            nb = [e.other_vert(v).co for e in v.link_edges]
            v.co = v.co.lerp(sum(nb, Vector()) / len(nb), 0.5)
        print("pass", it, "folded edges", len(bad))
    # What's left (and the strong bends on the face): rotate the shared edge, if that leaves the
    # two faces better aligned.
    bm.normal_update()
    mw = low.matrix_world
    rotated = 0
    for e in list(bm.edges):
        if len(e.link_faces) != 2 or not e.is_valid:
            continue
        ang = math.degrees(e.link_faces[0].normal.angle(e.link_faces[1].normal, 0))
        c = mw @ ((e.verts[0].co + e.verts[1].co) / 2)
        face_zone = c.z > 1.15 and c.y < -0.05
        if ang > max_angle or (face_zone and ang > 100):
            res = bmesh.ops.rotate_edges(bm, edges=[e], use_ccw=False)
            new = res["edges"]
            if new:
                bm.normal_update()
                ne = new[0]
                ang2 = math.degrees(ne.link_faces[0].normal.angle(ne.link_faces[1].normal, 0)) \
                    if len(ne.link_faces) == 2 else 180
                if ang2 >= ang:
                    bmesh.ops.rotate_edges(bm, edges=[ne], use_ccw=True)
                else:
                    rotated += 1
    print("edges rotated", rotated)
    bm.to_mesh(low.data)
    bm.free()
    low.data.update()


def step_restore_mesh():
    """Goes back to the mesh saved in noah_texture.blend (same topology): positions and UV."""
    low = _low()
    with bpy.data.libraries.load(os.path.join(OUT_DIR, "noah_texture.blend")) as (src, dst):
        dst.objects = [LOW]
    saved = dst.objects[0]
    assert len(saved.data.vertices) == len(low.data.vertices), "different topology"
    for v, sv in zip(low.data.vertices, saved.data.vertices):
        v.co = sv.co
    for l, sl in zip(low.data.uv_layers[UV_GAME].data, saved.data.uv_layers[UV_GAME].data):
        l.uv = sl.uv
    low.data.update()
    lib = saved.library
    bpy.data.meshes.remove(saved.data)
    for o in [o for o in bpy.data.objects if lib is not None and o.library is lib]:
        bpy.data.objects.remove(o)
    if lib is not None:
        bpy.data.libraries.remove(lib)
    print("mesh restored")


def step_shoulders(radius=0.015, passes=0):
    """Removes the flap and the fold at the sleeve/vest seam: smooths the mesh in a strip
    around the seam and flags those triangles so their normal map is left flat."""
    import bmesh
    low = _low()
    me = low.data
    names = list(PARTS)
    part = np.zeros(len(me.polygons), np.int32)
    me.attributes[PART_ATTR].data.foreach_get("value", part)
    gi, mi = names.index("sleeve"), names.index("mantle")
    mw = low.matrix_world
    inv = mw.inverted()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    seam = set()
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        a, b = (part[f.index] for f in e.link_faces)
        c = mw @ ((e.verts[0].co + e.verts[1].co) / 2)
        if {a, b} == {gi, mi} and 0.9 < c.z < 1.12 and 0.17 < abs(c.x) < 0.32:
            seam.update(e.verts)
    seam_pts = [mw @ v.co for v in seam]
    zone = [v for v in bm.verts if min(((mw @ v.co) - q).length for q in seam_pts) < radius] if seam_pts else []
    print("vertices on the seam", len(seam), "in the strip", len(zone))
    # Laplacian-type smoothing without shrinking (back and forth, Taubin's method).
    for it in range(passes):
        for lam in (0.5, -0.53):
            new = {}
            for v in zone:
                nb = [e.other_vert(v).co for e in v.link_edges]
                c = sum(nb, Vector()) / len(nb)
                new[v] = v.co + (c - v.co) * lam
            for v, co in new.items():
                v.co = co
    flagged = set(f.index for v in zone for f in v.link_faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    attr = me.attributes.get(SHOULDER_SEAM_ATTR) or me.attributes.new(SHOULDER_SEAM_ATTR, "INT", "FACE")
    vals = np.zeros(len(me.polygons), np.int32)
    vals[list(flagged)] = 1
    attr.data.foreach_set("value", vals)
    print("triangles flagged", len(flagged))


def step_tuck_flap(depth=0.012, reach=0.03):
    """Hides the sleeve flap under the vest: the vertices that belong only to the sleeve, near
    the shoulder seam, are moved toward the arm's axis. It doesn't touch vertices of other parts."""
    import bmesh
    low = _low()
    me = low.data
    names = list(PARTS)
    part = np.zeros(len(me.polygons), np.int32)
    me.attributes[PART_ATTR].data.foreach_get("value", part)
    gi, mi = names.index("sleeve"), names.index("mantle")
    mw = low.matrix_world
    inv = mw.inverted()
    bm = bmesh.new()
    bm.from_mesh(me)
    seam = []
    for e in bm.edges:
        if len(e.link_faces) == 2 and {part[f.index] for f in e.link_faces} == {gi, mi}:
            c = mw @ ((e.verts[0].co + e.verts[1].co) / 2)
            if 0.9 < c.z < 1.12 and 0.17 < abs(c.x) < 0.32:
                seam.append(c)
    moved = 0
    for v in bm.verts:
        if not v.link_faces or any(part[f.index] != gi for f in v.link_faces):
            continue
        w = mw @ v.co
        if not (0.95 < w.z < 1.13 and 0.17 < abs(w.x) < 0.34) or not seam:
            continue
        d = min((w - q).length for q in seam)
        if d > reach:
            continue
        # Arm axis: from the shoulder (x≈±0.2, z≈1.05) toward the elbow; it's pushed in horizontally
        # toward that axis and a bit downward.
        axis = Vector((math.copysign(0.24, w.x), 0.0, w.z))
        inward = (axis - w)
        inward.z = 0
        if inward.length < 1e-6:
            continue
        k = depth * (1 - d / reach)
        w = w + inward.normalized() * k + Vector((0, 0, -k * 0.6))
        v.co = inv @ w
        moved += 1
    bm.to_mesh(me)
    bm.free()
    me.update()
    print("sleeve vertices tucked under the vest", moved, "seam", len(seam))


def step_bake():
    scene = bpy.context.scene
    high = bpy.data.objects["model"]
    low = _low()
    high.hide_viewport = False
    high.hide_render = False
    low.hide_render = False
    color = _new_image("NoahBaseColor")
    normal = _new_image("NoahNormalGame", data=True)
    ao = _new_image("NoahAO", data=True)

    mat = low.data.materials[0]
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.type in ("TEX_IMAGE", "NORMAL_MAP", "UVMAP"):
            nt.nodes.remove(n)
    bsdf = nt.nodes["Principled BSDF"]
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = UV_GAME
    nodes = {}
    for key, img in (("color", color), ("normal", normal), ("ao", ao)):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = img
        nt.links.new(uvn.outputs["UV"], t.inputs["Vector"])
        nodes[key] = t
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.uv_map = UV_GAME
    nt.links.new(nodes["color"].outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(nodes["normal"].outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])

    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    bake = scene.render.bake
    bake.margin = 16
    bake.cage_extrusion = 0.012
    bake.max_ray_distance = 0.03
    bake.use_pass_direct = False
    bake.use_pass_indirect = False
    bake.use_pass_color = True

    def run(kind, node, selected):
        bake.use_selected_to_active = selected
        bpy.ops.object.select_all(action="DESELECT")
        if selected:
            high.select_set(True)
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        nt.nodes.active = node
        bpy.ops.object.bake(type=kind)
        print("baked", kind)

    run("NORMAL", nodes["normal"], True)
    run("DIFFUSE", nodes["color"], True)
    # Occlusion of the light mesh itself (soft shadows in folds, neck, armpits…).
    high.hide_render = True
    scene.cycles.samples = 64
    scene.world.light_settings.distance = 0.035
    run("AO", nodes["ao"], False)
    for img, name in ((color, "noah_base_color.png"), (normal, "noah_normal_game.png"), (ao, "noah_ao.png")):
        img.filepath_raw = os.path.join(OUT_DIR, name)
        img.file_format = "PNG"
        img.save()
    high.hide_viewport = True
    scene.render.engine = "BLENDER_EEVEE"


def _pixels(img):
    a = np.empty(SIZE * SIZE * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(SIZE, SIZE, 4)


def _position_map(obj):
    """3D (world) position of each texel of the game UV (UV_GAME); NaN where there's no mesh."""
    me = obj.data
    me.calc_loop_triangles()
    uv = me.uv_layers[UV_GAME].data
    mw = obj.matrix_world
    pos = np.full((SIZE, SIZE, 3), np.nan, np.float32)
    face = np.full((SIZE, SIZE), -1, np.int32)
    tris = []
    for tri in me.loop_triangles:
        uvs = np.array([uv[i].uv[:] for i in tri.loops], np.float64) * SIZE
        ps = np.array([(mw @ me.vertices[v].co)[:] for v in tri.vertices], np.float32)
        tris.append((uvs, ps, tri.polygon_index))
    # Two passes: first the texels whose center falls inside each triangle; then, those that
    # only touch it (up to 0.8 px outside the edge), without overwriting the ones already assigned. That way no
    # narrow triangle is left without texels (otherwise the edge fill would give it the color
    # of the neighboring piece in the image).
    for tolerance in (0.0, 0.8):
        for uvs, ps, poly_index in tris:
            x0, y0 = np.floor(uvs.min(0) - 1).astype(int)
            x1, y1 = np.ceil(uvs.max(0) + 2).astype(int)
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, SIZE), min(y1, SIZE)
            if x1 <= x0 or y1 <= y0:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            (ax, ay), (bx, by), (cx, cy) = uvs
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-12:
                continue
            l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / den
            l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / den
            l3 = 1 - l1 - l2
            # Distance (in pixels) to each side = barycentric coordinate × height over that side.
            area2 = abs(den)
            h = [area2 / max(np.hypot(*(uvs[(k + 1) % 3] - uvs[(k + 2) % 3])), 1e-9) for k in range(3)]
            inside = (l1 * h[0] >= -tolerance) & (l2 * h[1] >= -tolerance) & (l3 * h[2] >= -tolerance)
            region_face = face[y0:y1, x0:x1]
            if tolerance > 0:
                inside &= region_face < 0
            if not inside.any():
                continue
            c1, c2 = np.clip(l1, 0, 1), np.clip(l2, 0, 1)
            c3 = np.clip(1 - c1 - c2, 0, 1)
            p = c1[..., None] * ps[0] + c2[..., None] * ps[1] + c3[..., None] * ps[2]
            pos[y0:y1, x0:x1][inside] = p[inside]
            region_face[inside] = poly_index
    return pos, face


def _box(a, r):
    """Mean over a (2r+1)² window (with a cumulative sum)."""
    pad = np.pad(a, ((r + 1, r), (r + 1, r)) + ((0, 0),) * (a.ndim - 2), mode="edge")
    c = pad.cumsum(0).cumsum(1)
    k = 2 * r + 1
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def _noise(p, scale, seed):
    """Smooth 3D noise (sum of sines with fixed phases, no dependencies)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(p.shape[:2], np.float32)
    for _ in range(6):
        d = rng.normal(size=3)
        d /= np.linalg.norm(d)
        out += np.sin((p @ d) * scale * rng.uniform(0.7, 1.4) + rng.uniform(0, 6.28))
    return out / 6


def step_paint(debug_face=None):
    low = _low()
    base = _pixels(bpy.data.images["NoahBaseColor"])[..., :3]
    ao = _pixels(bpy.data.images["NoahAO"])[..., 0]
    pos, face = _position_map(low)
    valid = ~np.isnan(pos[..., 0])
    p = np.nan_to_num(pos)
    names = list(PARTS)
    palette = np.stack([_hex(PARTS[n]) for n in names])

    # 1. Part of each texel: the nearest palette color, and then the majority in a 7×7
    #    window (removes the stray spots of Rodin's paint).
    dist = ((base[..., None, :] - palette[None, None]) ** 2).sum(-1)
    # Where each part can be (position on the body, in meters). Color alone isn't enough: the
    # shaded white of the hair looks like the beige of the tunic.
    z, ax, back = p[..., 2], np.abs(p[..., 0]), p[..., 1] > 0.05     # Noah faces -Y.
    allowed = {
        # Skin: only head (not on the nape, the hair covers it), hands and feet.
        "skin": (((z > 1.1) & ~(back & (z < 1.3) & (ax < 0.2))) | ((ax > 0.27) & (z < 0.8)) | (z < 0.2)),
        "nose": (z > 1.2) & (z < 1.36) & (ax < 0.06),
        "gray_hair": (z > 0.7) & ~((ax > BROW_ZONE[0]) & (ax < BROW_ZONE[1]) & (z > BROW_ZONE[2])
                                     & (z < BROW_ZONE[3]) & (p[..., 1] < -0.1)),
        # Below the vest it shows all around; above, only in the front opening.
        "tunic": ((z < 0.36) & (z > 0.14)) | ((z > 0.3) & (z < 1.16) & (ax < 0.13) & (p[..., 1] < -0.08)),
        "mantle": (z < 1.18) & (z > 0.25) & ~((ax > 0.235) & (z > 0.55)),  # Not on the arms.
        "sleeve": (z < 1.15) & (z > 0.5) & (ax > 0.14),
        "rope": (z > 0.5) & (z < 0.8),
        "sandal": z < 0.06,
    }
    for k, n in enumerate(names):
        dist[..., k] += np.where(allowed[n], 0.0, 10.0)
    label = dist.argmin(-1)

    # First the part of each triangle is decided (majority of its texels) and the stray
    # triangles are fixed (no neighbor shares its part). Then each texel can only choose between
    # the part of its triangle and that of the neighboring triangles: that way a sleeve is a whole sleeve and parts
    # only mix at the real edges between pieces.
    me = low.data
    nf = len(me.polygons)
    hist = np.zeros((nf, len(names)), np.float32)
    m = valid & (face >= 0)
    np.add.at(hist, (face[m], label[m]), 1.0)
    face_label = hist.argmax(1)
    neighbors = [set() for _ in range(nf)]
    edge_faces = {}
    for poly in me.polygons:
        for key in poly.edge_keys:
            edge_faces.setdefault(key, []).append(poly.index)
    for fs in edge_faces.values():
        for a in fs:
            for b in fs:
                if a != b:
                    neighbors[a].add(b)
    for _ in range(3):
        new_label = face_label.copy()
        for f in range(nf):
            nb = [face_label[n] for n in neighbors[f]]
            if nb and face_label[f] not in nb:
                new_label[f] = max(set(nb), key=nb.count)
        face_label = new_label
    allowed_face = np.zeros((nf, len(names)), bool)
    for f in range(nf):
        allowed_face[f, face_label[f]] = True
        for n in neighbors[f]:
            allowed_face[f, face_label[n]] = True
    # Allowed = what the neighboring triangles allow AND the position rules on the body.
    ok = allowed_face[np.clip(face, 0, None)] & np.stack([allowed[n] for n in names], -1)
    dist = np.where(ok, dist, dist + 10.0)
    label = dist.argmin(-1)
    if debug_face is not None:
        mf = face == debug_face
        print("face", debug_face, "texels", int(mf.sum()), "face part", names[face_label[debug_face]],
              "allowed", [names[k] for k in np.nonzero(allowed_face[debug_face])[0]],
              "neighbors", [names[face_label[n]] for n in neighbors[debug_face]],
              "hist", dict(zip(names, hist[debug_face].astype(int).tolist())),
              "texel labels", dict(zip(names, np.bincount(label[mf], minlength=len(names)).tolist())))
    for _ in range(3):
        # Local majority, but only among the parts allowed for each texel's triangle:
        # in the image, next to the edge of a piece there can be another piece that is far away on the body.
        votes = np.stack([_box(((label == k) & valid).astype(np.float32), 6) for k in range(len(names))], -1)
        votes = np.where(ok, votes, -1.0)
        label = votes.argmax(-1)
    if debug_face is not None:
        print("after majority", dict(zip(names, np.bincount(label[face == debug_face], minlength=len(names)).tolist())))
    # Edge of the vest's front opening: at each height (every 1 cm) the width that best
    # separates tunic (inside) from vest (outside) is searched for and smoothed into a clean line.
    ti, mi = names.index("tunic"), names.index("mantle")
    front = valid & (p[..., 1] < -0.08) & (z > 0.36) & (z < 1.12) & (ax < 0.2)
    zb = np.arange(0.36, 1.12, 0.01)
    cut = np.full(len(zb), np.nan)
    for i, z0 in enumerate(zb):
        band = front & (np.abs(z - z0) < 0.01) & np.isin(label, [ti, mi])
        if band.sum() < 20:
            continue
        a, lab = ax[band], label[band]
        best, best_err = np.nan, 1e9
        for t in np.arange(0.03, 0.15, 0.0025):
            err = np.sum((a < t) & (lab == mi)) + np.sum((a >= t) & (lab == ti))
            if err < best_err:
                best, best_err = t, err
        cut[i] = best
    ok_cut = ~np.isnan(cut)
    if ok_cut.sum() > 5:
        cut = np.interp(zb, zb[ok_cut], cut[ok_cut])
        k = np.exp(-np.arange(-6, 7) ** 2 / (2 * 3.0 ** 2))
        cut = np.convolve(np.pad(cut, 6, mode="edge"), k / k.sum(), mode="valid")
        line = np.interp(z, zb, cut)
        region = front & np.isin(label, [ti, mi])
        label = np.where(region & (ax < line), ti, np.where(region & (ax >= line), mi, label))
        print("vest opening (half width cm)", [round(float(c) * 100, 1) for c in cut[::10]])
    # Edges that follow the mesh: if a triangle clearly belongs to a single part (70 % or more of its
    # pixels), it's painted entirely with that part. That way the sleeve/vest or rope/tunic seam follows the
    # edges of the pieces instead of drawing a zigzag of pixels.
    m2 = valid & (face >= 0)
    hist2 = np.zeros((nf, len(names)), np.float32)
    np.add.at(hist2, (face[m2], label[m2]), 1.0)
    dom = hist2.argmax(1)
    frac = hist2.max(1) / np.maximum(hist2.sum(1), 1)
    solid = frac >= 0.7
    fl = np.clip(face, 0, None)
    take = m2 & solid[fl]
    label = np.where(take, dom[fl], label)
    print("single-part triangles", int(solid.sum()), "of", nf)
    attr = me.attributes.get(PART_ATTR) or me.attributes.new(PART_ATTR, "INT", "FACE")
    attr.data.foreach_set("value", dom.astype(np.int32))
    # Sandals (following references/noah_turnaround.png): dark brown sole and a wide strap over the front
    # of the foot, with the toes peeking out. They're placed according to the measurement of each foot.
    si, pi_ = names.index("sandal"), names.index("skin")
    feet = valid & (z < 0.13) & (ax > 0.03) & (ax < 0.22)
    for sx in (1, -1):
        f = feet & (np.sign(p[..., 0]) == sx)
        if f.sum() < 50:
            continue
        ys = p[..., 1][f]
        toe, heel = np.percentile(ys, 1), np.percentile(ys, 99)     # Noah faces -Y.
        t = (p[..., 1] - toe) / max(heel - toe, 1e-6)                # 0 tip, 1 heel.
        sole = f & (z < 0.022)
        top = f & (z >= 0.022)
        straps = top & (t > 0.17) & (t < 0.42) & (z < 0.075)         # A wide strap over the foot.
        label = np.where(sole | straps, si, np.where(top, pi_, label))
        print("foot", sx, "length cm", round(float(heel - toe) * 100, 1))
    counts = {n: int(((label == k) & valid).sum()) for k, n in enumerate(names)}
    print("texels per part", counts)

    # 2. Color: flat per part; the skin keeps its smoothed paint.
    color = palette[label]
    skin = np.isin(label, [names.index(n) for n in SKIN_FAMILY]) & valid
    soft = _box(base * valid[..., None], 2) / np.maximum(_box(valid.astype(np.float32), 2), 1e-6)[..., None]
    # Only the face keeps Rodin's paint (blush, nose); hands, legs and feet, flat color.
    head = skin & (z > 1.1)
    color[head] = soft[head]

    brow = (ax > BROW_ZONE[0] - 0.01) & (ax < BROW_ZONE[1] + 0.01) & (z > BROW_ZONE[2] - 0.01) \
        & (z < BROW_ZONE[3] + 0.01) & (p[..., 1] < -0.1) & valid
    ring = (ax > 0.02) & (ax < 0.15) & (((z > 1.30) & (z < 1.325)) | ((z > 1.42) & (z < 1.44))) \
        & (p[..., 1] < -0.1) & skin
    if ring.any():
        color[brow] = np.median(color[ring], axis=0)
    # 3. Cloth: linen weave (tunic and sleeves) and fine fabric (vest), in 3D coordinates so
    #    it doesn't depend on how the UV is unwrapped.
    around = np.arctan2(p[..., 0], -p[..., 1]) * 0.2
    weave = 0.5 * (np.sin(around / 0.006 * 2 * np.pi) + np.sin(p[..., 2] / 0.006 * 2 * np.pi))
    linen = 1 + 0.035 * weave + 0.03 * _noise(p, 900, 1)
    cloth = 1 + 0.025 * _noise(p, 400, 2) + 0.015 * _noise(p, 1500, 3)
    for name, pattern in (("tunic", linen), ("sleeve", linen), ("mantle", cloth)):
        m = (label == names.index(name)) & valid
        color[m] *= pattern[m][:, None]
    # Hair and beard: very soft locks (the relief already comes from the normals).
    hair = (label == names.index("gray_hair")) & valid
    color[hair] *= (1 + 0.025 * _noise(p * np.array([4, 4, 0.6]), 300, 4))[hair][:, None]

    # 4. Soft shading from the occlusion.
    shade = 1 - 0.55 * (1 - np.clip(ao, 0, 1))
    # On the face the occlusion marks folds of the light mesh that don't exist in the design.
    face_skin = skin & (z > 1.15) & (p[..., 1] < -0.05)
    shade = np.where(face_skin, 1 - 0.12 * (1 - np.clip(ao, 0, 1)), shade)
    color *= shade[..., None]

    # 5. Edges: the color is extended outside each piece so no seams show.
    filled = valid.copy()
    for _ in range(24):
        acc = _box(color * filled[..., None], 1)
        cnt = _box(filled.astype(np.float32), 1)
        grow = (~filled) & (cnt > 0)
        color[grow] = acc[grow] / cnt[grow][:, None]
        filled |= grow

    nimg = bpy.data.images["NoahNormalGame"]
    nrm = _pixels(nimg)
    head_skin = skin & (z > 1.15) & ~((label == names.index("nose")))
    flat_zone = head_skin | (valid & (z < 0.2) & (ax < 0.22) & np.isin(label, [names.index("skin"), names.index("sandal")]))
    seam = me.attributes.get(SHOULDER_SEAM_ATTR)
    if seam is not None:
        flags = np.zeros(nf, np.int8)
        seam.data.foreach_get("value", flags)
        flat_zone |= valid & (face >= 0) & flags.astype(bool)[np.clip(face, 0, None)]
    soft_mask = np.clip(_box(flat_zone.astype(np.float32), 6) * 1.6, 0, 1)   # Blurred edge.
    flat = np.array([0.5, 0.5, 1.0], np.float32)
    nrm[..., :3] = nrm[..., :3] * (1 - soft_mask[..., None]) + flat * soft_mask[..., None]
    nout = bpy.data.images.get("NoahNormalFinal") or bpy.data.images.new("NoahNormalFinal", SIZE, SIZE, is_data=True)
    nout.colorspace_settings.name = "Non-Color"
    nout.pixels.foreach_set(nrm.ravel())
    nout.filepath_raw = os.path.join(OUT_DIR, "noah_normal_game_final.png")
    nout.file_format = "PNG"
    nout.save()
    for n in low.data.materials[0].node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image and n.image.name in ("NoahNormalGame", "NoahNormalFinal"):
            n.image = nout

    out = bpy.data.images.get("NoahColorFinal") or bpy.data.images.new("NoahColorFinal", SIZE, SIZE)
    rgba = np.concatenate([np.clip(color, 0, 1), np.ones((SIZE, SIZE, 1), np.float32)], -1)
    out.pixels.foreach_set(rgba.ravel())
    out.filepath_raw = os.path.join(OUT_DIR, "noah_color_game.png")
    out.file_format = "PNG"
    out.save()
    tex = next(n for n in low.data.materials[0].node_tree.nodes
               if n.type == "TEX_IMAGE" and n.image and n.image.name in ("NoahBaseColor", "NoahColorFinal"))
    tex.image = out
    print("painted", "coverage", f"{valid.mean():.0%}")


def step_export(path):
    low = _low()
    me = low.data
    # Only the new UV in the game file.
    for layer in [l for l in me.uv_layers if l.name != UV_GAME]:
        me.uv_layers.remove(layer)
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.context.scene.objects:
        if o.name == LOW or o.name.startswith(("NoahEye", "EyeGlint", "NoahBrow", "RodinTurn", "Rodin")):
            o.select_set(True)
    nodes = low.data.materials[0].node_tree.nodes
    for n in [n for n in nodes if n.type == "TEX_IMAGE" and n.image and n.image.name == "NoahAO"]:
        nodes.remove(n)     # The occlusion is already painted into the color; it isn't exported separately.
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True)
    total = 0
    for o in bpy.context.selected_objects:
        if o.type == "MESH":
            ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
            total += sum(len(p.vertices) - 2 for p in ev.data.polygons)
    print("exported", path, "triangles", total)
    if total > 4000:
        print("WARNING: more triangles than expected; check modifiers (e.g. smoothing added by hand)")
