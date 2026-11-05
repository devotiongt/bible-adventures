"""Procesa los objetos generados con Hunyuan3D (herramientas/blender/generados/*.glb) para el juego.

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/procesar_generados.py -- \\
        assets/aldea/generados.glb [nombre ...]

Para cada objeto:
1. Limpia: une vértices repetidos y quita los trozos sueltos que flotan (artefactos del generador).
2. Lo deja de pie en el suelo, centrado, con la fachada hacia -Y (en Godot, +Z) y a su tamaño real
   (TAMANOS, en metros, contra Noé de 1,55 m).
3. Lo reduce a un número de triángulos razonable para el juego (TRIANGULOS).
4. Lo pinta con los colores de su recorte (referencias/recortes/<nombre>.png): busca el ángulo de
   cámara desde el que la silueta del modelo coincide con la del dibujo y proyecta los colores desde
   ahí; las partes que no se ven en el dibujo toman el color de la parte visible más cercana.
Todos los objetos se exportan juntos en un solo .glb, cada uno con su nombre.
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
SRC = os.environ.get("GENERADOS_DIR", os.path.join(ROOT, "herramientas/blender/generados"))
CUTS = os.path.join(ROOT, "referencias/recortes")

# Tamaño real: ("alto" | "ancho", metros). "ancho" es la medida horizontal mayor.
TAMANOS = {
    "pozo": ("alto", 2.1), "horno": ("alto", 0.95), "cantaros": ("ancho", 1.0),
    "cestas": ("ancho", 0.9), "sacos": ("ancho", 1.0),
    "telar": ("alto", 1.55), "tendedero": ("ancho", 2.8), "banco": ("ancho", 1.5),
    "troncos_asiento": ("ancho", 1.1), "mesa": ("ancho", 2.0), "cerca": ("ancho", 2.1),
    "abrevadero": ("ancho", 1.8), "lena": ("ancho", 1.1), "fogata": ("ancho", 1.4), "bancal": ("ancho", 2.0),
    # Piezas para armar los puestos (armar_puestos.py): el puesto vacío y su mercancía.
    "puesto_vacio": ("alto", 2.3), "rollos_crema": ("ancho", 0.75), "rollos_colores": ("ancho", 0.7),
    "telas_dobladas": ("ancho", 0.6), "caja_manzanas": ("ancho", 0.55), "caja_naranjas": ("ancho", 0.55),
    "caja_peras": ("ancho", 0.55), "caja_uvas": ("ancho", 0.55),
    "fruta_manzanas": ("ancho", 0.45), "fruta_naranjas": ("ancho", 0.45), "fruta_peras": ("ancho", 0.45),
    "fruta_uvas": ("ancho", 0.45),
    # Piezas de la fogata (armar_fogata.py): el anillo de piedras con su ceniza y los troncos en tipi.
    "fogata_piedras": ("ancho", 1.3), "fogata_troncos": ("alto", 0.5),
}
# Mercancía: lo que no es madera va sin veta (alfa 0,7 en el color de vértice).
SIN_VETA = {"rollos_crema", "rollos_colores", "telas_dobladas", "caja_manzanas", "caja_naranjas", "caja_peras",
            "caja_uvas", "cantaros", "fruta_manzanas", "fruta_naranjas", "fruta_peras", "fruta_uvas"}
# Triángulos finales: los que se repiten mucho (cerca) más ligeros; los de la plaza, con más detalle.
TRIANGULOS = {"cerca": 1500, "lena": 3000, "troncos_asiento": 2000, "sacos": 4000, "cestas": 5000,
              "cantaros": 5000, "pozo": 9000, "telar": 7000, "bancal": 7000, "puesto_vacio": 10000,
              "rollos_crema": 2500, "rollos_colores": 2500, "telas_dobladas": 3000, "caja_manzanas": 3500,
              "caja_naranjas": 3500, "caja_peras": 3500, "caja_uvas": 3500, "fruta_manzanas": 14000,
              "fruta_naranjas": 12000, "fruta_peras": 14000, "fruta_uvas": 14000,   # Fruta: más, si no se pierden los tallos.
              "fogata_piedras": 6000, "fogata_troncos": 3000}
TRIANGULOS_POR_DEFECTO = 6000
# Cuántos colores principales tiene cada dibujo (por defecto, 5).
# Los de un solo material llevan un único color limpio (la luz del juego les da el volumen).
PALETAS = {"horno": 1, "banco": 1, "mesa": 1, "cerca": 1, "lena": 1, "troncos_asiento": 1, "sacos": 1,
           "cantaros": 1, "abrevadero": 2, "pozo": 4, "fogata": 4, "cestas": 6, "puesto_frutas": 6, "bancal": 4,
           "telar": 4, "tendedero": 5, "puesto_vacio": 3, "rollos_crema": 1, "rollos_colores": 2,
           "telas_dobladas": 4, "caja_manzanas": 3, "caja_naranjas": 3, "caja_peras": 3, "caja_uvas": 3, "fruta_manzanas": 4,
           "fruta_naranjas": 4, "fruta_peras": 4, "fruta_uvas": 4,
           "fogata_piedras": 1, "fogata_troncos": 1}


def base(name):
    """Nombre del objeto sin el sufijo de versión (banco_v42 → banco): para medidas, colores y recorte."""
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


# Trozos sueltos a conservar aunque sean pequeños: las llamas de la fogata son piezas aparte.
CONSERVAR_TROZOS = {"fogata"}


def clean(obj, keep_islands=False):
    """Une vértices repetidos y quita los trozos sueltos pequeños (< 0,4 % de las caras)."""
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
    """De pie en el suelo, centrado y a su tamaño real."""
    co = np.array([v.co for v in obj.data.vertices])
    lo, hi = co.min(0), co.max(0)
    kind, meters = TAMANOS[base(name)]
    size = (hi[2] - lo[2]) if kind == "alto" else max(hi[0] - lo[0], hi[1] - lo[1])
    s = meters / size
    offset = Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
    for v in obj.data.vertices:
        v.co = (v.co + offset) * s


def decimate(obj, target):
    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    if tris > target:
        mod = obj.modifiers.new("Reducir", "DECIMATE")
        mod.ratio = target / tris
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)


def _cut_mask(name, res):
    """Recorte del dibujo: colores (lineales, 0-1) y máscara de lo que no es fondo blanco, a res × res."""
    img = bpy.data.images.load(os.path.join(CUTS, base(name) + ".png"))
    img.scale(res, res)
    px = np.array(img.pixels[:], np.float32).reshape(res, res, 4)[::-1, :, :3]   # Fila 0 arriba.
    bpy.data.images.remove(img)
    srgb = px                                        # Blender da los píxeles del PNG en sRGB.
    mask = (np.abs(srgb - 1.0).sum(-1) > 0.12)
    return srgb, mask


def _project(points, yaw, elev):
    """Proyección ortográfica desde una cámara girada `yaw` y elevada `elev` (radianes), mirando a +Y."""
    d = np.array([math.sin(yaw) * math.cos(elev), math.cos(yaw) * math.cos(elev), -math.sin(elev)])
    r = np.array([math.cos(yaw), -math.sin(yaw), 0.0])
    u = np.cross(r, d)
    return points @ r, points @ u, points @ d


def _to_pixels(x, y, res, box):
    """Lleva la caja proyectada del modelo a la caja de la silueta del dibujo (en píxeles)."""
    (x0, x1), (y0, y1) = (x.min(), x.max()), (y.min(), y.max())
    c0, r0, c1, r1 = box
    col = c0 + (x - x0) / max(x1 - x0, 1e-6) * (c1 - c0)
    row = r1 - (y - y0) / max(y1 - y0, 1e-6) * (r1 - r0)
    return np.clip(col.round().astype(int), 0, res - 1), np.clip(row.round().astype(int), 0, res - 1)


def _features(rgb):
    """Rasgos para agrupar colores: sobre todo el tono (rgb normalizado), poco el brillo. Así la cara
    en sombra y la iluminada de una misma pieza caen en el mismo grupo."""
    s = rgb.sum(-1, keepdims=True) + 1e-4
    return np.concatenate([rgb / s * 3.0, s * 0.12], -1)


def _palette(pixels, k, iters=14):
    """Colores principales (k-medias por tono) de los píxeles del dibujo. Cada color se toma de la
    mitad más clara de sus píxeles: la cara iluminada, sin la sombra pintada."""
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
    """Cada vértice toma el color que más tienen sus vecinos: quita motas sueltas."""
    edges = np.array([e.vertices[:] for e in obj.data.edges])
    for _ in range(rounds):
        votes = np.zeros((len(labels), k))
        np.add.at(votes, (edges[:, 0], labels[edges[:, 1]]), 1)
        np.add.at(votes, (edges[:, 1], labels[edges[:, 0]]), 1)
        np.add.at(votes, (np.arange(len(labels)), labels), 1.5)
        labels = votes.argmax(1)
    return labels


# Telas dobladas, de arriba abajo (sRGB, de referencias/mercado_piezas.png).
CAPAS_TELA = [(0.42, 0.58, 0.82), (0.27, 0.62, 0.62), (0.88, 0.66, 0.25)]
MADERA_CAJA = (0.62, 0.40, 0.24)


def _cavity(obj):
    """Concavidad por vértice (0 plano, > 0 hundido): cuánto se hunde respecto a sus vecinos. Sirve para
    oscurecer los huecos entre frutas o las juntas entre piedras."""
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


# Pozo, por zonas (medidas del modelo en metros): base empedrada, brocal de piedra, postes y travesaño
# de madera, la cuerda y el agua.
PIEDRA_BASE = (0.64, 0.62, 0.59)
PIEDRA = (0.56, 0.55, 0.54)
CUERDA = (0.72, 0.57, 0.37)
AGUA = (0.20, 0.27, 0.32)


def _well_colors(obj, centers):
    out = np.zeros((len(centers), 3), np.float32)
    alpha = np.full(len(centers), 0.7, np.float32)
    wood = np.array(MADERA_CAJA)
    nrm = np.array([f.normal for f in obj.data.polygons])
    for i, (x, y, z) in enumerate(centers):
        r = np.hypot(x, y)
        # Postes: se ensanchan abajo, por eso el margen en y; la cara de dentro del poste mira al centro.
        inward = nrm[i][0] * np.sign(x) < -0.3
        # Fuera del brocal (|x| > 0,75 nunca es piedra salvo la base) todo es poste.
        side = abs(nrm[i][1]) > 0.7                   # Costados del poste (miran hacia delante o atrás).
        post = z > 0.22 and ((abs(x) > 0.75 and abs(y) < 0.5) or (abs(x) > 0.6 and abs(y) < 0.4 and (inward or side)))
        # Cuerda: solo el tramo que baja (por encima del asa del cubo) y la vuelta en el travesaño.
        rope = (abs(x) < 0.08 and abs(y) < 0.08 and 1.28 < z < 1.58) or (abs(x) < 0.2 and 1.58 < z < 1.82)
        bucket = r < 0.32 and z > 0.7 and (nrm[i][0] * x + nrm[i][1] * y) >= 0
        if rope:
            out[i] = CUERDA
        elif post or bucket or z > 0.95:
            out[i], alpha[i] = wood, 1.0          # Postes, travesaño, manivela y cubo: madera (con veta).
        elif z < 0.2:
            out[i] = PIEDRA_BASE
        elif r < 0.5 and z < 0.86 and (nrm[i][0] * x + nrm[i][1] * y) < 0:
            out[i] = AGUA if z < 0.5 else np.array(PIEDRA) * 0.75    # Dentro del pozo.
        else:
            out[i] = PIEDRA
    cav = _cavity(obj)
    for f in obj.data.polygons:
        if alpha[f.index] < 1.0:
            out[f.index] *= 1.0 - np.clip(cav[list(f.vertices)].mean() * 2.5, 0.0, 0.5)   # Juntas.
    return out, alpha


TALLO = (0.40, 0.25, 0.13)
HOJA = (0.36, 0.62, 0.20)


def _fruit_colors(obj, name, face_col, palette):
    """Montón de fruta: la fruta de su color limpio, los tallos café y las hojitas verdes (según el dibujo),
    y los huecos entre fruta y fruta más oscuros, para que cada una se distinga."""
    fruit = np.array(COLOR_FRUTA[base(name)], np.float32)

    def chroma(c):
        c = np.asarray(c, np.float32)
        return c / (c.sum(-1, keepdims=True) + 1e-4)
    # Cada grupo de color del dibujo es fruta, tallo u hoja según su tono (sin contar el brillo: la
    # fruta en sombra sigue siendo fruta). Solo es tallo u hoja si su tono está claramente más cerca.
    kinds = []
    for c in palette:
        d_fruit = np.abs(chroma(c) - chroma(fruit)).sum()
        d_stem = np.abs(chroma(c) - chroma(TALLO)).sum()
        d_leaf = np.abs(chroma(c) - chroma(HOJA)).sum()
        if base(name) != "fruta_peras" and d_leaf < d_fruit * 0.6 and d_leaf < d_stem:
            kinds.append(HOJA)
        elif d_stem < d_fruit * 0.5 and c.sum() < fruit.sum() * 0.9:
            kinds.append(TALLO)
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
    """Mercancía de los puestos, por zonas en vez de proyectar el dibujo (salía en parches):
    - Cajas: la fruta (lo alto de dentro) de un solo color, el más saturado de la parte de arriba del
      dibujo; lo demás, madera.
    - Telas dobladas: cada capa (por altura) de su color."""
    z = centers[:, 2]
    h0, h1 = z.min(), z.max()
    out = face_col.copy()
    if kind == "telas_dobladas":
        band = np.clip(((h1 - z) / max(h1 - h0, 1e-6) * 3).astype(int), 0, 2)
        out[:] = np.array(CAPAS_TELA)[band]
        return out
    rows = np.nonzero(inner.any(1))[0]
    cols = np.nonzero(inner.any(0))[0]
    hgt, wid = rows[-1] - rows[0], cols[-1] - cols[0]
    top = inner.copy()
    top[rows[0] + hgt // 2:] = False
    top[:, : cols[0] + wid // 4] = False
    top[:, cols[-1] - wid // 4:] = False
    wood = np.array(MADERA_CAJA)
    cands = _palette(colors[top], 3)
    # La fruta: el color de arriba que más se aleja de la madera (y algo saturado).
    fruit = cands[np.argmax(((cands - wood) ** 2).sum(1) + (cands.max(1) - cands.min(1)) * 0.3)]
    xy = np.abs(centers[:, :2]) / np.maximum(np.abs(centers[:, :2]).max(0), 1e-6)
    is_fruit = (z > h0 + (h1 - h0) * 0.4) & (xy < 0.8).all(1)   # La misma zona que quita _fill_fruit.
    # Fruta algo más clara y viva que en el dibujo (allí tiene sus sombras pintadas).
    lum = fruit.mean()
    fruit = np.clip((lum + (fruit - lum) * 1.25) * 1.2, 0.0, 1.0)
    out[:] = wood
    out[is_fruit] = fruit
    return out


# Montón de fruta generado aparte que va dentro de cada caja (la fruta de la caja generada sale como un bulto).
# Color de cada montón de fruta (sRGB): uno solo y limpio; la luz del juego le da el volumen.
COLOR_FRUTA = {"fruta_manzanas": (0.86, 0.18, 0.16), "fruta_naranjas": (0.98, 0.55, 0.12),
               "fruta_peras": (0.62, 0.80, 0.24), "fruta_uvas": (0.50, 0.24, 0.62)}
FRUTA = {"caja_manzanas": "fruta_manzanas", "caja_naranjas": "fruta_naranjas", "caja_peras": "fruta_peras",
         "caja_uvas": "fruta_uvas"}


# Tallos: (frutas a lo ancho del montón, color, largo en m). En el dibujo son finos y se pierden al
# reducir el modelo, así que se ponen aparte en lo alto de cada fruta.
TALLOS = {"fruta_manzanas": (6, (0.40, 0.25, 0.13), 0.035), "fruta_naranjas": (6, (0.30, 0.50, 0.18), 0.012),
          "fruta_peras": (7, (0.40, 0.25, 0.13), 0.04), "fruta_uvas": (6, (0.30, 0.50, 0.18), 0.03)}


def _colored(fill, color, alpha=0.7):
    """Objeto con la geometría que crea fill(bm) y un solo color (atributo "Color", por esquina)."""
    me = bpy.data.meshes.new("pieza")
    bm = bmesh.new()
    fill(bm)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("pieza", me)
    bpy.context.scene.collection.objects.link(obj)
    attr = me.color_attributes.new("Color", "BYTE_COLOR", "CORNER")
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color]
    for d in attr.data:
        d.color = (lin[0], lin[1], lin[2], alpha)
    return obj


def _stems(mound, kind, fruit_size):
    """Un tallito en la cima de cada fruta: los vértices más altos de su vecindario (radio de media fruta)."""
    _, color, length = TALLOS[kind]
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
    """Quita el bulto de fruta de la caja y mete el montón de fruta generado aparte
    (referencias/fruta_montones.png → generados/fruta_<tipo>.glb): ajustado al hueco de la caja, con la
    base en el fondo y la parte de arriba a ras del borde."""
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
    mound = _prepare(FRUTA[base(name)])
    mco = np.array([v.co for v in mound.data.vertices])
    mlo, mhi = mco.min(0), mco.max(0)
    floor_z = h0 + (h1 - h0) * 0.12
    rim = h1 + (h1 - h0) * 0.06                     # La fruta de arriba asoma un poco.
    target = np.array([xh * 1.58, yh * 1.58, rim - floor_z])
    size = mhi - mlo
    # El montón, girado si hace falta para que su lado largo vaya con el de la caja.
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
    stems = _stems(mound, FRUTA[base(name)], xh * 1.58 / TALLOS[FRUTA[base(name)]][0])
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
    """Puesto del mercado (el vacío, que luego arma armar_puestos.py), por zonas (alturas sobre el suelo, como fracción de la altura total):
    - Toldo (> 0,70, salvo los postes): su color fuerte y alfa 0; el shader le dibuja las rayas con el
      crema, rectas.
    - Postes de las esquinas y lo que queda bajo el mostrador (< 0,30): madera.
    - Mercancía (entre 0,30 y 0,70): colores del mostrador del dibujo (su propia paleta), una pieza de
      un color, suavizado entre caras vecinas; alfa 0,7 para que el shader no le ponga veta (salvo lo
      que es de madera, como las cajas de fruta)."""
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
    # En el toldo solo se excluye la punta redonda de cada poste.
    # Solo el remate redondo de cada poste (en las esquinas de delante y de atrás); el faldón que cuelga
    # por los lados es tela.
    post_tip = ((np.abs(x) > np.abs(x).max() * 0.85) & (np.abs(y) > np.abs(y).max() * 0.6)
                & (z < h0 + (h1 - h0) * 0.78))
    cloth = (z > h0 + (h1 - h0) * 0.70) & ~post_tip
    goods = (z > h0 + (h1 - h0) * 0.30) & ~cloth & ~corner

    # Mercancía: color de muestra de cada vértice → el más cercano de la paleta del mostrador.
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
    # El puesto es el vacío: lo que hay bajo el toldo es madera (la mercancía la pone armar_puestos.py).
    return out, alpha


def paint(obj, high_points, name, res=192):
    """Pinta los vértices con los colores del recorte, desde el ángulo que mejor encaja con su silueta."""
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
    # Visibilidad: profundidad mínima por píxel con los puntos del modelo detallado.
    x, y, depth = _project(high_points, yaw, elev)
    c, r = _to_pixels(x, y, res, box)
    zbuf = np.full((res, res), np.inf)
    np.minimum.at(zbuf, (r, c), depth)
    verts = np.array([v.co for v in obj.data.vertices])
    vx, vy, vd = _project(verts, yaw, elev)
    # Los vértices del modelo reducido, con la misma caja que el detallado.
    x0, x1, y0, y1 = x.min(), x.max(), y.min(), y.max()
    c0, r0, c1, r1 = box
    vc = np.clip(np.round(c0 + (vx - x0) / (x1 - x0) * (c1 - c0)).astype(int), 0, res - 1)
    vr = np.clip(np.round(r1 - (vy - y0) / (y1 - y0) * (r1 - r0)).astype(int), 0, res - 1)
    size = float(np.ptp(high_points, 0).max())
    near = np.minimum.reduce([np.roll(np.roll(zbuf, dr, 0), dc, 1) for dr in (-1, 0, 1) for dc in (-1, 0, 1)])
    # Solo cuentan los píxeles bien dentro de la silueta (en el borde se cuela el fondo blanco).
    inner = mask.copy()
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)):
        inner &= np.roll(np.roll(mask, dr, 0), dc, 1)
    visible = (vd <= near[vr, vc] + size * 0.03) & inner[vr, vc]
    # Colores principales del dibujo: así cada parte queda de un color limpio (estilo juguete) en vez
    # de llevarse las luces y sombras pintadas.
    # En los puestos, los colores de la estructura y la mercancía salen de la parte de abajo del dibujo
    # (arriba está el toldo, que se pinta aparte a rayas).
    region = inner.copy()
    if name.startswith("puesto"):
        rows = np.nonzero(inner.any(1))[0]
        region[: rows[0] + (rows[-1] - rows[0]) * 2 // 5] = False
    palette = _palette(colors[region], PALETAS.get(base(name), 5))
    sampled = _features(colors[vr, vc])
    labels = np.argmin(((sampled[:, None, :] - _palette.centers[None]) ** 2).sum(-1), 1)
    # Lo que no se ve en el dibujo: la parte visible más cercana.
    tree = kdtree.KDTree(int(visible.sum()))
    vis_idx = np.nonzero(visible)[0]
    for k, i in enumerate(vis_idx):
        tree.insert(verts[i], k)
    tree.balance()
    for i in np.nonzero(~visible)[0]:
        _, k, _ = tree.find(verts[i])
        labels[i] = labels[vis_idx[k]]
    # En los montones de fruta no se suaviza mucho: borraría los tallitos, que son pequeños.
    labels = _smooth_labels(obj, labels, len(palette), rounds=1 if base(name) in COLOR_FRUTA else 6)
    # Un color por cara (bordes nítidos, como piezas pintadas): el que más tienen sus vértices.
    polys = obj.data.polygons
    face_col = np.zeros((len(polys), 3), np.float32)
    centers = np.zeros((len(polys), 3), np.float32)
    for f in polys:
        ids = list(f.vertices)
        face_col[f.index] = palette[np.bincount(labels[ids], minlength=len(palette)).argmax()]
        centers[f.index] = f.center
    alpha = np.ones(len(polys), np.float32)
    if name.startswith("puesto"):
        # Color de muestra de cada vértice (los ocultos, el del visible más cercano).
        sampled_rgb = colors[vr, vc].copy()
        for i in np.nonzero(~visible)[0]:
            _, k, _ = tree.find(verts[i])
            sampled_rgb[i] = sampled_rgb[vis_idx[k]]
        face_col, alpha = _paint_stall(obj, centers, colors, inner, sampled_rgb, palette)
    out = face_col
    if base(name) in COLOR_FRUTA:
        out = face_col = _fruit_colors(obj, name, face_col, palette)
    if base(name) == "pozo":
        face_col, alpha = _well_colors(obj, centers)
        out = face_col
    if base(name).startswith("caja") or base(name) == "telas_dobladas":
        out = face_col = _goods_colors(base(name), centers, face_col, colors, inner, palette)
    if base(name) in SIN_VETA:
        z = centers[:, 2]
        top = z.min() + (z.max() - z.min()) * 0.55
        xy = np.abs(centers[:, :2]) / np.maximum(np.abs(centers[:, :2]).max(0), 1e-6)
        for f in polys:
            i = f.index
            # Cajas de fruta: la fruta es lo alto y de dentro (la madera, el borde y los lados).
            fruit = base(name).startswith("caja") and z[i] > top and (xy[i] < 0.84).all()
            if not base(name).startswith("caja") or fruit or not _woodish(face_col[i]):
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
    """Cargar, limpiar, colocar a su tamaño, reducir y pintar un objeto generado."""
    obj = load(name)
    stats = clean(obj, base(name) in CONSERVAR_TROZOS)
    place(obj, name)
    high = np.array([v.co for v in obj.data.vertices])
    decimate(obj, TRIANGULOS.get(base(name), TRIANGULOS_POR_DEFECTO))
    obj["_stats"] = list(stats) + list(paint(obj, high, name))
    return obj


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = argv[0]
    names = argv[1:] or sorted(n for n in TAMANOS if os.path.exists(os.path.join(SRC, n + ".glb")))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    done = []
    for i, name in enumerate(names):
        obj = _prepare(name)
        islands, dropped, iou, yaw, elev, vis, nv = obj["_stats"]
        if base(name) in FRUTA:
            gone, added = _fill_fruit(obj, name)
            print(f"  {name}: bulto de fruta quitado ({gone} caras), montón de {added} caras", flush=True)
        for p in obj.data.polygons:
            p.use_smooth = True
        obj.location.x = i * 3.0                   # En fila, para verlos en Blender.
        tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
        print(f"OBJETO {name}: trozos {islands} (quitados {dropped}), triangulos {tris}, "
              f"medidas {tuple(round(v, 2) for v in obj.dimensions)}, encaje {iou:.2f} "
              f"(giro {yaw:.0f}, altura {elev:.0f}), vertices vistos {vis}/{nv}", flush=True)
        done.append(obj)
    bpy.ops.object.select_all(action="DESELECT")
    for o in done:
        o.select_set(True)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if os.path.isdir(out):
        # Un archivo por objeto para retocarlos a mano (herramientas/blender/objetos/<nombre>.blend);
        # luego se juntan y exportan con exportar_objetos.py.
        names = [o.name for o in done]
        tmp = os.path.join(out, "_todos.blend")
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
        print("GENERADOS OK ->", out, flush=True)
        return
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_yup=True,
                              export_vertex_color="ACTIVE")
    print("GENERADOS OK ->", out, flush=True)


main()
