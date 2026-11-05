"""Paints a generated character (shape only, Hunyuan3D) with the colors of its turnaround sheet, by parts, and
leaves it with a clean texture.

Usage (without opening Blender):
    blender --background --factory-startup --python tools/blender/paint_character.py -- \\
        <model.glb> <name> <height_m> <output.glb> [renders_folder]

The cropped views of the sheet go in references/character_views/<name>_{front,side,back,
three_quarters}.png (each one tight to the figure). Steps:
1. Cleans the mesh (removes loose bits), stands it up at its height, centered and facing -Y.
2. Each view is fitted to the model's silhouette (camera turn) and projected onto the detailed
   model. With a depth buffer, each point only takes color from the views that really see it
   (with nothing in front); the side and three-quarter views are also used mirrored for the other side.
3. The color of each view is matched to the most similar part in PARTS (several sample tones per part,
   so the drawing's shading doesn't change the part), among those the body zone allows; some
   parts go by position (hands, sole, nape). Each view votes weighted by how squarely it sees the
   point, and the part with the most votes wins.
4. What no view sees takes the part of the nearest seen point; then loose spots are removed
   (each point takes the part of the majority of its neighbors).
5. Light copy with UV: each pixel of the texture takes the color of the part of the nearest detailed
   point. That way the edges between parts stay sharp with few triangles.
"""

import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector, kdtree

ROOT = os.getcwd()
_ns = {"__name__": "process_generated"}
exec(open(os.path.join(ROOT, "tools/blender/process_generated.py"), encoding="utf-8").read()
     .replace("\nmain()\n", "\n"), _ns)
_project, _to_pixels = _ns["_project"], _ns["_to_pixels"]

DETAIL = 160000             # Faces of the detailed model (for painting).
FACES = 12000               # Faces of the game model.
TEXTURE = 1024
RES = 512                   # Resolution of each view when projecting.
FOLD = 0.3                  # Angle (rad) of an inward fold that separates patches.
SMALL = ["eye", "hair", "sash"]
MAJORITY = 0.6              # Share of a patch that one part has to have to paint it whole.

# Parts: final color (sRGB) and sample tones taken from the sheet (sRGB 0-255).
PARTS = {
    "skin": ((0.93, 0.71, 0.60), [(214, 159, 128), (232, 182, 152), (196, 140, 112)]),
    "hair": ((0.70, 0.70, 0.72), [(165, 165, 168), (140, 140, 146), (196, 196, 199)]),
    "headscarf": ((0.92, 0.87, 0.74), [(219, 205, 179), (187, 173, 153), (240, 232, 212)]),
    "eye": ((0.20, 0.15, 0.13), [(60, 45, 40), (40, 30, 28)]),
    "dress": ((0.71, 0.50, 0.47), [(177, 127, 112), (157, 109, 90), (130, 88, 72)]),
    "overtunic": ((0.55, 0.62, 0.50), [(147, 146, 124), (123, 127, 105), (91, 94, 81), (165, 168, 145)]),
    "sash": ((0.80, 0.60, 0.30), [(200, 150, 70), (170, 120, 50), (222, 176, 96)]),
    "sandal": ((0.55, 0.38, 0.25), [(150, 100, 60), (110, 72, 45), (175, 125, 85)]),
}
NAMES = list(PARTS)
# Gemini parts map (references/PROMPTS.md, no. 21): the same sheet with one pure color per part.
# If it exists (references/character_views/<name>_parts_<view>.png), it's used instead of guessing the part
# from the drawing's shaded color, and the zone rules aren't needed.
FLATS = {"skin": (255, 128, 0), "hair": (128, 128, 128), "headscarf": (255, 255, 0), "eye": (0, 0, 0),
         "dress": (255, 0, 0), "overtunic": (0, 255, 0), "sash": (0, 0, 255), "sandal": (139, 69, 19)}
PURITY = 3 * 45 ** 2        # Maximum (squared) distance to a pure color for the pixel to count.
# Possible parts by height (fraction of the character's height).
ZONES = [(0.0, 0.06, ["skin", "sandal"]),
         (0.06, 0.62, ["dress", "overtunic", "sash"]),
         (0.62, 0.71, ["headscarf", "overtunic", "dress"]),
         (0.71, 1.01, ["skin", "hair", "headscarf", "eye"])]
# Parts that go by position: the hands (far from the center, as a fraction of the half width, and below the
# cuff), the sole of the sandals, and the nape and the sides of the head (whatever doesn't face the front).
HANDS = (0.62, 0.28, 0.40)
CUFFS = (0.40, 0.5)             # Sleeve cuffs, above the hands: the color of the dress.
SOLE = 0.02
NAPE = -0.25
# The sash: its band at the waist (heights, width) and the knot hanging in the center (heights, width).
SASH = ((0.42, 0.53, 0.62), (0.28, 0.53, 0.2))
EYES = (0.82, 0.9)
# The hair only peeks out at the forehead: heights, width (fraction of the half width) and how much it faces the front.
HAIR = (0.87, 0.95, 0.42, -0.6)
# Views of the sheet: expected camera turn (degrees) and whether they're also used mirrored.
VIEWS = {"front": (0, False), "side": (90, True), "back": (180, False), "three_quarters": (35, True)}


def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in [o for o in bpy.data.objects if o.type != "MESH"]:
        bpy.data.objects.remove(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.active_object
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def decimate(obj, faces):
    mod = obj.modifiers.new("Decimate", "DECIMATE")
    mod.ratio = min(1.0, faces / max(1, len(obj.data.polygons)))
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def prepare(obj, height):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    seen, islands = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, isl = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            isl.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        islands.append(isl)
    big = max(len(i) for i in islands)
    bmesh.ops.delete(bm, geom=[f for i in islands if len(i) < big * 0.02 for f in i], context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    co = np.array([v.co for v in obj.data.vertices])
    lo, hi = co.min(0), co.max(0)
    s = height / (hi[2] - lo[2])
    for v in obj.data.vertices:
        v.co = Vector(((v.co.x - (lo[0] + hi[0]) / 2) * s, (v.co.y - (lo[1] + hi[1]) / 2) * s, (v.co.z - lo[2]) * s))
    decimate(obj, DETAIL)
    for p in obj.data.polygons:
        p.use_smooth = True


def load_view(name, kind, flip):
    img = bpy.data.images.load(os.path.join(ROOT, "references/character_views", f"{name}_{kind}.png"))
    img.scale(RES, RES)
    px = np.array(img.pixels[:], np.float32).reshape(RES, RES, 4)[::-1, :, :3] * 255
    bpy.data.images.remove(img)
    if flip:
        px = px[:, ::-1]
    mask = px.min(-1) < 232
    rows, cols = np.nonzero(mask)
    return px, mask, (cols.min(), rows.min(), cols.max(), rows.max())


def fit_yaw(points, mask, box, around):
    """Camera turn (near the expected one) at which the model's silhouette best fits the view."""
    sample = points[np.random.default_rng(1).choice(len(points), min(30000, len(points)), False)]
    best = (-1.0, 0.0)
    for deg in range(around - 30, around + 31, 3):
        x, y, _ = _project(sample, math.radians(deg), 0.0)
        c, r = _to_pixels(x, y, RES, box)
        sil = np.zeros((RES, RES), bool)
        sil[r, c] = True
        sil = sil | np.roll(sil, 1, 0) | np.roll(sil, 1, 1) | np.roll(sil, -1, 0) | np.roll(sil, -1, 1)
        iou = (sil & mask).sum() / max((sil | mask).sum(), 1)
        if iou > best[0]:
            best = (iou, math.radians(deg))
    return best


def allowed_parts(p, lo, hi, height, normal):
    """Part fixed by position (or None) and parts allowed by color for a point."""
    zf = p[2] / height
    xf = abs(p[0] - (lo[0] + hi[0]) / 2) / ((hi[0] - lo[0]) / 2)
    if xf > HANDS[0] and HANDS[1] < zf < HANDS[2]:
        return "skin", None
    if zf < SOLE:
        return "sandal", None
    if zf >= 0.7 and normal[1] > NAPE:
        return "headscarf", None
    allowed = next(z[2] for z in ZONES if z[0] <= zf < z[1])
    if not any(z0 < zf < z1 and xf < w for z0, z1, w in SASH):
        allowed = [a for a in allowed if a != "sash"]
    if not EYES[0] < zf < EYES[1]:
        allowed = [a for a in allowed if a != "eye"]
    if not (HAIR[0] < zf < HAIR[1] and xf < HAIR[2] and normal[1] < HAIR[3]):
        allowed = [a for a in allowed if a != "hair"]
    if xf > HANDS[0] and CUFFS[0] <= zf < CUFFS[1]:
        allowed = ["dress"]
    return None, allowed


def label_points(obj, name, height):
    me = obj.data
    points = np.array([v.co for v in me.vertices])
    normals = np.array([v.normal for v in me.vertices])
    lo, hi = points.min(0), points.max(0)
    size = float(np.ptp(points, 0).max())
    votes = np.zeros((len(points), len(NAMES)))
    rules = [allowed_parts(p, lo, hi, height, n) for p, n in zip(points, normals)]
    protos = [(NAMES.index(n), np.array(c, float)) for n, (_, cs) in PARTS.items() for c in cs]
    flat = os.path.exists(os.path.join(ROOT, "references/character_views", f"{name}_parts_front.png"))
    flat_cols = np.array([FLATS[n] for n in NAMES], float)
    for kind, (around, mirrored) in VIEWS.items():
        for flip in ((False, True) if mirrored else (False,)):
            px, mask, box = load_view(name + "_parts" if flat else name, kind, flip)
            iou, yaw = fit_yaw(points, mask, box, -around if flip else around)
            x, y, depth = _project(points, yaw, 0.0)
            c, r = _to_pixels(x, y, RES, box)
            zbuf = np.full((RES, RES), np.inf)
            np.minimum.at(zbuf, (r, c), depth)
            near = np.minimum.reduce([np.roll(np.roll(zbuf, dr, 0), dc, 1) for dr in (-1, 0, 1) for dc in (-1, 0, 1)])
            inner = mask.copy()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)):
                inner &= np.roll(np.roll(mask, dr, 0), dc, 1)
            d = np.array([math.sin(yaw), math.cos(yaw), 0.0])
            facing = np.clip(-(normals @ d), 0.0, 1.0)
            visible = (depth <= near[r, c] + size * 0.01) & inner[r, c] & (facing > 0.15)
            weight = 1.5 if kind == "front" else 1.0       # The front one is the one the model comes from.
            if flat:
                vis = np.nonzero(visible)[0]
                cols = px[r[vis], c[vis]]
                dist = ((cols[:, None, :] - flat_cols[None]) ** 2).sum(-1)
                part = dist.argmin(1)
                # Out go the pixels on the edge between two parts (mixed colors) and the colors that don't
                # fit where they are: the brown of the sandal far from the feet, the black of the eyes far from
                # the face.
                zf = points[vis, 2] / height
                ok = dist[np.arange(len(vis)), part] < PURITY
                ok &= (part != NAMES.index("sandal")) | (zf < 0.08)
                ok &= (part != NAMES.index("eye")) | ((zf > EYES[0]) & (zf < EYES[1]))
                np.add.at(votes, (vis[ok], part[ok]), weight * facing[vis[ok]] ** 2)
                print(f"  view {kind}{' (mirrored)' if flip else ''}: turn {math.degrees(yaw):.0f}, fit {iou:.2f}, "
                      f"sees {visible.mean():.0%} (parts map)", flush=True)
                continue
            for i in np.nonzero(visible)[0]:
                if rules[i][0]:
                    continue
                col = px[r[i], c[i]]
                best = min((np.sum((col - pc) ** 2), k) for k, pc in protos if NAMES[k] in rules[i][1])
                # The sash is thin and the drawing's shading mixes it up with the dress: where there can be a sash,
                # its vote counts double.
                boost = 2.0 if NAMES[best[1]] == "sash" else 1.0
                votes[i, best[1]] += weight * boost * facing[i] ** 2
            print(f"  view {kind}{' (mirrored)' if flip else ''}: turn {math.degrees(yaw):.0f}, fit {iou:.2f}, "
                  f"sees {visible.mean():.0%}", flush=True)
    labels = votes.argmax(1)
    labels[votes.sum(1) == 0] = -1
    for i, (fixed, _) in enumerate(rules):
        if fixed and not flat:
            labels[i] = NAMES.index(fixed)
    # What no view sees: the part of the nearest point that has a part.
    known = np.nonzero(labels >= 0)[0]
    tree = kdtree.KDTree(len(known))
    for k, i in enumerate(known):
        tree.insert(points[i], k)
    tree.balance()
    for i in np.nonzero(labels < 0)[0]:
        labels[i] = labels[known[tree.find(points[i])[1]]]
    return points, clean_spots(me, labels)


def clean_spots(me, labels, rounds=10):
    edges = np.array([e.vertices[:] for e in me.edges])
    k = len(NAMES)
    for _ in range(rounds):
        votes = np.zeros((len(labels), k))
        np.add.at(votes, (edges[:, 0], labels[edges[:, 1]]), 1)
        np.add.at(votes, (edges[:, 1], labels[edges[:, 0]]), 1)
        top = votes.argmax(1)
        change = (votes[np.arange(len(labels)), top] >= votes.sum(1) * 0.6) & (top != labels)
        labels = np.where(change, top, labels)
    return labels


def patch_labels(obj, vlabels):
    """Splits the surface into patches along its inward folds (where the overtunic overlaps the dress,
    the headscarf frames the face, the cuff meets the hand) and gives each patch the part of the majority of
    its faces, if it's a clear majority. That way the edges follow the shape of the clothes and no specks are left.
    Returns the center and the part of each face."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    k = len(NAMES)
    flab = np.array([np.bincount(vlabels[[v.index for v in f.verts]], minlength=k).argmax() for f in bm.faces])
    area = np.array([f.calc_area() for f in bm.faces])
    centers = np.array([f.calc_center_median() for f in bm.faces])
    patch = np.full(len(bm.faces), -1)
    count = 0
    for f in bm.faces:
        if patch[f.index] >= 0:
            continue
        patch[f.index] = count
        stack = [f]
        while stack:
            g = stack.pop()
            for e in g.edges:
                if len(e.link_faces) != 2 or e.calc_face_angle_signed(0.0) < -FOLD:
                    continue
                for h in e.link_faces:
                    if patch[h.index] < 0:
                        patch[h.index] = count
                        stack.append(h)
        count += 1
    bm.free()
    votes = np.zeros((count, k))
    np.add.at(votes, (patch, flab), area)
    top = votes.argmax(1)
    clear = votes[np.arange(count), top] >= votes.sum(1) * MAJORITY
    feet = centers[:, 2] < centers[:, 2].max() * 0.06       # The feet, by color: toes and sandal straps.
    small = np.isin(flab, [NAMES.index(n) for n in SMALL])  # Eyes, hair and sash: a patch doesn't swallow them.
    out = np.where(clear[patch] & ~feet & ~small, top[patch], flab)
    print(f"  patches {count}, with a clear majority {clear.mean():.0%}, faces changed {(out != flab).mean():.1%}",
          flush=True)
    return centers, out


def bake_texture(low, points, labels):
    tree = kdtree.KDTree(len(points))
    for i, p in enumerate(points):
        tree.insert(p, i)
    tree.balance()
    final = np.array([PARTS[n][0] for n in NAMES], np.float32)
    tex = np.zeros((TEXTURE, TEXTURE, 4), np.float32)
    filled = np.zeros((TEXTURE, TEXTURE), bool)
    me = low.data
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data
    co = np.array([v.co for v in me.vertices])
    for tri in me.loop_triangles:
        t = np.array([uv[li].uv for li in tri.loops]) * TEXTURE - 0.5
        p3 = co[list(tri.vertices)]
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1, TEXTURE - 1) + 1),
                             np.arange(max(y0, 0), min(y1, TEXTURE - 1) + 1))
        q = np.stack([xs.ravel(), ys.ravel()], 1).astype(np.float32)
        a, b, c = t
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        w0 = ((b[1] - c[1]) * (q[:, 0] - c[0]) + (c[0] - b[0]) * (q[:, 1] - c[1])) / den
        w1 = ((c[1] - a[1]) * (q[:, 0] - c[0]) + (a[0] - c[0]) * (q[:, 1] - c[1])) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
        for (px, py), bw in zip(q[inside].astype(int), np.stack([w0, w1, w2], 1)[inside]):
            if filled[py, px]:
                continue
            tex[py, px, :3] = final[labels[tree.find(bw @ p3)[1]]]
            tex[py, px, 3] = 1.0
            filled[py, px] = True
    for _ in range(64):                             # Margin around each UV island.
        if filled.all():
            break
        grow = np.zeros_like(filled)
        acc = np.zeros_like(tex)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(np.roll(filled, dy, 0), dx, 1)
            new = sh & ~filled & ~grow
            acc[new] = np.roll(np.roll(tex, dy, 0), dx, 1)[new]
            grow |= new
        tex[grow] = acc[grow]
        filled |= grow
    return tex


def make_low(high, name, points, labels):
    low = high.copy()
    low.data = high.data.copy()
    bpy.context.scene.collection.objects.link(low)
    low.name = low.data.name = name
    decimate(low, FACES)
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    img = bpy.data.images.new(name + "_color", TEXTURE, TEXTURE, alpha=True)
    img.colorspace_settings.name = "sRGB"
    img.pixels[:] = bake_texture(low, points, labels).ravel()
    img.pack()
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.85
    low.data.materials.clear()
    low.data.materials.append(mat)
    bpy.data.objects.remove(high)
    return low


def render(obj, folder, name):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "TEXTURE"
    sc.render.resolution_x, sc.render.resolution_y = 600, 900
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = obj.dimensions.z * 1.1
    for k, ang in (("front", 0), ("side", 90), ("back", 180), ("three_quarters", 35)):
        a = math.radians(ang)
        cam.location = (math.sin(a) * 6, -math.cos(a) * 6, obj.dimensions.z / 2)
        cam.rotation_euler = (math.radians(90), 0, a)
        sc.render.filepath = os.path.join(folder, f"{name}_{k}.png")
        bpy.ops.render.render(write_still=True)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    src, name, height, out = args[0], args[1], float(args[2]), args[3]
    high = load(src)
    prepare(high, height)
    points, labels = label_points(high, name, height)
    points, labels = patch_labels(high, labels)
    counts = np.bincount(labels, minlength=len(NAMES))
    print("PARTS", {n: int(counts[i]) for i, n in enumerate(NAMES)}, flush=True)
    low = make_low(high, name, points, labels)
    print("FACES", len(low.data.polygons), "SIZE", tuple(round(v, 3) for v in low.dimensions))
    if len(args) > 4:
        render(low, args[4], name)
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_yup=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.splitext(out)[0] + ".blend")


main()
