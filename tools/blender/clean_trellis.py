"""Prepares a character generated with TRELLIS (Hugging Face, with texture) for the game.

Usage (without opening Blender):
    blender --background --factory-startup --python tools/blender/clean_trellis.py -- \
        <trellis.glb> <output.glb> <height_m> <yaw_degrees>

TRELLIS delivers the mesh in hundreds of pieces, with a metallic material and flat faces: the pieces are
joined back together, the material becomes matte, the surface smooth (except sharp creases), the texture a bit
lighter (it comes with baked shadow), and the character standing, centered, at its height and facing -Y
(yaw_degrees fixes it if it comes out sideways). The views you send it work best without a background
(the Space's preprocess_image).
"""

import math
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector

src, out, height, yaw = sys.argv[sys.argv.index("--") + 1:][:4]
ANKLE = (0.93, 0.71, 0.60)      # Skin color (sRGB) for the ankles that get added.


def _skin_color(obj, faces):
    """Average texture color on those faces (sRGB): the skin at the top of the foot."""
    me = obj.data
    img = next(n.image for m in me.materials for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image)
    w, h = img.size
    px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[..., :3]
    uv = me.uv_layers.active.data
    cols = [px[int(np.clip(uv[li].uv[1], 0, 0.999) * h), int(np.clip(uv[li].uv[0], 0, 0.999) * w)]
            for f in faces for li in me.polygons[f].loop_indices]
    return np.median(np.array(cols), 0) if cols else np.array(ANKLE)


def fill_ankles(obj):
    """TRELLIS sometimes leaves a gap between the clothing's edge and the feet (no ankles): the feet end up
    floating. If there's no mesh at some low height, each ankle starts at the top of its foot (its center and
    its thickness) and rises up inside the clothing, in the same skin color the texture has there."""
    me = obj.data
    co = np.array([v.co for v in me.vertices])
    h = co[:, 2].max()
    zs = np.arange(0.02, 0.25, 0.005) * h / 1.45
    empty = [z for z in zs if not (np.abs(co[:, 2] - z) < 0.003).any()]
    if not empty:
        return
    top, bottom = max(empty), min(empty)
    band = co[(co[:, 2] < bottom) & (co[:, 2] > bottom - 0.025)]      # The top of the feet.
    hem = co[(co[:, 2] > top) & (co[:, 2] < top + 0.02)]               # The clothing's edge.
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    for side in (-1, 1):
        ring = band[band[:, 0] * side > 0]
        if len(ring) < 3:
            continue
        cx, cy = ring[:, 0].mean(), ring[:, 1].mean()
        r0 = np.median(np.hypot(ring[:, 0] - cx, ring[:, 1] - cy)) * 0.95
        # The skin, taken from the hands (the widest part of the body, arms down or in T): the skin at the top
        # of the foot mixes with the sandal strap. It is lightened like the texture (below).
        xmax = np.abs(co[:, 0]).max()
        hands = [f.index for f in bm.faces if abs(f.calc_center_median().x) > xmax * 0.9]
        col = np.clip(_skin_color(obj, hands) * 1.08, 0, 1)
        mat = bpy.data.materials.new(f"Ankle{side}")
        mat.use_nodes = True
        b = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*[c ** 2.2 for c in col], 1)
        b.inputs["Roughness"].default_value = 0.9
        me.materials.append(mat)
        slot = len(me.materials) - 1
        z0, z1 = bottom - 0.02, top + 0.06
        ret = bmesh.ops.create_cone(bm, cap_ends=False, segments=12, radius1=r0, radius2=r0 * 1.05, depth=z1 - z0)
        bmesh.ops.translate(bm, verts=ret["verts"], vec=(cx, cy, (z0 + z1) / 2))
        for face in {fc for v in ret["verts"] for fc in v.link_faces}:
            face.material_index = slot
            face.smooth = True
        print(f"ankle {side}: center ({cx:.3f}, {cy:.3f}), radius {r0:.3f}, color {np.round(col, 2)}")
    bm.to_mesh(me)
    bm.free()
    print("ankles added, gap from", round(bottom, 3), "to", round(top, 3), "clothing edge", len(hem))


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
ms = [o for o in bpy.data.objects if o.type == "MESH"]
for o in [o for o in bpy.data.objects if o.type != "MESH"]:
    bpy.data.objects.remove(o)
bpy.ops.object.select_all(action="DESELECT")
for o in ms: o.select_set(True)
bpy.context.view_layer.objects.active = ms[0]
if len(ms) > 1: bpy.ops.object.join()
obj = bpy.context.active_object
obj.rotation_mode = "XYZ"
obj.rotation_euler[2] += math.radians(float(yaw))
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
# Tiny loose chunks out (the sandals and other separate pieces stay).
bm = bmesh.new(); bm.from_mesh(obj.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
seen, isl = set(), []
for f in bm.faces:
    if f.index in seen: continue
    st, cur = [f], []; seen.add(f.index)
    while st:
        g = st.pop(); cur.append(g)
        for e in g.edges:
            for h in e.link_faces:
                if h.index not in seen: seen.add(h.index); st.append(h)
    isl.append(cur)
big = max(len(i) for i in isl)
gone = [f for i in isl if len(i) < 3 for f in i]
bmesh.ops.delete(bm, geom=gone, context="FACES")
bm.to_mesh(obj.data); bm.free()
co = np.array([v.co for v in obj.data.vertices]); lo, hi = co.min(0), co.max(0)
s = float(height) / (hi[2] - lo[2])
for v in obj.data.vertices:
    v.co = Vector(((v.co.x - (lo[0] + hi[0]) / 2) * s, (v.co.y - (lo[1] + hi[1]) / 2) * s, (v.co.z - lo[2]) * s))
obj.name = obj.data.name = "wife"
# TRELLIS delivers it as metal (metallic 1) and with flat faces: matte cloth and skin, and a smooth surface
# except at sharp creases.
for m in obj.data.materials:
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Metallic"].default_value = 0.0
    b.inputs["Roughness"].default_value = 0.9
    b.inputs["Specular IOR Level"].default_value = 0.3
bpy.context.view_layer.objects.active = obj
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
fill_ankles(obj)
# TRELLIS bakes some shadow into the texture: it is lightened so it looks like the turnaround sheet.
for img in bpy.data.images:
    if img.size[0] > 0:
        px = np.array(img.pixels[:], np.float32).reshape(-1, 4)
        px[:, :3] = np.clip(px[:, :3] * 1.08, 0, 1)
        img.pixels[:] = px.ravel(); img.pack()
print("chunks", len(isl), "removed", len(gone), "size", [round(v, 3) for v in obj.dimensions], "faces", len(obj.data.polygons))
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=False, export_yup=True)
