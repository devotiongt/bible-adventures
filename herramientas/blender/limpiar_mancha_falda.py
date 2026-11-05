"""Quita de la textura de un personaje las manchas de piel pintadas en la falda (TRELLIS pinta el brazo
donde en el dibujo tocaba la túnica). En las caras de la falda (por altura y cerca del centro, sin manos ni
piernas), los píxeles rosados toman el color de la tela.

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/limpiar_mancha_falda.py -- \\
        <entrada.glb> <salida.glb> <z_desde> <z_hasta> <medio_ancho>
"""

import sys

import bpy
import numpy as np

src, out, z0, z1, half = sys.argv[sys.argv.index("--") + 1:][:5]
z0, z1, half = float(z0), float(z1), float(half)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
obj = next(o for o in bpy.data.objects if o.type == "MESH")
me = obj.data
img = next(n.image for m in me.materials for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image)
w, h = img.size
px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)
uv = me.uv_layers.active.data
mask = np.zeros((h, w), bool)
me.calc_loop_triangles()
for tri in me.loop_triangles:
    c = obj.matrix_world @ tri.center
    if not (z0 < c.z < z1 and abs(c.x) < half):
        continue
    t = np.array([uv[li].uv for li in tri.loops]) * [w, h]
    x0, y0 = np.floor(t.min(0)).astype(int)
    x1, y1 = np.ceil(t.max(0)).astype(int)
    xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1, w - 1) + 1), np.arange(max(y0, 0), min(y1, h - 1) + 1))
    q = np.stack([xs.ravel(), ys.ravel()], 1).astype(np.float32) + 0.5
    a, b, cc = t
    den = (b[1] - cc[1]) * (a[0] - cc[0]) + (cc[0] - b[0]) * (a[1] - cc[1])
    if abs(den) < 1e-9:
        continue
    w0 = ((b[1] - cc[1]) * (q[:, 0] - cc[0]) + (cc[0] - b[0]) * (q[:, 1] - cc[1])) / den
    w1 = ((cc[1] - a[1]) * (q[:, 0] - cc[0]) + (a[0] - cc[0]) * (q[:, 1] - cc[1])) / den
    inside = (w0 >= -0.05) & (w1 >= -0.05) & (1 - w0 - w1 >= -0.05)
    mask[ys.ravel()[inside], xs.ravel()[inside]] = True
rgb = px[..., :3]
# Tono de la tela: proporción rojo/azul y verde/azul de lo que es tela (lo menos rojizo de la falda).
ratio = rgb[..., 0] / np.maximum(rgb[..., 2], 1e-3)
cloth = mask & (ratio < np.percentile(ratio[mask], 50))
tela_ratio = np.median(ratio[cloth])
spot = mask & (ratio > tela_ratio * 1.05)                  # Rosado: piel pintada en la tela.
# Se rellena desde los bordes con el color de la tela vecina (conserva la luz y los pliegues de alrededor).
good = mask & ~spot
for _ in range(200):
    todo = spot & ~good
    if not todo.any():
        break
    acc = np.zeros_like(rgb)
    cnt = np.zeros(mask.shape)
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        sg = np.roll(np.roll(good, dy, 0), dx, 1)
        acc += np.roll(np.roll(rgb, dy, 0), dx, 1) * sg[..., None]
        cnt += sg
    fill = todo & (cnt > 0)
    rgb[fill] = acc[fill] / cnt[fill][:, None]
    good |= fill
tela = np.median(rgb[cloth], 0)
px[..., :3] = rgb
img.pixels[:] = px.ravel()
img.pack()
print("FALDA texels", int(mask.sum()), "manchas corregidas", int(spot.sum()), "tela", np.round(tela, 3))
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=False, export_yup=True)
