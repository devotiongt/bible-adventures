"""Pinta un personaje generado (solo forma, Hunyuan3D) con los colores de su hoja de giro, por partes, y lo
deja con una textura limpia.

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/pintar_personaje.py -- \\
        <modelo.glb> <nombre> <altura_m> <salida.glb> [carpeta_renders]

Las vistas recortadas de la hoja van en referencias/vistas_personajes/<nombre>_{frente,lado,espalda,
tres_cuartos}.png (cada una justa a la figura). Pasos:
1. Limpia la malla (quita trozos sueltos), la pone de pie a su altura, centrada y mirando a -Y.
2. Cada vista se encaja con la silueta del modelo (giro de la cámara) y se proyecta sobre el modelo
   detallado. Con un búfer de profundidad, cada punto solo toma color de las vistas que lo ven de verdad
   (sin nada delante); el lado y los tres cuartos se usan también en espejo para el otro costado.
3. El color de cada vista se lleva a la parte más parecida de PARTES (varios tonos de muestra por parte,
   para que la sombra del dibujo no cambie la parte), entre las que permite la zona del cuerpo; algunas
   partes van por posición (manos, suela, nuca). Cada vista vota con el peso de cuánto ve el punto de
   frente, y gana la parte con más votos.
4. Lo que ninguna vista ve toma la parte del punto visto más cercano; luego se quitan manchas sueltas
   (cada punto toma la parte de la mayoría de sus vecinos).
5. Copia ligera con UV: cada píxel de la textura toma el color de la parte del punto detallado más
   cercano. Así los bordes entre partes quedan nítidos con pocos triángulos.
"""

import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector, kdtree

ROOT = os.getcwd()
_ns = {"__name__": "procesar_generados"}
exec(open(os.path.join(ROOT, "herramientas/blender/procesar_generados.py"), encoding="utf-8").read()
     .replace("\nmain()\n", "\n"), _ns)
_project, _to_pixels = _ns["_project"], _ns["_to_pixels"]

DETALLE = 160000            # Caras del modelo detallado (para pintar).
CARAS = 12000               # Caras del modelo del juego.
TEXTURA = 1024
RES = 512                   # Resolución de cada vista al proyectar.
PLIEGUE = 0.3               # Ángulo (rad) de un pliegue hacia dentro que separa parches.
PEQUENAS = ["ojo", "pelo", "faja"]
MAYORIA = 0.6               # Parte de un parche que tiene que tener una parte para pintarlo entero.

# Partes: color final (sRGB) y tonos de muestra tomados de la hoja (sRGB 0-255).
PARTES = {
    "piel": ((0.93, 0.71, 0.60), [(214, 159, 128), (232, 182, 152), (196, 140, 112)]),
    "pelo": ((0.70, 0.70, 0.72), [(165, 165, 168), (140, 140, 146), (196, 196, 199)]),
    "panuelo": ((0.92, 0.87, 0.74), [(219, 205, 179), (187, 173, 153), (240, 232, 212)]),
    "ojo": ((0.20, 0.15, 0.13), [(60, 45, 40), (40, 30, 28)]),
    "vestido": ((0.71, 0.50, 0.47), [(177, 127, 112), (157, 109, 90), (130, 88, 72)]),
    "sobretunica": ((0.55, 0.62, 0.50), [(147, 146, 124), (123, 127, 105), (91, 94, 81), (165, 168, 145)]),
    "faja": ((0.80, 0.60, 0.30), [(200, 150, 70), (170, 120, 50), (222, 176, 96)]),
    "sandalia": ((0.55, 0.38, 0.25), [(150, 100, 60), (110, 72, 45), (175, 125, 85)]),
}
NAMES = list(PARTES)
# Mapa de partes de Gemini (referencias/PROMPTS.md, n.º 21): la misma hoja con un color puro por parte.
# Si existe (referencias/vistas_personajes/<nombre>_partes_<vista>.png), se usa en vez de adivinar la parte
# por el color sombreado del dibujo, y sobran las reglas por zona.
PLANOS = {"piel": (255, 128, 0), "pelo": (128, 128, 128), "panuelo": (255, 255, 0), "ojo": (0, 0, 0),
          "vestido": (255, 0, 0), "sobretunica": (0, 255, 0), "faja": (0, 0, 255), "sandalia": (139, 69, 19)}
PUREZA = 3 * 45 ** 2        # Distancia máxima (al cuadrado) a un color puro para contar el píxel.
# Partes posibles por altura (fracción de la altura del personaje).
ZONAS = [(0.0, 0.06, ["piel", "sandalia"]),
         (0.06, 0.62, ["vestido", "sobretunica", "faja"]),
         (0.62, 0.71, ["panuelo", "sobretunica", "vestido"]),
         (0.71, 1.01, ["piel", "pelo", "panuelo", "ojo"])]
# Partes que van por posición: las manos (lejos del centro, en fracción del medio ancho, y por debajo del
# puño), la suela de las sandalias, y la nuca y los lados de la cabeza (lo que no mira al frente).
MANOS = (0.62, 0.28, 0.40)
PUNOS = (0.40, 0.5)             # Puños de las mangas, sobre las manos: del color del vestido.
SUELA = 0.02
NUCA = -0.25
# La faja: su banda a la cintura (alturas, ancho) y el nudo colgando en el centro (alturas, ancho).
FAJA = ((0.42, 0.53, 0.62), (0.28, 0.53, 0.2))
OJOS = (0.82, 0.9)
# El pelo solo asoma en la frente: alturas, ancho (fracción del medio ancho) y cuánto mira al frente.
PELO = (0.87, 0.95, 0.42, -0.6)
# Vistas de la hoja: giro esperado de la cámara (grados) y si también se usan en espejo.
VISTAS = {"frente": (0, False), "lado": (90, True), "espalda": (180, False), "tres_cuartos": (35, True)}


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
    mod = obj.modifiers.new("Reducir", "DECIMATE")
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
    decimate(obj, DETALLE)
    for p in obj.data.polygons:
        p.use_smooth = True


def load_view(name, kind, flip):
    img = bpy.data.images.load(os.path.join(ROOT, "referencias/vistas_personajes", f"{name}_{kind}.png"))
    img.scale(RES, RES)
    px = np.array(img.pixels[:], np.float32).reshape(RES, RES, 4)[::-1, :, :3] * 255
    bpy.data.images.remove(img)
    if flip:
        px = px[:, ::-1]
    mask = px.min(-1) < 232
    rows, cols = np.nonzero(mask)
    return px, mask, (cols.min(), rows.min(), cols.max(), rows.max())


def fit_yaw(points, mask, box, around):
    """Giro de la cámara (cerca del esperado) con el que la silueta del modelo encaja mejor con la vista."""
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
    """Parte fija por posición (o None) y partes permitidas por color para un punto."""
    zf = p[2] / height
    xf = abs(p[0] - (lo[0] + hi[0]) / 2) / ((hi[0] - lo[0]) / 2)
    if xf > MANOS[0] and MANOS[1] < zf < MANOS[2]:
        return "piel", None
    if zf < SUELA:
        return "sandalia", None
    if zf >= 0.7 and normal[1] > NUCA:
        return "panuelo", None
    allowed = next(z[2] for z in ZONAS if z[0] <= zf < z[1])
    if not any(z0 < zf < z1 and xf < w for z0, z1, w in FAJA):
        allowed = [a for a in allowed if a != "faja"]
    if not OJOS[0] < zf < OJOS[1]:
        allowed = [a for a in allowed if a != "ojo"]
    if not (PELO[0] < zf < PELO[1] and xf < PELO[2] and normal[1] < PELO[3]):
        allowed = [a for a in allowed if a != "pelo"]
    if xf > MANOS[0] and PUNOS[0] <= zf < PUNOS[1]:
        allowed = ["vestido"]
    return None, allowed


def label_points(obj, name, height):
    me = obj.data
    points = np.array([v.co for v in me.vertices])
    normals = np.array([v.normal for v in me.vertices])
    lo, hi = points.min(0), points.max(0)
    size = float(np.ptp(points, 0).max())
    votes = np.zeros((len(points), len(NAMES)))
    rules = [allowed_parts(p, lo, hi, height, n) for p, n in zip(points, normals)]
    protos = [(NAMES.index(n), np.array(c, float)) for n, (_, cs) in PARTES.items() for c in cs]
    flat = os.path.exists(os.path.join(ROOT, "referencias/vistas_personajes", f"{name}_partes_frente.png"))
    flat_cols = np.array([PLANOS[n] for n in NAMES], float)
    for kind, (around, mirrored) in VISTAS.items():
        for flip in ((False, True) if mirrored else (False,)):
            px, mask, box = load_view(name + "_partes" if flat else name, kind, flip)
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
            weight = 1.5 if kind == "frente" else 1.0      # La de frente es la que sale del modelo.
            if flat:
                vis = np.nonzero(visible)[0]
                cols = px[r[vis], c[vis]]
                dist = ((cols[:, None, :] - flat_cols[None]) ** 2).sum(-1)
                part = dist.argmin(1)
                # Fuera los píxeles del borde entre dos partes (mezcla de colores) y los colores que no
                # caben en su sitio: el café de la sandalia lejos de los pies, el negro de los ojos lejos de
                # la cara.
                zf = points[vis, 2] / height
                ok = dist[np.arange(len(vis)), part] < PUREZA
                ok &= (part != NAMES.index("sandalia")) | (zf < 0.08)
                ok &= (part != NAMES.index("ojo")) | ((zf > OJOS[0]) & (zf < OJOS[1]))
                np.add.at(votes, (vis[ok], part[ok]), weight * facing[vis[ok]] ** 2)
                print(f"  vista {kind}{' (espejo)' if flip else ''}: giro {math.degrees(yaw):.0f}, encaje {iou:.2f}, "
                      f"ve {visible.mean():.0%} (mapa de partes)", flush=True)
                continue
            for i in np.nonzero(visible)[0]:
                if rules[i][0]:
                    continue
                col = px[r[i], c[i]]
                best = min((np.sum((col - pc) ** 2), k) for k, pc in protos if NAMES[k] in rules[i][1])
                # La faja es fina y la sombra del dibujo la confunde con el vestido: donde puede haber faja,
                # su voto vale doble.
                boost = 2.0 if NAMES[best[1]] == "faja" else 1.0
                votes[i, best[1]] += weight * boost * facing[i] ** 2
            print(f"  vista {kind}{' (espejo)' if flip else ''}: giro {math.degrees(yaw):.0f}, encaje {iou:.2f}, "
                  f"ve {visible.mean():.0%}", flush=True)
    labels = votes.argmax(1)
    labels[votes.sum(1) == 0] = -1
    for i, (fixed, _) in enumerate(rules):
        if fixed and not flat:
            labels[i] = NAMES.index(fixed)
    # Lo que no ve ninguna vista: la parte del punto con parte más cercano.
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
    """Parte la superficie en parches por sus pliegues hacia dentro (donde la sobretúnica pisa el vestido,
    el pañuelo enmarca la cara, el puño se junta con la mano) y da a cada parche la parte de la mayoría de
    sus caras, si es una mayoría clara. Así los bordes siguen la forma de la ropa y no quedan motas.
    Devuelve el centro y la parte de cada cara."""
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
                if len(e.link_faces) != 2 or e.calc_face_angle_signed(0.0) < -PLIEGUE:
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
    clear = votes[np.arange(count), top] >= votes.sum(1) * MAYORIA
    feet = centers[:, 2] < centers[:, 2].max() * 0.06       # Los pies, por color: dedos y tiras de la sandalia.
    small = np.isin(flab, [NAMES.index(n) for n in PEQUENAS])  # Ojos, pelo y faja: no se los come un parche.
    out = np.where(clear[patch] & ~feet & ~small, top[patch], flab)
    print(f"  parches {count}, con mayoría clara {clear.mean():.0%}, caras cambiadas {(out != flab).mean():.1%}",
          flush=True)
    return centers, out


def bake_texture(low, points, labels):
    tree = kdtree.KDTree(len(points))
    for i, p in enumerate(points):
        tree.insert(p, i)
    tree.balance()
    final = np.array([PARTES[n][0] for n in NAMES], np.float32)
    tex = np.zeros((TEXTURA, TEXTURA, 4), np.float32)
    filled = np.zeros((TEXTURA, TEXTURA), bool)
    me = low.data
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data
    co = np.array([v.co for v in me.vertices])
    for tri in me.loop_triangles:
        t = np.array([uv[li].uv for li in tri.loops]) * TEXTURA - 0.5
        p3 = co[list(tri.vertices)]
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        xs, ys = np.meshgrid(np.arange(max(x0, 0), min(x1, TEXTURA - 1) + 1),
                             np.arange(max(y0, 0), min(y1, TEXTURA - 1) + 1))
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
    for _ in range(64):                             # Margen alrededor de cada isla de la UV.
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
    decimate(low, CARAS)
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    img = bpy.data.images.new(name + "_color", TEXTURA, TEXTURA, alpha=True)
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
    for k, ang in (("frente", 0), ("lado", 90), ("espalda", 180), ("tres_cuartos", 35)):
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
    print("PARTES", {n: int(counts[i]) for i, n in enumerate(NAMES)}, flush=True)
    low = make_low(high, name, points, labels)
    print("CARAS", len(low.data.polygons), "MEDIDAS", tuple(round(v, 3) for v in low.dimensions))
    if len(args) > 4:
        render(low, args[4], name)
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_yup=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.splitext(out)[0] + ".blend")


main()
