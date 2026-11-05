"""Processes the objects generated with Hunyuan3D (tools/blender/generated/*.glb) for the game.

Usage (without opening Blender):
    blender --background --factory-startup --python tools/blender/process_generated.py -- \\
        assets/village/generated.glb [name ...]

For each object:
1. Cleans it: merges duplicate vertices and removes the loose floating chunks (generator artifacts).
2. Stands it on the ground, centered, with its front facing -Y (in Godot, +Z) and at its real size
   (SIZES, in meters, against Noah at 1.55 m).
3. Reduces it to a reasonable triangle count for the game (TRIANGLES).
4. Paints it with the colors of its cutout (references/cutouts/<name>.png): finds the camera angle
   from which the model's silhouette matches the drawing's and projects the colors from
   there; the parts not seen in the drawing take the color of the nearest visible part.
All objects are exported together in a single .glb, each with its name.
"""

import math
import os
import re
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, kdtree

ROOT = os.getcwd()
SRC = os.environ.get("GENERATED_DIR", os.path.join(ROOT, "tools/blender/generated"))
CUTS = os.path.join(ROOT, "references/cutouts")

# Real size: ("height" | "width", meters). "width" is the largest horizontal measurement.
SIZES = {
    "well": ("height", 2.1), "oven": ("height", 0.95), "jugs": ("width", 1.0),
    "baskets": ("width", 0.9), "sacks": ("width", 1.0),
    "loom": ("height", 1.55), "clothesline": ("width", 2.8), "bench": ("width", 1.5),
    "log_seats": ("width", 1.1), "table": ("width", 2.0), "fence": ("width", 2.1),
    "trough": ("width", 1.8), "firewood": ("width", 1.1), "campfire": ("width", 1.4), "garden_bed": ("width", 2.0),
    # Pieces to build the stalls (build_stalls.py): the empty stall and its goods.
    "empty_stall": ("height", 2.3), "cream_rolls": ("width", 0.75), "colored_rolls": ("width", 0.7),
    "folded_cloths": ("width", 0.6), "apple_crate": ("width", 0.55), "orange_crate": ("width", 0.55),
    "pear_crate": ("width", 0.55), "grape_crate": ("width", 0.55),
    "apple_fruit": ("width", 0.45), "orange_fruit": ("width", 0.45), "pear_fruit": ("width", 0.45),
    "grape_fruit": ("width", 0.45),
    # Campfire pieces (build_campfire.py): the ring of stones with its ash and the logs in a tipi.
    "campfire_stones": ("width", 1.3), "campfire_logs": ("height", 0.5),
}
# Goods: whatever is not wood has no grain (alpha 0.7 in the vertex color).
NO_GRAIN = {"cream_rolls", "colored_rolls", "folded_cloths", "apple_crate", "orange_crate", "pear_crate",
            "grape_crate", "jugs", "apple_fruit", "orange_fruit", "pear_fruit", "grape_fruit"}
# Final triangles: the ones repeated a lot (fence) lighter; the plaza ones, with more detail.
TRIANGLES = {"fence": 1500, "firewood": 3000, "log_seats": 2000, "sacks": 4000, "baskets": 5000,
             "jugs": 5000, "well": 9000, "loom": 7000, "garden_bed": 7000, "empty_stall": 10000,
             "cream_rolls": 2500, "colored_rolls": 2500, "folded_cloths": 3000, "apple_crate": 3500,
             "orange_crate": 3500, "pear_crate": 3500, "grape_crate": 3500, "apple_fruit": 14000,
             "orange_fruit": 12000, "pear_fruit": 14000, "grape_fruit": 14000,   # Fruit: more, or the stems get lost.
             "campfire_stones": 6000, "campfire_logs": 3000}
DEFAULT_TRIANGLES = 6000
# How many main colors each drawing has (default, 5).
# Single-material ones get one clean color (the game's lighting gives them volume).
PALETTES = {"oven": 1, "bench": 1, "table": 1, "fence": 1, "firewood": 1, "log_seats": 1, "sacks": 1,
            "jugs": 1, "trough": 2, "well": 4, "campfire": 4, "baskets": 6, "fruit_stall": 6, "garden_bed": 4,
            "loom": 4, "clothesline": 5, "empty_stall": 3, "cream_rolls": 1, "colored_rolls": 2,
            "folded_cloths": 4, "apple_crate": 3, "orange_crate": 3, "pear_crate": 3, "grape_crate": 3, "apple_fruit": 4,
            "orange_fruit": 4, "pear_fruit": 4, "grape_fruit": 4,
            "campfire_stones": 1, "campfire_logs": 1}


def base(name):
    """Object name without the version suffix (bench_v42 → bench): for sizes, colors and cutout."""
    return re.sub(r"_v\d+$", "", name)


def load(name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(SRC, name + ".glb"))
    meshes = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    for o in [o for o in bpy.data.objects if o not in before and o.type != "MESH"]:
        bpy.data.objects.remove(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.active_object
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.name = name
    obj.data.name = name
    return obj


# Loose chunks to keep even if small: the campfire flames are separate pieces.
KEEP_CHUNKS = {"campfire"}


def clean(obj, keep_islands=False):
    """Merges duplicate vertices and removes small loose chunks (< 0.4% of the faces)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.faces.ensure_lookup_table()
    seen = set()
    islands = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, island = [f], []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            island.append(cur)
            for e in cur.edges:
                for nf in e.link_faces:
                    if nf.index not in seen:
                        seen.add(nf.index)
                        stack.append(nf)
        islands.append(island)
    total = len(bm.faces)
    drop = [] if keep_islands else [f for isl in islands if len(isl) < total * 0.004 for f in isl]
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    return len(islands), len([i for i in islands if len(i) < total * 0.004])


def place(obj, name):
    """Standing on the ground, centered and at its real size."""
    co = np.array([v.co for v in obj.data.vertices])
    lo, hi = co.min(0), co.max(0)
    kind, meters = SIZES[base(name)]
    size = (hi[2] - lo[2]) if kind == "height" else max(hi[0] - lo[0], hi[1] - lo[1])
    s = meters / size
    offset = Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
    for v in obj.data.vertices:
        v.co = (v.co + offset) * s


def decimate(obj, target):
    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    if tris > target:
        mod = obj.modifiers.new("Decimate", "DECIMATE")
        mod.ratio = target / tris
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)


def _cut_mask(name, res):
    """Drawing cutout: colors (linear, 0-1) and mask of what isn't white background, at res × res."""
    img = bpy.data.images.load(os.path.join(CUTS, base(name) + ".png"))
    img.scale(res, res)
    px = np.array(img.pixels[:], np.float32).reshape(res, res, 4)[::-1, :, :3]   # Row 0 at the top.
    bpy.data.images.remove(img)
    srgb = px                                        # Blender gives the PNG pixels in sRGB.
    mask = (np.abs(srgb - 1.0).sum(-1) > 0.12)
    return srgb, mask


def _project(points, yaw, elev):
    """Orthographic projection from a camera rotated `yaw` and raised `elev` (radians), looking toward +Y."""
    d = np.array([math.sin(yaw) * math.cos(elev), math.cos(yaw) * math.cos(elev), -math.sin(elev)])
    r = np.array([math.cos(yaw), -math.sin(yaw), 0.0])
    u = np.cross(r, d)
    return points @ r, points @ u, points @ d


def _to_pixels(x, y, res, box):
    """Maps the model's projected box onto the box of the drawing's silhouette (in pixels)."""
    (x0, x1), (y0, y1) = (x.min(), x.max()), (y.min(), y.max())
    c0, r0, c1, r1 = box
    col = c0 + (x - x0) / max(x1 - x0, 1e-6) * (c1 - c0)
    row = r1 - (y - y0) / max(y1 - y0, 1e-6) * (r1 - r0)
    return np.clip(col.round().astype(int), 0, res - 1), np.clip(row.round().astype(int), 0, res - 1)


def _features(rgb):
    """Features to group colors: mostly hue (normalized rgb), a little brightness. That way the shaded
    and lit faces of the same piece fall into the same group."""
    s = rgb.sum(-1, keepdims=True) + 1e-4
    return np.concatenate([rgb / s * 3.0, s * 0.12], -1)


def _palette(pixels, k, iters=14):
    """Main colors (k-means by hue) of the drawing's pixels. Each color is taken from the
    lighter half of its pixels: the lit face, without the painted shadow."""
    rng = np.random.default_rng(3)
    px = pixels[rng.choice(len(pixels), min(6000, len(pixels)), False)]
    fx = _features(px)
    centers = fx[rng.choice(len(fx), k, False)]
    for _ in range(iters):
        lab = np.argmin(((fx[:, None, :] - centers[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if (lab == j).any():
                centers[j] = fx[lab == j].mean(0)
    out = []
    _palette.centers = centers
    for j in range(k):
        group = px[lab == j]
        if len(group) == 0:
            out.append(centers[j])
            continue
        bright = group[group.sum(1) >= np.median(group.sum(1))]
        out.append(bright.mean(0))
    return np.clip(np.array(out), 0.0, 1.0)


def _smooth_labels(obj, labels, k, rounds=6):
    """Each vertex takes the color most common among its neighbors: removes stray specks."""
    edges = np.array([e.vertices[:] for e in obj.data.edges])
    for _ in range(rounds):
        votes = np.zeros((len(labels), k))
        np.add.at(votes, (edges[:, 0], labels[edges[:, 1]]), 1)
        np.add.at(votes, (edges[:, 1], labels[edges[:, 0]]), 1)
        np.add.at(votes, (np.arange(len(labels)), labels), 1.5)
        labels = votes.argmax(1)
    return labels


# Folded cloths, top to bottom (sRGB, from references/market_parts.png).
CLOTH_LAYERS = [(0.42, 0.58, 0.82), (0.27, 0.62, 0.62), (0.88, 0.66, 0.25)]
CRATE_WOOD = (0.62, 0.40, 0.24)


def _cavity(obj):
    """Concavity per vertex (0 flat, > 0 sunken): how much it sinks relative to its neighbors. Used to
    darken the gaps between fruits or the joints between stones."""
    me = obj.data
    co = np.array([v.co for v in me.vertices])
    nrm = np.array([v.normal for v in me.vertices])
    acc = np.zeros(len(co))
    cnt = np.zeros(len(co))
    for e in me.edges:
        a, b = e.vertices
        d = co[b] - co[a]
        ln = np.linalg.norm(d) + 1e-9
        acc[a] += np.dot(nrm[a], d) / ln
        acc[b] += np.dot(nrm[b], -d) / ln
        cnt[a] += 1
        cnt[b] += 1
    return np.clip(acc / np.maximum(cnt, 1), 0.0, 1.0)


# Well, by zones (model measurements in meters): cobbled base, stone curb, wooden posts and crossbar,
# the rope and the water.
BASE_STONE = (0.64, 0.62, 0.59)
STONE = (0.56, 0.55, 0.54)
ROPE = (0.72, 0.57, 0.37)
WATER = (0.20, 0.27, 0.32)


def _well_colors(obj, centers):
    out = np.zeros((len(centers), 3), np.float32)
    alpha = np.full(len(centers), 0.7, np.float32)
    wood = np.array(CRATE_WOOD)
    nrm = np.array([f.normal for f in obj.data.polygons])
    for i, (x, y, z) in enumerate(centers):
        r = np.hypot(x, y)
        # Posts: they widen at the bottom, hence the margin in y; the post's inner face looks toward the center.
        inward = nrm[i][0] * np.sign(x) < -0.3
        # Outside the curb (|x| > 0.75 is never stone except the base) everything is post.
        side = abs(nrm[i][1]) > 0.7                   # Sides of the post (facing forward or back).
        post = z > 0.22 and ((abs(x) > 0.75 and abs(y) < 0.5) or (abs(x) > 0.6 and abs(y) < 0.4 and (inward or side)))
        # Rope: only the stretch that goes down (above the bucket handle) and the loop on the crossbar.
        rope = (abs(x) < 0.08 and abs(y) < 0.08 and 1.28 < z < 1.58) or (abs(x) < 0.2 and 1.58 < z < 1.82)
        bucket = r < 0.32 and z > 0.7 and (nrm[i][0] * x + nrm[i][1] * y) >= 0
        if rope:
            out[i] = ROPE
        elif post or bucket or z > 0.95:
            out[i], alpha[i] = wood, 1.0          # Posts, crossbar, crank and bucket: wood (with grain).
        elif z < 0.2:
            out[i] = BASE_STONE
        elif r < 0.5 and z < 0.86 and (nrm[i][0] * x + nrm[i][1] * y) < 0:
            out[i] = WATER if z < 0.5 else np.array(STONE) * 0.75    # Inside the well.
        else:
            out[i] = STONE
    cav = _cavity(obj)
    for f in obj.data.polygons:
        if alpha[f.index] < 1.0:
            out[f.index] *= 1.0 - np.clip(cav[list(f.vertices)].mean() * 2.5, 0.0, 0.5)   # Joints.
    return out, alpha


STEM = (0.40, 0.25, 0.13)
LEAF = (0.36, 0.62, 0.20)


def _fruit_colors(obj, name, face_col, palette):
    """Pile of fruit: the fruit in its clean color, the stems brown and the little leaves green (per the drawing),
    and the gaps between fruits darker, so each one stands out."""
    fruit = np.array(FRUIT_COLOR[base(name)], np.float32)

    def chroma(c):
        c = np.asarray(c, np.float32)
        return c / (c.sum(-1, keepdims=True) + 1e-4)
    # Each color group in the drawing is fruit, stem or leaf by its hue (ignoring brightness: shaded
    # fruit is still fruit). It's only stem or leaf if its hue is clearly closer.
    kinds = []
    for c in palette:
        d_fruit = np.abs(chroma(c) - chroma(fruit)).sum()
        d_stem = np.abs(chroma(c) - chroma(STEM)).sum()
        d_leaf = np.abs(chroma(c) - chroma(LEAF)).sum()
        if base(name) != "pear_fruit" and d_leaf < d_fruit * 0.6 and d_leaf < d_stem:
            kinds.append(LEAF)
        elif d_stem < d_fruit * 0.5 and c.sum() < fruit.sum() * 0.9:
            kinds.append(STEM)
        else:
            kinds.append(fruit)
    out = np.empty_like(face_col)
    for i, c in enumerate(face_col):
        out[i] = kinds[int(np.argmin(((palette - c) ** 2).sum(1)))]
    cav = _cavity(obj)
    for f in obj.data.polygons:
        c = cav[list(f.vertices)].mean()
        out[f.index] = out[f.index] * (1.0 - np.clip(c * 2.2, 0.0, 0.55))
    return out


def _goods_colors(kind, centers, face_col, colors, inner, palette):
    """Stall goods, by zones instead of projecting the drawing (it came out patchy):
    - Crates: the fruit (the high inner part) in a single color, the most saturated one from the top of the
      drawing; the rest, wood.
    - Folded cloths: each layer (by height) in its color."""
    z = centers[:, 2]
    h0, h1 = z.min(), z.max()
    out = face_col.copy()
    if kind == "folded_cloths":
        band = np.clip(((h1 - z) / max(h1 - h0, 1e-6) * 3).astype(int), 0, 2)
        out[:] = np.array(CLOTH_LAYERS)[band]
        return out
    rows = np.nonzero(inner.any(1))[0]
    cols = np.nonzero(inner.any(0))[0]
    hgt, wid = rows[-1] - rows[0], cols[-1] - cols[0]
    top = inner.copy()
    top[rows[0] + hgt // 2:] = False
    top[:, : cols[0] + wid // 4] = False
    top[:, cols[-1] - wid // 4:] = False
    wood = np.array(CRATE_WOOD)
    cands = _palette(colors[top], 3)
    # The fruit: the top color farthest from wood (and somewhat saturated).
    fruit = cands[np.argmax(((cands - wood) ** 2).sum(1) + (cands.max(1) - cands.min(1)) * 0.3)]
    xy = np.abs(centers[:, :2]) / np.maximum(np.abs(centers[:, :2]).max(0), 1e-6)
    is_fruit = (z > h0 + (h1 - h0) * 0.4) & (xy < 0.8).all(1)   # The same zone that _fill_fruit removes.
    # Fruit a bit lighter and brighter than in the drawing (there it has its shadows painted).
    lum = fruit.mean()
    fruit = np.clip((lum + (fruit - lum) * 1.25) * 1.2, 0.0, 1.0)
    out[:] = wood
    out[is_fruit] = fruit
    return out


# Separately generated fruit pile that goes inside each crate (the fruit of the generated crate comes out as a lump).
# Color of each fruit pile (sRGB): a single clean one; the game's lighting gives it volume.
FRUIT_COLOR = {"apple_fruit": (0.86, 0.18, 0.16), "orange_fruit": (0.98, 0.55, 0.12),
               "pear_fruit": (0.62, 0.80, 0.24), "grape_fruit": (0.50, 0.24, 0.62)}
FRUIT = {"apple_crate": "apple_fruit", "orange_crate": "orange_fruit", "pear_crate": "pear_fruit",
         "grape_crate": "grape_fruit"}


# Stems: (fruits across the pile's width, color, length in m). In the drawing they're thin and get lost when
# reducing the model, so they're added separately on top of each fruit.
STEMS = {"apple_fruit": (6, (0.40, 0.25, 0.13), 0.035), "orange_fruit": (6, (0.30, 0.50, 0.18), 0.012),
         "pear_fruit": (7, (0.40, 0.25, 0.13), 0.04), "grape_fruit": (6, (0.30, 0.50, 0.18), 0.03)}


def _colored(fill, color, alpha=0.7):
    """Object with the geometry fill(bm) creates and a single color ("Color" attribute, per corner)."""
    me = bpy.data.meshes.new("piece")
    bm = bmesh.new()
    fill(bm)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("piece", me)
    bpy.context.scene.collection.objects.link(obj)
    attr = me.color_attributes.new("Color", "BYTE_COLOR", "CORNER")
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color]
    for d in attr.data:
        d.color = (lin[0], lin[1], lin[2], alpha)
    return obj


def _stems(mound, kind, fruit_size):
    """A little stem on top of each fruit: the highest vertices in their neighborhood (radius of half a fruit)."""
    _, color, length = STEMS[kind]
    co = np.array([v.co for v in mound.data.vertices])
    tree = kdtree.KDTree(len(co))
    for i, c in enumerate(co):
        tree.insert((c[0], c[1], 0.0), i)
    tree.balance()
    top = co[:, 2].max()
    peaks = []
    for i in np.argsort(-co[:, 2]):
        c = co[i]
        if c[2] < top - fruit_size * 1.2:
            break
        near = [k for _, k, _ in tree.find_range((c[0], c[1], 0.0), fruit_size * 0.45)]
        if co[near, 2].max() <= c[2] + 1e-6 and all(np.hypot(*(c[:2] - p[:2])) > fruit_size * 0.6 for p in peaks):
            peaks.append(c)
    parts = []
    for p in peaks:
        def fill(bm, p=p):
            bmesh.ops.create_cone(bm, cap_ends=True, segments=5, radius1=fruit_size * 0.05,
                                  radius2=fruit_size * 0.035, depth=length)
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                             matrix=Matrix.Rotation(0.25, 3, "X") @ Matrix.Rotation(np.random.uniform(0, 6.28), 3, "Z"))
            bmesh.ops.translate(bm, vec=(p[0], p[1], p[2] + length * 0.4), verts=bm.verts)
        parts.append(_colored(fill, color))
    return parts


def _fill_fruit(obj, name):
    """Removes the fruit lump from the crate and puts in the separately generated fruit pile
    (references/fruit_piles.png → generated/<type>_fruit.glb): fitted to the crate's hollow, with its
    base on the bottom and its top level with the rim."""
    co = np.array([v.co for v in obj.data.vertices])
    h0, h1 = co[:, 2].min(), co[:, 2].max()
    xh, yh = np.abs(co[:, 0]).max(), np.abs(co[:, 1]).max()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    drop = [f for f in bm.faces if f.calc_center_median().z > h0 + (h1 - h0) * 0.4
            and abs(f.calc_center_median().x) < xh * 0.8 and abs(f.calc_center_median().y) < yh * 0.8]
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    mound = _prepare(FRUIT[base(name)])
    mco = np.array([v.co for v in mound.data.vertices])
    mlo, mhi = mco.min(0), mco.max(0)
    floor_z = h0 + (h1 - h0) * 0.12
    rim = h1 + (h1 - h0) * 0.06                     # The top fruit sticks out a little.
    target = np.array([xh * 1.58, yh * 1.58, rim - floor_z])
    size = mhi - mlo
    # The pile, rotated if needed so its long side lines up with the crate's.
    if (size[0] > size[1]) != (target[0] > target[1]):
        for v in mound.data.vertices:
            v.co = Vector((v.co.y, -v.co.x, v.co.z))
        mco = np.array([v.co for v in mound.data.vertices])
        mlo, mhi = mco.min(0), mco.max(0)
        size = mhi - mlo
    sc = target / np.maximum(size, 1e-6)
    ctr = (mlo + mhi) / 2
    for v in mound.data.vertices:
        p = (np.array(v.co) - np.array([ctr[0], ctr[1], mlo[2]])) * sc
        v.co = Vector((p[0], p[1], p[2] + floor_z))
    faces = len(mound.data.polygons)
    stems = _stems(mound, FRUIT[base(name)], xh * 1.58 / STEMS[FRUIT[base(name)]][0])
    bpy.ops.object.select_all(action="DESELECT")
    for o in stems:
        o.select_set(True)
    mound.select_set(True)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.join()
    return len(drop), faces


def _face_neighbors(obj):
    by_edge = {}
    for f in obj.data.polygons:
        for k in f.edge_keys:
            by_edge.setdefault(k, []).append(f.index)
    nb = [[] for _ in obj.data.polygons]
    for fs in by_edge.values():
        for a in fs:
            nb[a].extend(b for b in fs if b != a)
    return nb


def _woodish(c):
    return c[0] > c[2] * 1.3 and c[0] > c[1] * 1.05 and c.sum() < 2.0


def _paint_stall(obj, centers, colors, inner, vlabels_from, palette):
    """Market stall (the empty one, later built up by build_stalls.py), by zones (heights above the ground, as a fraction of the total height):
    - Awning (> 0.70, except the posts): its strong color and alpha 0; the shader draws the straight
      cream stripes on it.
    - Corner posts and whatever is below the counter (< 0.30): wood.
    - Goods (between 0.30 and 0.70): colors from the drawing's counter (its own palette), one piece in
      one color, smoothed between neighboring faces; alpha 0.7 so the shader doesn't add grain (except
      what's wooden, like the fruit crates)."""
    rows = np.nonzero(inner.any(1))[0]
    cols = np.nonzero(inner.any(0))[0]
    hgt, wid = rows[-1] - rows[0], cols[-1] - cols[0]
    top = colors[rows[0]:rows[0] + max(4, hgt // 4)]
    two = _palette(top[inner[rows[0]:rows[0] + len(top)]], 2)
    sat = two.max(1) - two.min(1)
    strong = two[np.argmax(sat)]
    woodish = [c for c in palette if _woodish(c)]
    wood = max(woodish, key=lambda c: np.ptp(c)) if woodish else palette[0]
    goods_region = np.zeros_like(inner)
    goods_region[rows[0] + hgt * 45 // 100: rows[0] + hgt * 85 // 100, cols[0] + wid // 5: cols[-1] - wid // 5] = True
    goods_region &= inner
    goods_pal = _palette(colors[goods_region], 6)
    goods_centers = _palette.centers

    z = centers[:, 2]
    h0, h1 = z.min(), z.max()
    x, y = centers[:, 0], centers[:, 1]
    corner = (np.abs(x) > np.abs(x).max() * 0.82) & (np.abs(y) > np.abs(y).max() * 0.55)
    # On the awning only the round tip of each post is excluded.
    # Only the round top of each post (at the front and back corners); the valance hanging
    # down the sides is cloth.
    post_tip = ((np.abs(x) > np.abs(x).max() * 0.85) & (np.abs(y) > np.abs(y).max() * 0.6)
                & (z < h0 + (h1 - h0) * 0.78))
    cloth = (z > h0 + (h1 - h0) * 0.70) & ~post_tip
    goods = (z > h0 + (h1 - h0) * 0.30) & ~cloth & ~corner

    # Goods: sampled color of each vertex → the nearest one in the counter palette.
    feats = _features(vlabels_from)
    vlab = np.argmin(((feats[:, None, :] - goods_centers[None]) ** 2).sum(-1), 1)
    polys = obj.data.polygons
    flab = np.array([np.bincount(vlab[list(f.vertices)], minlength=len(goods_pal)).argmax() for f in polys])
    nb = _face_neighbors(obj)
    for _ in range(6):
        new = flab.copy()
        for fi in np.nonzero(goods)[0]:
            votes = np.bincount([flab[n] for n in nb[fi] if goods[n]] + [flab[fi]] * 2, minlength=len(goods_pal))
            new[fi] = votes.argmax()
        flab = new

    out = np.tile(wood, (len(polys), 1)).astype(np.float32)
    alpha = np.ones(len(polys), np.float32)
    out[cloth] = strong
    alpha[cloth] = 0.0
    gcol = goods_pal[flab]
    # The stall is the empty one: what's under the awning is wood (build_stalls.py adds the goods).
    return out, alpha


def paint(obj, high_points, name, res=192):
    """Paints the vertices with the cutout's colors, from the angle that best matches its silhouette."""
    colors, mask = _cut_mask(name, res)
    rows, cols = np.nonzero(mask)
    box = (cols.min(), rows.min(), cols.max(), rows.max())
    sample = high_points[np.random.default_rng(1).choice(len(high_points), min(40000, len(high_points)), False)]
    best = (-1.0, 0.0, 0.0)
    for yaw_deg in range(-90, 91, 6):
        for elev_deg in range(0, 61, 6):
            yaw, elev = math.radians(yaw_deg), math.radians(elev_deg)
            x, y, _ = _project(sample, yaw, elev)
            c, r = _to_pixels(x, y, res, box)
            sil = np.zeros((res, res), bool)
            sil[r, c] = True
            sil = sil | np.roll(sil, 1, 0) | np.roll(sil, 1, 1) | np.roll(sil, -1, 0) | np.roll(sil, -1, 1)
            iou = (sil & mask).sum() / max((sil | mask).sum(), 1)
            if iou > best[0]:
                best = (iou, yaw, elev)
    iou, yaw, elev = best
    # Visibility: minimum depth per pixel with the points of the detailed model.
    x, y, depth = _project(high_points, yaw, elev)
    c, r = _to_pixels(x, y, res, box)
    zbuf = np.full((res, res), np.inf)
    np.minimum.at(zbuf, (r, c), depth)
    verts = np.array([v.co for v in obj.data.vertices])
    vx, vy, vd = _project(verts, yaw, elev)
    # The vertices of the reduced model, with the same box as the detailed one.
    x0, x1, y0, y1 = x.min(), x.max(), y.min(), y.max()
    c0, r0, c1, r1 = box
    vc = np.clip(np.round(c0 + (vx - x0) / (x1 - x0) * (c1 - c0)).astype(int), 0, res - 1)
    vr = np.clip(np.round(r1 - (vy - y0) / (y1 - y0) * (r1 - r0)).astype(int), 0, res - 1)
    size = float(np.ptp(high_points, 0).max())
    near = np.minimum.reduce([np.roll(np.roll(zbuf, dr, 0), dc, 1) for dr in (-1, 0, 1) for dc in (-1, 0, 1)])
    # Only pixels well inside the silhouette count (at the edge the white background leaks in).
    inner = mask.copy()
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)):
        inner &= np.roll(np.roll(mask, dr, 0), dc, 1)
    visible = (vd <= near[vr, vc] + size * 0.03) & inner[vr, vc]
    # Main colors of the drawing: that way each part ends up one clean color (toy style) instead
    # of carrying the painted lights and shadows.
    # On the stalls, the colors of the structure and goods come from the bottom part of the drawing
    # (the awning is at the top, painted separately with stripes).
    region = inner.copy()
    if "_stall" in name:
        rows = np.nonzero(inner.any(1))[0]
        region[: rows[0] + (rows[-1] - rows[0]) * 2 // 5] = False
    palette = _palette(colors[region], PALETTES.get(base(name), 5))
    sampled = _features(colors[vr, vc])
    labels = np.argmin(((sampled[:, None, :] - _palette.centers[None]) ** 2).sum(-1), 1)
    # What isn't seen in the drawing: the nearest visible part.
    tree = kdtree.KDTree(int(visible.sum()))
    vis_idx = np.nonzero(visible)[0]
    for k, i in enumerate(vis_idx):
        tree.insert(verts[i], k)
    tree.balance()
    for i in np.nonzero(~visible)[0]:
        _, k, _ = tree.find(verts[i])
        labels[i] = labels[vis_idx[k]]
    # Fruit piles aren't smoothed much: it would erase the little stems, which are small.
    labels = _smooth_labels(obj, labels, len(palette), rounds=1 if base(name) in FRUIT_COLOR else 6)
    # One color per face (crisp edges, like painted pieces): the one most of its vertices have.
    polys = obj.data.polygons
    face_col = np.zeros((len(polys), 3), np.float32)
    centers = np.zeros((len(polys), 3), np.float32)
    for f in polys:
        ids = list(f.vertices)
        face_col[f.index] = palette[np.bincount(labels[ids], minlength=len(palette)).argmax()]
        centers[f.index] = f.center
    alpha = np.ones(len(polys), np.float32)
    if "_stall" in name:
        # Sampled color of each vertex (hidden ones take the nearest visible one's).
        sampled_rgb = colors[vr, vc].copy()
        for i in np.nonzero(~visible)[0]:
            _, k, _ = tree.find(verts[i])
            sampled_rgb[i] = sampled_rgb[vis_idx[k]]
        face_col, alpha = _paint_stall(obj, centers, colors, inner, sampled_rgb, palette)
    out = face_col
    if base(name) in FRUIT_COLOR:
        out = face_col = _fruit_colors(obj, name, face_col, palette)
    if base(name) == "well":
        face_col, alpha = _well_colors(obj, centers)
        out = face_col
    if base(name).endswith("_crate") or base(name) == "folded_cloths":
        out = face_col = _goods_colors(base(name), centers, face_col, colors, inner, palette)
    if base(name) in NO_GRAIN:
        z = centers[:, 2]
        top = z.min() + (z.max() - z.min()) * 0.55
        xy = np.abs(centers[:, :2]) / np.maximum(np.abs(centers[:, :2]).max(0), 1e-6)
        for f in polys:
            i = f.index
            # Fruit crates: the fruit is the high inner part (the wood, the rim and the sides).
            fruit = base(name).endswith("_crate") and z[i] > top and (xy[i] < 0.84).all()
            if not base(name).endswith("_crate") or fruit or not _woodish(face_col[i]):
                alpha[i] = 0.7
    attr = obj.data.color_attributes.new("Color", "BYTE_COLOR", "CORNER")
    lin = np.where(out <= 0.04045, out / 12.92, ((out + 0.055) / 1.055) ** 2.4)
    for f in polys:
        col = lin[f.index]
        for li in f.loop_indices:
            attr.data[li].color = (col[0], col[1], col[2], float(alpha[f.index]))
    obj.data.color_attributes.active_color = attr
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 0.85
    attr_node = nodes.new("ShaderNodeVertexColor")
    attr_node.layer_name = "Color"
    mat.node_tree.links.new(attr_node.outputs["Color"], bsdf.inputs["Base Color"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return iou, math.degrees(yaw), math.degrees(elev), int(visible.sum()), len(verts)


def _prepare(name):
    """Load, clean, place at its size, reduce and paint a generated object."""
    obj = load(name)
    stats = clean(obj, base(name) in KEEP_CHUNKS)
    place(obj, name)
    high = np.array([v.co for v in obj.data.vertices])
    decimate(obj, TRIANGLES.get(base(name), DEFAULT_TRIANGLES))
    obj["_stats"] = list(stats) + list(paint(obj, high, name))
    return obj


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = argv[0]
    names = argv[1:] or sorted(n for n in SIZES if os.path.exists(os.path.join(SRC, n + ".glb")))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    done = []
    for i, name in enumerate(names):
        obj = _prepare(name)
        islands, dropped, iou, yaw, elev, vis, nv = obj["_stats"]
        if base(name) in FRUIT:
            gone, added = _fill_fruit(obj, name)
            print(f"  {name}: fruit lump removed ({gone} faces), pile of {added} faces", flush=True)
        for p in obj.data.polygons:
            p.use_smooth = True
        obj.location.x = i * 3.0                   # In a row, to see them in Blender.
        tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        print(f"OBJECT {name}: chunks {islands} (removed {dropped}), triangles {tris}, "
              f"size {tuple(round(v, 2) for v in obj.dimensions)}, fit {iou:.2f} "
              f"(yaw {yaw:.0f}, elevation {elev:.0f}), vertices seen {vis}/{nv}", flush=True)
        done.append(obj)
    bpy.ops.object.select_all(action="DESELECT")
    for o in done:
        o.select_set(True)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if os.path.isdir(out):
        # One file per object to touch them up by hand (tools/blender/objects/<name>.blend);
        # then they are gathered and exported with export_objects.py.
        names = [o.name for o in done]
        tmp = os.path.join(out, "_all.blend")
        bpy.ops.wm.save_as_mainfile(filepath=tmp)
        for n in names:
            bpy.ops.wm.open_mainfile(filepath=tmp)
            for o in list(bpy.context.scene.objects):
                if o.name != n:
                    bpy.data.objects.remove(o)
            bpy.data.objects[n].location = (0, 0, 0)
            bpy.ops.outliner.orphans_purge(do_recursive=True)
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, n + ".blend"))
        os.remove(tmp)
        print("GENERATED OK ->", out, flush=True)
        return
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_yup=True,
                              export_vertex_color="ACTIVE")
    print("GENERATED OK ->", out, flush=True)


main()
