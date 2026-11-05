"""Pinta un objeto generado a partir de su mapa de materiales y lo deja con una textura limpia.

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/pintar_materiales.py -- pozo

El mapa de materiales (referencias/recortes/<nombre>_materiales.png) es el mismo dibujo del que salió el
modelo, recoloreado por Gemini con un color plano y puro por material (ver referencias/PROMPTS.md, n.º 16).
Así no hay que adivinar nada a partir de luces y sombras:
1. Se prepara el modelo como en procesar_generados.py (limpiar, de pie, a su tamaño) y se busca el ángulo
   de cámara desde el que su silueta coincide con la del mapa.
2. Cada punto del modelo detallado toma el material del píxel que le cae encima (los que no se ven, el del
   punto visible más cercano), y se pinta con el color final de ese material (MATERIALES).
3. Se hace una copia ligera, se le despliega la UV y se hornea el color del detallado en una textura:
   los bordes entre materiales quedan nítidos aunque el modelo final tenga pocos triángulos.
   El alfa de la textura marca la madera (1, lleva veta en el juego) del resto (0,7).
   (Se calcula a mano, punto más cercano por píxel: el horneado de Cycles salía vacío en segundo plano.)
Guarda herramientas/blender/objetos/<nombre>.blend, que exportar_objetos.py manda al juego.
"""

import math
import os
import sys

import bpy
import numpy as np
from mathutils import kdtree

ROOT = os.getcwd()
_ns = {"__name__": "procesar_generados"}
exec(open(os.path.join(ROOT, "herramientas/blender/procesar_generados.py"), encoding="utf-8").read()
     .replace("\nmain()\n", "\n"), _ns)
load, clean, place, decimate, base = _ns["load"], _ns["clean"], _ns["place"], _ns["decimate"], _ns["base"]
_project, _to_pixels = _ns["_project"], _ns["_to_pixels"]
TRIANGULOS, TRIANGULOS_POR_DEFECTO = _ns["TRIANGULOS"], _ns["TRIANGULOS_POR_DEFECTO"]
CONSERVAR_TROZOS = _ns["CONSERVAR_TROZOS"]

CUTS = os.path.join(ROOT, "referencias/recortes")
OUT = os.path.join(ROOT, "herramientas/blender/objetos")

# Material: (color en el mapa de Gemini, color final sRGB, es madera).
MATERIALES = {
    "piedra": ((120, 120, 120), (0.60, 0.59, 0.57), False),
    "junta": ((75, 75, 75), (0.43, 0.42, 0.41), False),
    "madera": ((139, 69, 19), (0.62, 0.40, 0.24), True),
    "cuerda": ((255, 215, 0), (0.80, 0.64, 0.40), False),
    "agua": ((0, 0, 0), (0.17, 0.23, 0.29), False),
    "metal": ((0, 0, 255), (0.42, 0.44, 0.48), False),
}
TEXTURA = 1024


def map_files(name):
    """Todos los mapas de materiales del objeto: el del dibujo y los de las vistas pintadas por Gemini."""
    files = [os.path.join(CUTS, name + "_materiales.png")]
    views = os.path.join(ROOT, "referencias/vistas")
    if os.path.isdir(views):
        files += sorted(os.path.join(views, f) for f in os.listdir(views)
                        if f.startswith(name + "_") and f.endswith("_materiales.png"))
    return [f for f in files if os.path.exists(f)]


def material_map(path, res, flip=False):
    img = bpy.data.images.load(path)
    img.scale(res, res)
    px = np.array(img.pixels[:], np.float32).reshape(res, res, 4)[::-1, :, :3] * 255
    bpy.data.images.remove(img)
    if flip:
        px = px[:, ::-1]                           # Gemini a veces dibuja en espejo.
    mask = np.abs(px - 255).sum(-1) > 40
    keys = list(MATERIALES)
    ref = np.array([MATERIALES[k][0] for k in keys], np.float32)
    labels = np.argmin(((px[:, :, None, :] - ref[None, None]) ** 2).sum(-1), -1)
    return labels, mask, keys


def fit_camera(points, mask, res):
    rows, cols = np.nonzero(mask)
    box = (cols.min(), rows.min(), cols.max(), rows.max())
    sample = points[np.random.default_rng(1).choice(len(points), min(40000, len(points)), False)]
    best = (-1.0, 0.0, 0.0)
    for yaw_deg in range(-180, 180, 6):
        for elev_deg in range(0, 61, 4):
            yaw, elev = math.radians(yaw_deg), math.radians(elev_deg)
            x, y, _ = _project(sample, yaw, elev)
            c, r = _to_pixels(x, y, res, box)
            sil = np.zeros((res, res), bool)
            sil[r, c] = True
            sil = sil | np.roll(sil, 1, 0) | np.roll(sil, 1, 1) | np.roll(sil, -1, 0) | np.roll(sil, -1, 1)
            iou = (sil & mask).sum() / max((sil | mask).sum(), 1)
            if iou > best[0]:
                best = (iou, yaw, elev)
    return best, box


def view_labels(points, normals, labels, mask, box, yaw, elev, res):
    """Material de cada punto según un mapa (-1 si ese mapa no lo ve) y cuánto lo ve de frente (0 a 1)."""
    x, y, depth = _project(points, yaw, elev)
    c, r = _to_pixels(x, y, res, box)
    zbuf = np.full((res, res), np.inf)
    np.minimum.at(zbuf, (r, c), depth)
    near = np.minimum.reduce([np.roll(np.roll(zbuf, dr, 0), dc, 1) for dr in (-1, 0, 1) for dc in (-1, 0, 1)])
    size = float(np.ptp(points, 0).max())
    # Bien dentro de la silueta: en el borde del dibujo se cuela el fondo o la pieza de al lado.
    inner = mask.copy()
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        inner &= np.roll(np.roll(mask, dr, 0), dc, 1)
    visible = (depth <= near[r, c] + size * 0.015) & inner[r, c]
    out = np.full(len(points), -1)
    out[visible] = labels[r[visible], c[visible]]
    d = np.array([math.sin(yaw) * math.cos(elev), math.cos(yaw) * math.cos(elev), -math.sin(elev)])
    facing = np.clip(-(normals @ d), 0.0, 1.0) * visible
    return out, facing


def clean_spots(mesh, labels, rounds=4):
    """Quita manchas sueltas: cada punto toma el material de la mayoría de sus vecinos en la malla (solo
    si una clara mayoría lo pide, para no comerse piezas finas como la cuerda)."""
    edges = np.array([e.vertices[:] for e in mesh.edges])
    k = labels.max() + 1
    for _ in range(rounds):
        votes = np.zeros((len(labels), k))
        np.add.at(votes, (edges[:, 0], labels[edges[:, 1]]), 1)
        np.add.at(votes, (edges[:, 1], labels[edges[:, 0]]), 1)
        total = votes.sum(1)
        top = votes.argmax(1)
        change = (votes[np.arange(len(labels)), top] >= total * 0.7) & (top != labels)
        labels = np.where(change, top, labels)
    return labels


def fill_hidden(points, out):
    """Lo que ningún mapa ve: el espejo (casi todos estos objetos son simétricos) o el visible más cercano."""
    size = float(np.ptp(points, 0).max())
    vis_idx = np.nonzero(out >= 0)[0]
    tree = kdtree.KDTree(len(vis_idx))
    for k, i in enumerate(vis_idx):
        tree.insert(points[i], k)
    tree.balance()
    res = out.copy()
    for i in np.nonzero(out < 0)[0]:
        for mirror in ((1, -1, 1), (-1, 1, 1), (-1, -1, 1), (1, 1, 1)):
            _, k, d = tree.find(points[i] * np.array(mirror))
            if d < size * 0.012 or mirror == (1, 1, 1):
                res[i] = out[vis_idx[k]]
                break
    return res


def bake_texture(low, points, labels, keys, size):
    """Textura del modelo ligero: cada píxel de la UV toma el material del punto detallado más cercano a
    su posición en 3D. Alfa: 1 madera, 0,7 lo demás."""
    tree = kdtree.KDTree(len(points))
    for i, p in enumerate(points):
        tree.insert(p, i)
    tree.balance()
    final = np.array([MATERIALES[k][1] for k in keys], np.float32)
    wood = np.array([MATERIALES[k][2] for k in keys])
    tex = np.zeros((size, size, 4), np.float32)
    filled = np.zeros((size, size), bool)
    me = low.data
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data
    co = np.array([v.co for v in me.vertices])
    for tri in me.loop_triangles:
        t = np.array([uv[li].uv for li in tri.loops]) * size - 0.5
        p3 = co[list(tri.vertices)]
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1, size - 1) + 1), np.arange(max(y0, 0), min(y1, size - 1) + 1))
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
            _, k, _ = tree.find(bw @ p3)
            lab = labels[k]
            tex[py, px, :3] = final[lab]
            tex[py, px, 3] = 1.0 if wood[lab] else 0.7
            filled[py, px] = True
    # Margen: se extiende el color a los píxeles vecinos vacíos (para que no se vean costuras).
    for _ in range(64):                          # Hasta llenar todo el espacio vacío.
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


def main():
    name = sys.argv[sys.argv.index("--") + 1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    high = load(name)
    clean(high, base(name) in CONSERVAR_TROZOS)
    place(high, name)
    decimate(high, 200000)                        # Detalle de sobra para pintar y hornear.
    points = np.array([v.co for v in high.data.vertices])
    normals = np.array([v.normal for v in high.data.vertices])
    res = 256
    best_label = np.full(len(points), -1)
    best_facing = np.zeros(len(points))
    for path in map_files(name):
        # Cada mapa se encaja por separado (giro, altura y espejo): Gemini no respeta el encuadre exacto.
        fits = []
        for flip in (False, True):
            labels_img, mask, keys = material_map(path, res, flip)
            (iou, yaw, elev), box = fit_camera(points, mask, res)
            fits.append((iou, flip, yaw, elev, box, labels_img, mask))
        iou, flip, yaw, elev, box, labels_img, mask = max(fits, key=lambda f: f[0])
        if iou < 0.8:
            print(f"  descartado {os.path.basename(path)}: encaje {iou:.2f}", flush=True)
            continue
        lab, facing = view_labels(points, normals, labels_img, mask, box, yaw, elev, res)
        better = facing > best_facing
        best_label[better] = lab[better]
        best_facing[better] = facing[better]
        print(f"  {os.path.basename(path)}: encaje {iou:.2f}{' (espejo)' if flip else ''}, giro {math.degrees(yaw):.0f}, "
              f"altura {math.degrees(elev):.0f}, ve {(lab >= 0).mean():.0%}", flush=True)
    seen = (best_label >= 0).mean()
    labels = clean_spots(high.data, fill_hidden(points, best_label))
    counts = {k: int((labels == i).sum()) for i, k in enumerate(keys)}
    print(f"MATERIALES {name}: vistos {seen:.0%}, {counts}", flush=True)

    # Copia ligera con UV y su material con la textura horneada.
    low = high.copy()
    low.data = high.data.copy()
    bpy.context.scene.collection.objects.link(low)
    low.name = name
    low.data.name = name
    for a in list(low.data.color_attributes):
        low.data.color_attributes.remove(a)
    decimate(low, TRIANGULOS.get(base(name), TRIANGULOS_POR_DEFECTO))
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.04)
    bpy.ops.object.mode_set(mode="OBJECT")
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    tex = nodes.new("ShaderNodeTexImage")
    tex.name = "Textura"
    low.data.materials.clear()
    low.data.materials.append(mat)

    texels = bake_texture(low, points, labels, keys, TEXTURA)
    color_img = bpy.data.images.new(name + "_color", TEXTURA, TEXTURA, alpha=True)
    color_img.colorspace_settings.name = "sRGB"
    color_img.pixels[:] = texels.ravel()          # Los colores ya están en sRGB (como en MATERIALES).
    color_img.pack()
    tex.image = color_img
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    mat.node_tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    for p in low.data.polygons:
        p.use_smooth = True

    bpy.data.objects.remove(high)
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    low.name = name                               # Ya sin el detallado, que tenía el nombre.
    low.data.name = name
    path = os.path.join(OUT, name + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("PINTADO", name, "->", path, "triangulos", sum(len(p.vertices) - 2 for p in low.data.polygons), flush=True)


main()
