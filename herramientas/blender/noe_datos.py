"""Noé reconstruido a partir de las referencias (no a ojo).

Datos de entrada, generados desde referencias/noe_giro.png:
    referencias/noe_partes.png      la hoja de giro segmentada por partes (pelo, piel, manto, manga…)
    referencias/noe_volumenes.json  cada volumen medido por alturas: ancho de la mitad delantera (vista
                                    de frente), de la trasera (vista de espalda) y fondo (vista de lado)

Cada volumen se construye sección a sección con esas medidas, y cada cara toma el color de la
parte que se ve en la vista que tiene enfrente (proyección). Así el chaleco, la túnica, la cuerda,
las mangas, la barba y el pelo quedan donde están en la referencia.

Uso:
    blender --background --factory-startup --python herramientas/blender/noe_datos.py -- assets/personajes/noe.glb [carpeta_renders]
    python3 herramientas/blender/en_vivo.py noe_datos paso_limpiar paso_volumenes paso_colores
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = globals().get("PROJECT_ROOT", os.getcwd())
REF_SHEET = os.path.join(ROOT, "referencias/noe_giro.png")
PARTS_SHEET = os.path.join(ROOT, "referencias/noe_partes.png")
VOLUMES = os.path.join(ROOT, "referencias/noe_volumenes.json")

PX = 1.55 / 478
REF_BASE_Y = 532
VIEW_X = {"frente": 165.5, "lado": 403.5, "espalda": 625.5}

# Color de cada parte en la imagen segmentada -> material.
PART_COLORS = {
    "Canas": (235, 235, 245), "Piel": (252, 212, 183), "Nariz": (235, 120, 100), "Ojo": (30, 20, 15),
    "Manto": (165, 91, 46), "Manga": (200, 174, 134), "Tunica": (221, 211, 192), "Cuerda": (94, 57, 24),
    "Sandalia": (40, 30, 25),
}
# Colores finales (paleta de referencias/paleta.png).
MATERIALS = {
    "Canas": "EFEFEF", "Piel": "FCD4B7", "Nariz": "EDA88A", "Ojo": "3A2418", "Manto": "A55B2E",
    "Manga": "C8AE86", "Tunica": "DDD3C0", "Cuerda": "5E3918", "Sandalia": "3F2A1D", "Brillo": "FFFFFF",
}
# Forma de la sección de cada volumen (2 = elipse, más = más cuadrada) y parte por defecto.
VOLUME_STYLE = {
    "cuerpo": (2.6, "Manto"), "cabeza": (2.2, "Canas"), "brazoI": (2.0, "Manga"), "brazoD": (2.0, "Manga"),
    "pieI": (2.2, "Sandalia"), "pieD": (2.2, "Sandalia"),
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
    """Ajuste suave de una curva medida: mediana (quita picos) y luego filtro gaussiano."""
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
    """Une las secciones medidas en una malla cerrada. Cada sección mezcla el ancho de la mitad
    delantera (vista de frente) con el de la trasera (vista de espalda)."""
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
        y_mid = (back - front) / 2          # Blender: delante es -Y.
        depth = (front + back) / 2
        ring = []
        for s in range(segments):
            a = math.tau * s / segments
            ca, sa = math.cos(a), math.sin(a)
            t = (1 + sa) / 2                  # 0 delante, 1 detrás.
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


# --- Lectura de la imagen segmentada ---------------------------------------------

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
    """Parte que se ve en la vista dada en el punto (x lateral, z altura), mirando un entorno 5x5."""
    w, h, px = _parts_image()
    col = VIEW_X[view] + x / PX
    row_top = REF_BASE_Y - z / PX           # Fila contada desde arriba.
    votes = {}
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            cxp, cyp = int(round(col + dx)), int(round(row_top + dy))
            if not (0 <= cxp < w and 0 <= cyp < h):
                continue
            i = ((h - 1 - cyp) * w + cxp) * 4    # Blender guarda las filas de abajo arriba.
            rgb = tuple(px[i + k] * 255 for k in range(3))
            if min(rgb) > 245:
                continue
            best = min(PART_COLORS, key=lambda k: sum((rgb[j] - PART_COLORS[k][j]) ** 2 for j in range(3)))
            votes[best] = votes.get(best, 0) + 1
    return max(votes, key=votes.get) if votes else None


# --- Medidas leídas sobre la referencia con la regla métrica (metros) ----------------
# (Blender: delante es -Y; en la vista de lado, "delante" positivo se convierte en -Y.)
M = {
    "bajo_tunica": 0.175, "bajo_manto": 0.32, "arriba_manto": 1.12, "abertura": 0.075,
    "hombro": Vector((0.24, 0.0, 1.065)), "puno": Vector((0.33, -0.01, 0.655)),
    "manga_r": (0.055, 0.074), "mano": Vector((0.35, -0.02, 0.585)), "mano_tam": (0.048, 0.034, 0.069),
    "cuerda": (0.69, 0.725), "nudo": Vector((0.012, 0.0, 0.69)), "cabos": (0.53, (-0.026, 0.03)),
    "ojo": Vector((0.076, 0.0, 1.33)), "ojo_tam": (0.012, 0.009, 0.018),
    "ceja": Vector((0.09, 0.0, 1.384)), "ceja_tam": (0.042, 0.016, 0.015),
    "nariz": Vector((0.0, -0.232, 1.29)), "nariz_tam": (0.034, 0.036, 0.036),
    "bigote": (1.225, 0.11), "oreja": Vector((0.196, -0.015, 1.32)), "oreja_tam": (0.022, 0.03, 0.04),
    "pie_x": 0.125, "pie_y": (0.1, -0.167), "pie_semiancho": 0.065, "pierna_r": 0.05,
}


# Contorno del torso leído con la regla sobre la referencia:
# (altura, semiancho de frente/espalda, fondo hacia delante, fondo hacia detrás).
TORSO_REGLA = [
    (0.175, 0.24, 0.175, 0.2), (0.25, 0.243, 0.178, 0.205), (0.32, 0.25, 0.18, 0.21), (0.42, 0.235, 0.177, 0.205),
    (0.52, 0.222, 0.172, 0.195), (0.62, 0.21, 0.165, 0.182), (0.7, 0.205, 0.165, 0.172), (0.8, 0.203, 0.155, 0.162),
    (0.9, 0.208, 0.15, 0.158), (1.0, 0.225, 0.145, 0.158), (1.07, 0.245, 0.14, 0.158), (1.12, 0.23, 0.12, 0.14),
    (1.15, 0.14, 0.08, 0.1), (1.17, 0.07, 0.05, 0.06),
]


def _torso_sections(step=0.01):
    """Secciones del torso cada centímetro, interpolando la tabla con una curva suave (Catmull-Rom)."""
    rows = TORSO_REGLA
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
    """Secciones del volumen medido entre z0 y z1, con un ajuste aún más suave (forma limpia)."""
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
    """Hace el torso simétrico de izquierda a derecha (la referencia lo es; así se quita el ruido)."""
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
    mod = obj.modifiers.new("Suave", "SUBSURF")
    mod.levels = level
    mod.render_levels = level


def _solidify(obj, t):
    mod = obj.modifiers.new("Grosor", "SOLIDIFY")
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


def paso_limpiar():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)
    global _parts
    _parts = None
    root = pivot("Noe", (0, 0, 0))
    pivot("Cuerpo", (0, 0, 0.7), root)
    _view()


def paso_ropa():
    """Túnica, sobretúnica sin mangas abierta por delante y cuerda, con el contorno medido."""
    data = json.load(open(VOLUMES))
    body = bpy.data.objects["Cuerpo"]
    outer = _torso_sections()
    # Túnica: el volumen medido, un poco por dentro donde la cubre el manto.
    inner = [dict(s, fx=[v * (0.97 if s["z"] > M["bajo_manto"] else 1.0) for v in s["fx"]],
                  bx=[v * (0.97 if s["z"] > M["bajo_manto"] else 1.0) for v in s["bx"]],
                  front=s["front"] * (0.97 if s["z"] > M["bajo_manto"] else 1.0),
                  back=s["back"] * (0.97 if s["z"] > M["bajo_manto"] else 1.0)) for s in outer]
    tunic = _mesh_from("Tunica", inner, 2.6, "Tunica")
    _subsurf(tunic)
    attach(tunic, body)
    # Sobretúnica: la piel exterior del volumen, de 0.32 a 1.12, con la abertura delantera recta.
    vest_secs = [s for s in outer if s["z"] >= M["bajo_manto"] - 0.005]
    vest = _mesh_from("Sobretunica", vest_secs, 2.6, "Manto",
                      skip=lambda c: c.y < 0 and abs(c.x) < M["abertura"] or c.z < M["bajo_manto"] + 0.001
                      or c.z > M["arriba_manto"] - 0.002)
    _solidify(vest, 0.018)
    _subsurf(vest)
    attach(vest, body)
    # Cuerda: sigue el mismo contorno (superelipse) del torso a la altura de la cintura.
    zc = sum(M["cuerda"]) / 2
    sec = min(outer, key=lambda s: abs(s["z"] - zc))
    half_x = (sec["fx"][1] - sec["fx"][0]) / 2 + 0.02
    y_mid = (sec["back"] - sec["front"]) / 2
    depth = (sec["front"] + sec["back"]) / 2 + 0.02
    ring = [Vector((half_x * _superellipse(math.cos(a), 2.6), y_mid + depth * _superellipse(math.sin(a), 2.6), zc))
            for a in [math.tau * k / 96 for k in range(97)]]
    _tube("Cuerda", ring, [0.017] * len(ring), "Cuerda", body, segments=10)
    front_y = y_mid - depth
    knot = M["nudo"].copy()
    knot.y = front_y - 0.01
    _sphere("Nudo", knot, (0.03, 0.022, 0.028), "Cuerda", body)
    for dx in M["cabos"][1]:
        pts = [Vector((dx, front_y - 0.012, zc - 0.02 - (zc - M["cabos"][0]) * k / 6)) for k in range(7)]
        _tube(f"Cabo{dx:+.2f}", pts, [0.013] * 6 + [0.016], "Cuerda", body, segments=10)


def paso_cabeza():
    """Cabeza, pelo y barba: el volumen sale de las siluetas; el color, de la vista que mira cada cara."""
    data = json.load(open(VOLUMES))
    body = bpy.data.objects["Cuerpo"]
    head_pivot = pivot("Cabeza", (0, 0, 1.13), body)
    secs = _sections_fit(data["cabeza"], 0.9, 1.6, sigma=3.0)
    # Coronilla redonda: por encima de 1.40 m, cada medida sigue una elipse que llega a cero en la
    # altura medida del pelo (1.555 m), partiendo del ancho real a 1.40 m.
    top_z = 1.555
    base = min(secs, key=lambda s: abs(s["z"] - 1.40))
    secs = [s for s in secs if s["z"] <= base["z"]]
    for k in range(1, 13):
        z = base["z"] + (top_z - base["z"]) * k / 12
        f = math.sqrt(max(1.0 - ((z - base["z"]) / (top_z - base["z"])) ** 2, 0.0)) if k < 12 else 0.05
        secs.append({"z": z, "fx": [v * f for v in base["fx"]], "bx": [v * f for v in base["bx"]],
                     "front": base["front"] * f + (1 - f) * (base["front"] - base["back"]) / 2 * 0,
                     "back": base["back"] * f})
    head = build_volume("CabezaPelo", secs, 2.1, 64, smooth=False)
    # Colores con las zonas medidas: óvalo de la cara (por encima de la línea de la barba), calva en
    # la coronilla y el resto pelo/barba.
    head.data.materials.append(material("Canas"))
    head.data.materials.append(material("Piel"))
    mw = head.matrix_world
    for poly in head.data.polygons:
        c = mw @ poly.center
        nrm = (mw.to_3x3() @ poly.normal).normalized()
        in_oval = (c.x / 0.15) ** 2 + ((c.z - 1.355) / 0.125) ** 2 < 1.0
        above_beard = c.z > 1.245 + 2.8 * c.x * c.x
        face = nrm.y < -0.3 and in_oval and above_beard
        bald = nrm.y > 0.1 and c.z > 1.49 and (c.x / 0.075) ** 2 + ((c.z - 1.555) / 0.06) ** 2 < 1.0
        poly.material_index = 1 if (face or bald) else 0
    # Mechones: ondas verticales suaves en el pelo de la espalda y los lados.
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
    """Cada cara toma el material de la mayoría de sus vecinas: bordes de color limpios."""
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
    """Punto de la superficie delantera del objeto en (x, z), lanzando un rayo desde delante."""
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    hit, normal, _i, _d = bvh.ray_cast(Vector((x, -2.0, z)), Vector((0, 1, 0)))
    if hit is None:
        return Vector((x, -0.2, z))
    return hit + normal * out


def paso_rasgos():
    """Ojos, cejas, nariz, bigote y orejas en las posiciones medidas, pegados a la cabeza."""
    head = bpy.data.objects["CabezaPelo"]
    pivot_head = bpy.data.objects["Cabeza"]
    for sx, side in ((1, "I"), (-1, "D")):
        eye_center = _on_surface(head, sx * M["ojo"].x, M["ojo"].z, 0.0)
        eye = pivot(f"Ojo{side}", eye_center, pivot_head)
        _sphere(f"Iris{side}", eye_center, M["ojo_tam"], "Ojo", eye)
        _sphere(f"Brillo{side}", eye_center + Vector((-sx * 0.004, -0.008, 0.006)), (0.004, 0.003, 0.005), "Brillo",
                eye)
        brow_pts = []
        for k in range(7):
            t = k / 6
            bx = sx * (M["ceja"].x - 0.038 + 0.076 * t)
            bz = M["ceja"].z + 0.012 * math.sin(t * math.pi) - 0.01 * t
            brow_pts.append(_on_surface(head, bx, bz, 0.008))
        _tube(f"Ceja{side}", brow_pts, [0.009, 0.014, 0.016, 0.016, 0.015, 0.012, 0.008], "Canas", pivot_head, 14)
        ear = M["oreja"].copy()
        ear.x *= sx
        _sphere(f"Oreja{side}", ear, M["oreja_tam"], "Piel", pivot_head)
        # Bigote: dos mechones del centro hacia fuera, cayendo en los extremos.
        z, half = M["bigote"]
        pts = []
        for k in range(7):
            t = k / 6
            x = sx * (0.012 + half * t)
            p = _on_surface(head, x, z - 0.035 * t * t, 0.006)
            pts.append(p)
        _tube(f"Bigote{side}", pts, [0.022, 0.024, 0.024, 0.022, 0.019, 0.015, 0.01], "Canas", pivot_head, 16)
    nose = M["nariz"].copy()
    nose.y += M["nariz_tam"][1]
    _sphere("Nariz", nose, M["nariz_tam"], "Nariz", pivot_head)


def paso_brazos():
    body = bpy.data.objects["Cuerpo"]
    for sx, side in ((1, "I"), (-1, "D")):
        shoulder = Vector((sx * 0.215, 0.0, 1.05))
        cuff = M["puno"] * Vector((sx, 1, 1))
        arm = pivot(f"Brazo{side}", shoulder, body)
        axis = (cuff - shoulder).normalized()
        # Manga: cono que se abre hacia el puño, abierta abajo y con grosor.
        pts = [shoulder + (cuff - shoulder) * (k / 10) for k in range(11)]
        r0, r1 = M["manga_r"]
        radii = [r0 + (r1 - r0) * (k / 10) ** 1.5 for k in range(11)]
        sleeve = _tube(f"Manga{side}", pts, radii, "Manga", arm, segments=24)
        bm = bmesh.new()
        bm.from_mesh(sleeve.data)
        lowest = min(bm.faces, key=lambda f: f.calc_center_median().z)
        bmesh.ops.delete(bm, geom=[lowest], context="FACES_ONLY")
        bm.to_mesh(sleeve.data)
        bm.free()
        _solidify(sleeve, -0.008)
        # Mano: manopla (dedos juntos) un poco más estrecha que el puño, más el pulgar.
        hand = cuff + axis * 0.07
        palm = _sphere(f"Mano{side}", hand, (0.044, 0.03, 0.07), "Piel", arm)
        palm.rotation_euler = (0.0, -sx * math.atan2(axis.x * sx, -axis.z), 0)
        _sphere(f"Dedos{side}", hand + axis * 0.045 + Vector((0, -0.004, 0)), (0.04, 0.026, 0.035), "Piel", arm)
        _sphere(f"Pulgar{side}", hand + Vector((-sx * 0.026, -0.022, 0.012)), (0.015, 0.016, 0.03), "Piel", arm)


def paso_pies():
    root = bpy.data.objects["Noe"]
    heel, toe = M["pie_y"]
    for sx, side in ((1, "I"), (-1, "D")):
        x = sx * M["pie_x"]
        foot = pivot(f"Pie{side}", (x, 0.04, 0.06), root)
        # Pierna y pie en una sola pieza: del tobillo baja y gira hacia delante hasta los dedos.
        _tube(f"PiernaPie{side}", [Vector((x, 0.03, 0.2)), Vector((x, 0.03, 0.07)), Vector((x, 0.0, 0.045)),
                                    Vector((x, -0.07, 0.04)), Vector((x, toe + 0.025, 0.035))],
              [0.048, 0.05, 0.052, 0.05, 0.036], "Piel", foot, 20)
        length = heel - toe
        _sphere(f"Suela{side}", Vector((x, (heel + toe) / 2, 0.012)), (M["pie_semiancho"], length / 2, 0.014),
                "Sandalia", foot)
        for y_strap, h in ((toe + 0.075, 0.062), (0.0, 0.07)):
            _tube(f"Tira{side}{y_strap:+.2f}", [Vector((x - 0.058, y_strap, 0.02)), Vector((x - 0.045, y_strap, h)),
                                                Vector((x + 0.045, y_strap, h)), Vector((x + 0.058, y_strap, 0.02))],
                  [0.011] * 4, "Sandalia", foot, 12)
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
    world = bpy.data.worlds.get("Cielo") or bpy.data.worlds.new("Cielo")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4
    scene.world = world
    key = bpy.data.objects.new("Sol", bpy.data.lights.new("Sol", "SUN"))
    key.data.energy = 2.0
    key.data.color = (1.0, 0.96, 0.9)
    key.data.angle = math.radians(25)
    key.rotation_euler = (math.radians(45), math.radians(8), math.radians(-30))
    rim = bpy.data.objects.new("Contraluz", bpy.data.lights.new("Contraluz", "SUN"))
    rim.data.energy = 1.2
    rim.rotation_euler = (math.radians(60), 0, math.radians(160))
    for o in (key, rim):
        scene.collection.objects.link(o)
    return [key, rim]


def paso_render(folder):
    """Las 4 vistas a la misma escala que la hoja de giro, para ponerlas debajo de la referencia."""
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
    cam = bpy.data.objects.new("CamaraOrto", bpy.data.cameras.new("CamaraOrto"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 572 * PX
    scene.collection.objects.link(cam)
    scene.camera = cam
    added.append(cam)
    cz = (REF_BASE_Y - 286) * PX
    views = (("frente", (0, -5, cz), (math.pi / 2, 0, 0)),
             ("lado", (-5, 0, cz), (math.pi / 2, 0, -math.pi / 2)),
             ("espalda", (0, 5, cz), (math.pi / 2, 0, math.pi)),
             ("tres_cuartos", (3.2, -3.8, cz), (math.pi / 2, 0, math.radians(40))))
    for label, loc, rot in views:
        cam.location = loc
        cam.rotation_euler = rot
        scene.render.filepath = os.path.join(folder, f"noe_{label}.png")
        bpy.ops.render.render(write_still=True)
    for o in added:
        bpy.data.objects.remove(o)


def paso_exportar(out_path):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=out_path, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True, export_animations=False)
    print(f"NOE OK -> {out_path}")


PASOS = [paso_limpiar, paso_ropa, paso_cabeza, paso_rasgos, paso_brazos, paso_pies]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path = argv[0] if argv else "noe.glb"
    renders = argv[1] if len(argv) > 1 else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for paso in PASOS:
        paso()
    if renders:
        paso_render(renders)
    paso_exportar(out_path)


if not globals().get("EN_VIVO"):
    main()
