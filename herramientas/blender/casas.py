"""Casas de adobe y objetos de la aldea de Noé (docs/DISENO_CAPITULO1.md), exportados a glTF.

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/casas.py -- assets/aldea/aldea.glb [carpeta_renders]

Cada objeto del archivo es una pieza con su origen en el suelo, en el centro, y con la fachada
(la puerta) mirando a -Y, que en Godot es +Z. Medidas en metros, contra Noé (1,55 m):
    CasaNoe        8 × 5 m, muros de 2,6 m, patio con murete delante
    CasaA/B/C      5 × 4 m, muros de 2,4 m (B con escalera al techo, C con toldo)
    Pozo           Ø 1,4 m, brocal de 0,7 m, travesaño y cubo
    Horno          tannur de barro, Ø 0,8 m, 0,9 m de alto
    Banco, Cantaro, Cesta, Lena, Cerca (tramo de 2 m), Puesto (alfarero)
"""

import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

random.seed(3)

COLORS = {
    "Adobe": (0.76, 0.49, 0.31),
    "AdobeSombra": (0.68, 0.43, 0.27),
    "Zocalo": (0.66, 0.42, 0.27),
    "Techo": (0.84, 0.59, 0.39),
    "Madera": (0.58, 0.39, 0.24),
    "MaderaOscura": (0.43, 0.28, 0.17),
    "Hueco": (0.25, 0.18, 0.14),
    "Barro": (0.79, 0.56, 0.38),
    "Piedra": (0.70, 0.67, 0.75),
    "TelaRosa": (0.91, 0.64, 0.56),
    "TelaAzul": (0.62, 0.72, 0.79),
    "Cuerda": (0.62, 0.50, 0.33),
    "Mimbre": (0.80, 0.66, 0.42),
    "Saco": (0.86, 0.79, 0.63),
    "TelaVerde": (0.62, 0.73, 0.52),
    "TelaOcre": (0.88, 0.70, 0.40),
    "Fuego": (0.98, 0.62, 0.28),
    "Brea": (0.20, 0.15, 0.12),
    "Agua": (0.55, 0.76, 0.82),
    "TelaRoja": (0.86, 0.38, 0.35),
    "TelaCrema": (0.97, 0.92, 0.84),
    "TelaAzulFuerte": (0.38, 0.58, 0.80),
    "PiedraGris": (0.62, 0.62, 0.64),
    "PiedraPozo": (0.55, 0.52, 0.48),
    "PiedraPozoOscura": (0.36, 0.34, 0.31),
    "LosaPozo": (0.60, 0.56, 0.51),
    "AguaPozo": (0.16, 0.26, 0.32),
    "Metal": (0.40, 0.40, 0.44),
    "Soga": (0.78, 0.63, 0.40),
    "MaderaCorte": (0.86, 0.68, 0.47),
    "AnilloCorte": (0.74, 0.55, 0.36),
    "Corteza": (0.50, 0.31, 0.19),
    "PiedraFogata": (0.60, 0.57, 0.54),
    "PiedraFogataOscura": (0.48, 0.45, 0.43),
    "Brasa": (0.95, 0.42, 0.15),
    "Ceniza": (0.42, 0.38, 0.35),
    "Llama": (1.00, 0.78, 0.25),
    "LlamaFuera": (0.98, 0.48, 0.13),
    "MimbreOscuro": (0.63, 0.47, 0.27),
    "Manzana": (0.86, 0.20, 0.17),
    "Naranja": (0.98, 0.56, 0.13),
    "Pera": (0.70, 0.80, 0.26),
    "Uva": (0.52, 0.26, 0.60),
    "Hoja": (0.36, 0.62, 0.20),
    "AguaBebedero": (0.38, 0.52, 0.60),
    "HiloCrema": (0.93, 0.88, 0.78),
    "TelaRojaTelar": (0.80, 0.33, 0.27),
    "LonaCrema": (0.88, 0.79, 0.62),
    "LonaAzul": (0.43, 0.60, 0.74),
    "LonaVerde": (0.56, 0.66, 0.50),
    "LonaSalvia": (0.68, 0.72, 0.62),
    "LonaGris": (0.60, 0.63, 0.58),
}


def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        # Los colores de arriba están en sRGB; Blender trabaja en lineal.
        linear = tuple(c ** 2.2 for c in COLORS[name])
        bsdf.inputs["Base Color"].default_value = (*linear, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.9
        mat.diffuse_color = (*linear, 1.0)
        if name in ("Llama", "LlamaFuera", "Brasa"):            # El fuego brilla.
            bsdf.inputs["Emission Color"].default_value = (*linear, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 1.5
    return mat


# --- Piezas básicas -----------------------------------------------------------

def _finish(obj, mat, bevel=0.0, segments=3, smooth=False):
    obj.data.materials.append(material(mat))
    if bevel > 0.0:
        mod = obj.modifiers.new("Bisel", "BEVEL")
        mod.width = bevel
        mod.segments = segments
        mod.limit_method = "ANGLE"
    for p in obj.data.polygons:
        p.use_smooth = smooth
    return obj


def box(name, size, loc, mat, bevel=0.0, rot=(0, 0, 0), taper=0.0, smooth=False, segments=3):
    """Caja con el centro de la base en `loc`. taper: cuánto se estrecha arriba (muros de adobe)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z = (v.co.z + 0.5) * size[2]
        if taper and v.co.z > size[2] * 0.5:
            v.co.x -= math.copysign(taper, v.co.x)
            v.co.y -= math.copysign(taper, v.co.y)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    obj.rotation_euler = rot
    bpy.context.collection.objects.link(obj)
    return _finish(obj, mat, bevel, segments=segments, smooth=smooth)


def cylinder(name, radius, depth, loc, mat, verts=16, rot=(0, 0, 0), top_radius=None, bevel=0.0, smooth=True):
    """Cilindro con la base en `loc` (sube por +Z antes de girar)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=radius,
                          radius2=radius if top_radius is None else top_radius, depth=depth)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, depth * 0.5))
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    obj.rotation_euler = rot
    bpy.context.collection.objects.link(obj)
    return _finish(obj, mat, bevel, smooth=smooth)


def lathe(name, profile, loc, mat, verts=20):
    """Pieza de torno (cántaros, horno): perfil [(radio, altura), ...] de abajo a arriba."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        ring = [bm.verts.new((r * math.cos(2 * math.pi * i / verts), r * math.sin(2 * math.pi * i / verts), z))
                for i in range(verts)]
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for i in range(verts):
            bm.faces.new((a[i], a[(i + 1) % verts], b[(i + 1) % verts], b[i]))
    bm.faces.new(list(reversed(rings[0])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    bpy.context.collection.objects.link(obj)
    return _finish(obj, mat, smooth=True)


def join(name, parts):
    """Une las piezas (aplicando sus modificadores) en un solo objeto con el origen en el suelo."""
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    for p in parts:
        bpy.context.view_layer.objects.active = p
        for m in list(p.modifiers):
            bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


# --- Casas --------------------------------------------------------------------

# Casas de arcilla (referencias/casas_adobe.jpg y casa_noe.jpg): bloques muy redondeados, como
# modelados a mano, con pretil grueso, vigas que asoman, ventanas hundidas con marco, puertas de
# tablas con escalón de piedra, escaleras de adobe, escaleras de mano, toldos a rayas y muretes de
# patio que abrazan la casa.

def clay(name, w, d, h, loc, mat="Adobe"):
    """Bloque de adobe con los bordes muy redondeados y los muros apenas inclinados."""
    return box(name, (w, d, h), loc, mat, bevel=min(0.32, h * 0.16, w * 0.12), taper=0.05, smooth=True,
               segments=4)


def roof(name, w, d, x, y, z):
    """Pretil grueso y redondeado alrededor del techo plano, con la losa algo más clara."""
    parts = [box(f"{name}_losa", (w - 0.3, d - 0.3, 0.06), (x, y, z - 0.02), "Techo", bevel=0.02)]
    for sy in (-1, 1):
        parts.append(box(f"{name}_pretx{sy}", (w, 0.3, 0.32), (x, y + sy * (d * 0.5 - 0.15), z - 0.12), "Adobe",
                         bevel=0.13, smooth=True, segments=3))
    for sx in (-1, 1):
        parts.append(box(f"{name}_prety{sx}", (0.3, d, 0.32), (x + sx * (w * 0.5 - 0.15), y, z - 0.12), "Adobe",
                         bevel=0.13, smooth=True, segments=3))
    return parts


def beams(name, w, d, x, y, z, sides=("front", "back")):
    """Hilera de vigas de madera que asoman bajo el pretil."""
    parts = []
    n = max(2, int(w / 0.95))
    for side in sides:
        if side in ("front", "back"):
            sy = -1 if side == "front" else 1
            for i in range(n):
                bx = x - w * 0.5 + (i + 0.5) * w / n
                # Nacen dentro del muro y asoman unos 35 cm hacia fuera.
                parts.append(cylinder(f"{name}_viga{side}{i}", 0.085, 0.5, (bx, y + sy * (d * 0.5 - 0.15), z),
                                      "MaderaOscura", verts=8, rot=(math.radians(-90) * sy, 0, 0)))
        else:
            sx = -1 if side == "left" else 1
            m = max(2, int(d / 0.95))
            for i in range(m):
                by = y - d * 0.5 + (i + 0.5) * d / m
                parts.append(cylinder(f"{name}_viga{side}{i}", 0.085, 0.5, (x + sx * (w * 0.5 - 0.15), by, z),
                                      "MaderaOscura", verts=8, rot=(0, math.radians(90) * sx, 0)))
    return parts


def window(name, x, y, z, face=-1, size=(0.55, 0.55)):
    """Ventana pequeña y hundida, con marco de madera. face: -1 fachada (-Y), 1 trasera."""
    fy = y + face * 0.02
    parts = [box(f"{name}_hueco", (size[0], 0.3, size[1]), (x, fy, z), "Hueco", bevel=0.04)]
    for dz, hh in ((-0.08, 0.1), (size[1] - 0.02, 0.1)):
        parts.append(box(f"{name}_marcoh{dz}", (size[0] + 0.3, 0.16, hh), (x, fy + face * 0.07, z + dz), "Madera",
                         bevel=0.025))
    for sx in (-1, 1):
        parts.append(box(f"{name}_marcov{sx}", (0.1, 0.16, size[1]), (x + sx * (size[0] * 0.5 + 0.05), fy + face * 0.07, z),
                         "Madera", bevel=0.02))
    return parts


def door(name, x, y, face=-1, w=1.0, h=1.85):
    """Puerta de tablas con su marco, dintel y escalón de piedra."""
    fy = y + face * 0.02
    parts = [box(f"{name}_hueco", (w + 0.1, 0.3, h + 0.05), (x, fy, 0.1), "Hueco", bevel=0.04),
             box(f"{name}_hoja", (w - 0.08, 0.08, h - 0.08), (x, fy + face * 0.1, 0.14), "Madera", bevel=0.02)]
    for i in range(3):
        parts.append(box(f"{name}_junta{i}", (0.025, 0.09, h - 0.2), (x - w * 0.25 + i * w * 0.25, fy + face * 0.13, 0.2),
                         "MaderaOscura"))
    parts.append(cylinder(f"{name}_pomo", 0.04, 0.06, (x + w * 0.32, fy + face * 0.15, 0.95), "MaderaOscura", verts=8,
                          rot=(math.radians(90) * -face, 0, 0)))
    parts.append(box(f"{name}_dintel", (w + 0.5, 0.24, 0.16), (x, fy + face * 0.09, h + 0.12), "MaderaOscura", bevel=0.04))
    for sx in (-1, 1):
        parts.append(box(f"{name}_jamba{sx}", (0.12, 0.2, h), (x + sx * (w * 0.5 + 0.08), fy + face * 0.08, 0.12), "Madera",
                         bevel=0.03))
    parts.append(box(f"{name}_escalon", (w + 0.5, 0.55, 0.14), (x, y + face * 0.32, 0), "PiedraGris", bevel=0.05,
                     smooth=True))
    return parts


def stair(name, x, y0, y1, h, width=0.9, mat="AdobeSombra"):
    """Escalera de adobe pegada a un muro: sube de y0 (abajo) a y1 (arriba) hasta la altura h."""
    parts = []
    steps = max(4, int(h / 0.3))
    for i in range(steps):
        t = (i + 1) / steps
        sy = y0 + (y1 - y0) * (i + 0.5) / steps
        parts.append(box(f"{name}_esc{i}", (width, abs(y1 - y0) / steps + 0.02, h * t), (x, sy, 0), mat, bevel=0.06,
                         smooth=True))
    # Murete lateral de la escalera, en rampa (más redondeado: parece modelado a mano).
    return parts


def ladder(name, x, y, z, height, lean=0.25, rot_z=0.0):
    """Escalera de mano apoyada (se inclina hacia +Y antes de girar rot_z)."""
    parts = []
    for sx in (-1, 1):
        parts.append(cylinder(f"{name}_larguero{sx}", 0.045, height, (x + sx * 0.22, y, z), "Madera", verts=6,
                              rot=(-lean, 0, rot_z)))
    steps = int(height / 0.35)
    for i in range(steps):
        zz = z + (i + 0.6) * height / steps * math.cos(lean)
        yy = y + (i + 0.6) * height / steps * math.sin(lean)
        parts.append(cylinder(f"{name}_peldano{i}", 0.03, 0.48, (x - 0.24, yy, zz), "MaderaOscura", verts=6,
                              rot=(0, math.radians(90), rot_z)))
    return parts


def striped(name, w, d, loc, colors, tilt=0.0, stripes=6, along_x=True):
    """Tela a rayas (toldo): franjas alternas de dos colores, algo inclinada."""
    parts = []
    for i in range(stripes):
        t = (i + 0.5) / stripes - 0.5
        if along_x:
            off, size = (t * w, 0, 0), (w / stripes + 0.005, d, 0.04)
        else:
            off, size = (0, t * d, 0), (w, d / stripes + 0.005, 0.04)
        parts.append(box(f"{name}_raya{i}", size, (loc[0] + off[0], loc[1] + off[1], loc[2]), colors[i % 2], bevel=0.01,
                         rot=(tilt, 0, 0)))
    return parts


def shade(name, w, d, x, y, z, colors=("TelaRoja", "TelaCrema")):
    """Sombra de tela a rayas sobre cuatro postes (en el techo)."""
    parts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(cylinder(f"{name}_poste{sx}{sy}", 0.05, 1.7, (x + sx * w * 0.5, y + sy * d * 0.5, z), "Madera",
                                  verts=8))
    parts += striped(f"{name}_tela", w + 0.2, d + 0.1, (x, y, z + 1.66), colors, stripes=7)
    return parts


def yard_wall(name, points, h=0.95, t=0.38, mat="Adobe"):
    """Murete de patio por una polilínea de puntos (x, y): tramos redondeados y uniones con poste."""
    parts = []
    for i in range(len(points) - 1):
        (ax, ay), (bx, by) = points[i], points[i + 1]
        length = math.hypot(bx - ax, by - ay)
        ang = math.atan2(by - ay, bx - ax)
        parts.append(box(f"{name}_tramo{i}", (length + t * 0.6, t, h), ((ax + bx) * 0.5, (ay + by) * 0.5, 0), mat,
                         bevel=0.15, smooth=True, segments=3, rot=(0, 0, ang)))
    return parts


def build_houses():
    houses = []
    # A: un bloque con escalera exterior al techo y sombra a rayas arriba; poyo bajo al pie.
    w, d, h = 4.6, 3.8, 2.5
    p = [clay("CasaA_bloque", w, d, h, (0, 0, 0))] + roof("CasaA_techo", w, d, 0, 0, h)
    p += beams("CasaA", w, d, 0, 0, h - 0.4, ("front", "back", "left"))
    p += door("CasaA_puerta", -0.5, -d * 0.5)
    p += window("CasaA_vent1", 1.25, -d * 0.5, 1.15)
    p += window("CasaA_vent2", -0.9, d * 0.5, 1.2, face=1) + window("CasaA_vent3", 0.9, d * 0.5, 1.2, face=1)
    p += stair("CasaA_escalera", w * 0.5 + 0.45, -d * 0.5 + 0.2, d * 0.5 - 0.1, h)
    p.append(clay("CasaA_poyo", 1.6, 0.6, 0.45, (-w * 0.5 + 0.6, -d * 0.5 - 0.3, 0), "AdobeSombra"))
    p += shade("CasaA_sombra", 2.6, 1.8, -0.6, 0.5, h)
    houses.append(join("CasaA", p))

    # B: dos alturas (bloque alto atrás a la izquierda), escalera de mano y patio con murete delante.
    w, d, h = 5.6, 4.2, 2.2
    p = [clay("CasaB_bajo", w, d, h, (0, 0, 0))] + roof("CasaB_techo", w, d, 0, 0, h)
    p += beams("CasaB", w, d, 0, 0, h - 0.38, ("front", "back"))
    p += [clay("CasaB_alto", 2.8, 3.0, 1.8, (-1.2, 0.5, h))] + roof("CasaB_techo2", 2.8, 3.0, -1.2, 0.5, h + 1.8)
    p += beams("CasaB_alto", 2.8, 3.0, -1.2, 0.5, h + 1.4, ("front",))
    p += window("CasaB_vent_alta", -1.2, -1.0, h + 0.75)
    p += door("CasaB_puerta", -1.2, -d * 0.5)
    p += window("CasaB_vent1", 1.6, -d * 0.5, 1.05)
    p += ladder("CasaB_escalera", 0.55, -0.6, h - 0.05, 2.1, lean=0.0, rot_z=0.0)
    p += yard_wall("CasaB_patio", [(-w * 0.5 + 0.2, -d * 0.5), (-w * 0.5 + 0.2, -d * 0.5 - 2.4), (-0.9, -d * 0.5 - 2.4)])
    p += yard_wall("CasaB_patio2", [(0.5, -d * 0.5 - 2.4), (w * 0.5 - 0.2, -d * 0.5 - 2.4), (w * 0.5 - 0.2, -d * 0.5)])
    houses.append(join("CasaB", p))

    # C: un bloque con toldo a rayas sobre la puerta, poyo con macetas delante y patio detrás.
    w, d, h = 4.4, 3.6, 2.4
    p = [clay("CasaC_bloque", w, d, h, (0, 0, 0))] + roof("CasaC_techo", w, d, 0, 0, h)
    p += beams("CasaC", w, d, 0, 0, h - 0.4, ("front", "left", "right"))
    p += door("CasaC_puerta", 0.0, -d * 0.5)
    p += window("CasaC_vent1", 1.45, -d * 0.5, 1.15)
    p += window("CasaC_vent2", 1.0, d * 0.5, 1.2, face=1)
    p += striped("CasaC_toldo", 1.9, 1.0, (0.0, -d * 0.5 - 0.5, 2.25), ("TelaAzulFuerte", "TelaCrema"),
                 tilt=math.radians(-18), stripes=6)
    for sx in (-1, 1):
        p.append(cylinder(f"CasaC_poste{sx}", 0.045, 2.15, (sx * 0.95, -d * 0.5 - 0.95, 0), "Madera", verts=8))
    p.append(clay("CasaC_poyo", 4.0, 0.55, 0.42, (0, -d * 0.5 - 0.28, 0), "AdobeSombra"))
    p += yard_wall("CasaC_patio", [(-w * 0.5 + 0.2, d * 0.5), (-w * 0.5 + 0.2, d * 0.5 + 2.2), (w * 0.5 - 0.2, d * 0.5 + 2.2),
                                   (w * 0.5 - 0.2, d * 0.5)])
    houses.append(join("CasaC", p))

    # Casa de Noé (referencias/casa_noe.jpg): planta baja ancha, planta alta retrasada con sombra a
    # rayas, escalera exterior a la planta baja y otra a la alta, y patio delante con murete y portón.
    w, d, h = 7.0, 5.0, 2.4
    p = [clay("CasaNoe_bajo", w, d, h, (0, 0, 0))] + roof("CasaNoe_techo", w, d, 0, 0, h)
    p += beams("CasaNoe", w, d, 0, 0, h - 0.4, ("front", "back", "left"))
    uw, ud, uh = 4.2, 3.2, 2.1
    p += [clay("CasaNoe_alto", uw, ud, uh, (-0.8, 0.8, h))] + roof("CasaNoe_techo2", uw, ud, -0.8, 0.8, h + uh)
    p += beams("CasaNoe_alto", uw, ud, -0.8, 0.8, h + uh - 0.4, ("front", "left"))
    p += door("CasaNoe_puerta_alta", -1.4, 0.8 - ud * 0.5, w=0.9, h=1.6)
    for part in p[-10:]:
        part.location.z += h
    p += window("CasaNoe_vent_alta", 0.4, 0.8 - ud * 0.5, h + 1.0)
    p += door("CasaNoe_puerta", -1.6, -d * 0.5)
    p += door("CasaNoe_puerta2", 1.7, -d * 0.5, w=0.9, h=1.7)
    p += window("CasaNoe_vent1", -3.0, -d * 0.5, 1.15) + window("CasaNoe_vent2", 0.1, -d * 0.5, 1.2)
    p += window("CasaNoe_vent3", 2.6, d * 0.5, 1.2, face=1)
    p += stair("CasaNoe_escalera", w * 0.5 + 0.45, -d * 0.5 + 0.3, d * 0.5 - 0.1, h)
    p += [part for part in stair("CasaNoe_escalera2", 1.75, -0.6, 2.2, uh)]
    for part in p[-max(4, int(uh / 0.3)):]:
        part.location.z += h
    p += shade("CasaNoe_sombra", 2.4, 1.6, -1.2, 1.1, h + uh)
    yard = -d * 0.5 - 4.0
    p += yard_wall("CasaNoe_patio", [(-w * 0.5 + 0.1, -d * 0.5), (-w * 0.5 - 0.4, -d * 0.5), (-w * 0.5 - 0.4, yard),
                                     (-0.6, yard)])
    p += yard_wall("CasaNoe_patio2", [(0.9, yard), (w * 0.5 + 0.9, yard), (w * 0.5 + 0.9, -d * 0.5 - 0.2)])
    for sx in (-0.6, 0.9):
        p.append(clay(f"CasaNoe_pilar{sx}", 0.55, 0.55, 1.35, (sx, yard, 0), "Adobe"))
    houses.append(join("CasaNoe", p))
    return houses


# --- Objetos ------------------------------------------------------------------

def build_well():
    """Pozo de la plaza (referencias/recortes/pozo.png), pieza a pieza y cada una de su color: base de
    losas redondeadas, brocal de tres hiladas de bloques (alternados como un muro), agua, dos postes,
    travesaño con la soga enrollada, la soga que baja, el cubo de duelas con aros de metal y la manivela."""
    rnd = random.Random(11)
    p = []
    # Base: anillo de losas alrededor del brocal.
    p.append(cylinder("Pozo_base", 1.25, 0.08, (0, 0, 0), "PiedraPozoOscura", verts=24, bevel=0.03))
    n = 14
    for i in range(n):
        a = 2 * math.pi * (i + 0.5) / n
        r = 1.0
        p.append(box(f"Pozo_losa{i}", (0.42, 2 * math.pi * r / n - 0.06, 0.1), (math.cos(a) * r, math.sin(a) * r, 0.06),
                     "LosaPozo", bevel=0.045, smooth=True, rot=(0, 0, a + rnd.uniform(-0.04, 0.04))))
    # Brocal: tres hiladas de bloques, cada una girada media pieza respecto a la de abajo.
    radius, bh, blocks = 0.62, 0.22, 11
    for row in range(3):
        for i in range(blocks):
            a = 2 * math.pi * (i + 0.5 * (row % 2)) / blocks
            w = 2 * math.pi * radius / blocks - 0.035
            p.append(box(f"Pozo_bloque{row}_{i}", (0.24, w, bh - 0.03),
                         (math.cos(a) * radius, math.sin(a) * radius, 0.14 + row * bh),
                         "PiedraPozo", bevel=0.05, smooth=True, rot=(0, 0, a + rnd.uniform(-0.03, 0.03))))
    # Remate del brocal y relleno oscuro entre bloques (las juntas).
    p.append(lathe("Pozo_juntas", [(0.5, 0.14), (0.72, 0.14), (0.72, 0.8), (0.5, 0.8)], (0, 0, 0), "PiedraPozoOscura",
                   verts=28))
    for i in range(blocks):
        a = 2 * math.pi * i / blocks
        p.append(box(f"Pozo_remate{i}", (0.3, 2 * math.pi * radius / blocks - 0.03, 0.09),
                     (math.cos(a) * radius, math.sin(a) * radius, 0.8), "PiedraPozo", bevel=0.04, smooth=True,
                     rot=(0, 0, a)))
    p.append(cylinder("Pozo_agua", 0.5, 0.02, (0, 0, 0.45), "AguaPozo", verts=24))
    # Postes y travesaño.
    for side in (-1, 1):
        p.append(box(f"Pozo_poste{side}", (0.2, 0.2, 2.05), (side * 0.9, 0, 0.06), "Madera", bevel=0.04, taper=0.015))
        p.append(box(f"Pozo_remate_poste{side}", (0.26, 0.26, 0.08), (side * 0.9, 0, 2.08), "MaderaOscura", bevel=0.03))
    p.append(cylinder("Pozo_travesano", 0.075, 2.25, (-1.12, 0, 1.86), "Madera", verts=10, rot=(0, math.radians(90), 0)))
    # Soga enrollada en el centro del travesaño y la que baja hasta el cubo.
    for i in range(5):
        p.append(cylinder(f"Pozo_vuelta{i}", 0.098, 0.05, (-0.13 + i * 0.055, 0, 1.86), "Soga", verts=12,
                          rot=(0, math.radians(90), 0)))
    p.append(cylinder("Pozo_soga", 0.02, 0.58, (0, 0, 1.22), "Soga", verts=6))
    # Cubo: duelas de madera, dos aros de metal y el asa.
    p.append(lathe("Pozo_cubo", [(0.0, 0.0), (0.13, 0.0), (0.15, 0.24), (0.14, 0.25), (0.0, 0.25)], (0, 0, 0.95),
                   "Madera", verts=12))
    for z in (0.99, 1.15):
        p.append(cylinder(f"Pozo_aro{z}", 0.15 if z > 1 else 0.138, 0.03, (0, 0, z), "Metal", verts=16))
    p.append(torus_part("Pozo_asa", 0.15, 0.012, (0, 0, 1.2), "Metal"))
    # Manivela en el poste derecho.
    p.append(box("Pozo_manivela_brazo", (0.06, 0.06, 0.32), (1.06, 0, 1.7), "MaderaOscura", bevel=0.015))
    p.append(cylinder("Pozo_manivela_mango", 0.03, 0.22, (1.06, 0, 1.72), "Madera", verts=8, rot=(0, math.radians(90), 0)))
    return join("Pozo", p)


def ball(name, r, loc, mat, scale=(1, 1, 1), segments=10):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=max(6, segments * 2 // 3), radius=r)
    bmesh.ops.scale(bm, vec=scale, verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    bpy.context.collection.objects.link(obj)
    return _finish(obj, mat, smooth=True)


def log(name, r, length, center, yaw=0.0, pitch=0.0, bark="Corteza", cut="MaderaCorte", bevel=0.02):
    """Tronco: cilindro de corteza con las dos caras de corte más claras. Va a lo largo de X, girado
    `yaw` alrededor de Z e inclinado `pitch` (hacia arriba)."""
    d = Vector((math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch)))
    c = Vector(center)
    rot = (0, math.radians(90) - pitch, yaw)
    parts = [cylinder(f"{name}_corteza", r, length, tuple(c - d * length / 2), bark, verts=10, rot=rot, bevel=bevel)]
    for k, sgn in enumerate((1, -1)):
        start = c + d * (length / 2) if sgn > 0 else c - d * (length / 2 + 0.012)
        parts.append(cylinder(f"{name}_corte{k}", r * 0.86, 0.012, tuple(start), cut, verts=10, rot=rot))
    return parts


def build_campfire():
    """Fogata (referencias/recortes/fogata.png): anillo de piedras redondeadas de dos tonos, lecho de
    ceniza con brasas y troncos en tipi. Sin llama: el fuego va aparte, animado en el juego."""
    rnd = random.Random(5)
    p = [lathe("Fogata_ceniza", [(0.0, 0.0), (0.4, 0.0), (0.33, 0.03), (0.18, 0.05), (0.0, 0.055)], (0, 0, 0),
               "Ceniza", verts=18)]
    n = 11
    for i in range(n):
        a = 2 * math.pi * i / n + rnd.uniform(-0.06, 0.06)
        sz = rnd.uniform(0.2, 0.26)
        p.append(box(f"Fogata_piedra{i}", (sz, sz * rnd.uniform(0.8, 0.95), sz * 0.7),
                     (math.cos(a) * 0.52, math.sin(a) * 0.52, -0.02),
                     "PiedraFogata" if i % 3 else "PiedraFogataOscura", bevel=sz * 0.35, smooth=True,
                     segments=3, rot=(0, rnd.uniform(-0.12, 0.12), a + rnd.uniform(-0.3, 0.3))))
    for i in range(7):
        a = rnd.uniform(0, 2 * math.pi)
        d = rnd.uniform(0.12, 0.3)
        p.append(ball(f"Fogata_brasa{i}", rnd.uniform(0.025, 0.04), (math.cos(a) * d, math.sin(a) * d, 0.035),
                      "Brasa", scale=(1.2, 1.0, 0.6), segments=8))
    # Troncos en tipi: apoyados en la ceniza y juntos arriba, sobre el fuego.
    for i in range(5):
        a = 2 * math.pi * i / 5 + 0.3
        p += log(f"Fogata_tronco{i}", 0.045, 0.5, (math.cos(a) * 0.13, math.sin(a) * 0.13, 0.19),
                 yaw=a + math.pi, pitch=math.radians(50), bevel=0.012)
    return join("Fogata", p)


def build_baskets():
    """Tres cestas de mimbre con fruta (referencias/recortes/cestas.png): cuerpo, franjas del tejido y
    borde más oscuros, y la fruta asomando."""
    rnd = random.Random(8)
    p = []
    fruits = (("Manzana", "Naranja", "Pera"), ("Pera", "Manzana", "Naranja"), ("Uva", "Pera", "Uva"))
    for b, (cx, cy) in enumerate(((-0.28, 0.12), (0.26, 0.2), (0.05, -0.24))):
        profile = [(0.0, 0.0), (0.15, 0.0), (0.2, 0.08), (0.23, 0.18), (0.22, 0.2)]
        p.append(lathe(f"Cesta{b}_cuerpo", profile, (cx, cy, 0), "Mimbre", verts=16))
        p.append(cylinder(f"Cesta{b}_fondo", 0.2, 0.02, (cx, cy, 0.13), "MimbreOscuro", verts=16))
        for z, r in ((0.07, 0.19), (0.13, 0.215)):
            p.append(torus_ring(f"Cesta{b}_franja{z}", r, 0.012, (cx, cy, z), "MimbreOscuro"))
        p.append(torus_ring(f"Cesta{b}_borde", 0.225, 0.022, (cx, cy, 0.2), "MimbreOscuro"))
        # Montón de fruta: un anillo de 7 junto al borde y 3 encima, en el centro.
        spots = [(2 * math.pi * k / 7, 0.13, 0.19) for k in range(7)] + \
                [(2 * math.pi * k / 3 + 0.5, 0.05, 0.25) for k in range(3)]
        for k, (a, d, z) in enumerate(spots):
            a += rnd.uniform(-0.2, 0.2)
            col = fruits[b][k % 3]
            r = 0.055 if col != "Uva" else 0.04
            x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
            p.append(ball(f"Cesta{b}_fruta{k}", r, (x, y, z), col))
            if col in ("Manzana", "Pera") and k % 2 == 0:
                p.append(cylinder(f"Cesta{b}_rabo{k}", 0.008, 0.035, (x, y, z + r * 0.85), "MaderaOscura", verts=5))
        p.append(ball(f"Cesta{b}_hoja", 0.04, (cx + 0.04, cy - 0.02, 0.31), "Hoja", scale=(1.4, 0.6, 0.25)))
    return join("Cesta", p)


def build_firewood():
    """Leña apilada (referencias/recortes/lena.png): troncos en pirámide (4, 3 y 2), con las caras de corte
    claras mirando al frente y algo de variación de grosor y de largo."""
    rnd = random.Random(4)
    p = []
    for row, n in enumerate((4, 3, 2)):
        for i in range(n):
            r = rnd.uniform(0.085, 0.1)
            x = (i - (n - 1) / 2) * 0.19
            z = 0.095 + row * 0.165
            p += log(f"Lena{row}_{i}", r, rnd.uniform(0.85, 0.95), (x, rnd.uniform(-0.04, 0.04), z),
                     yaw=math.radians(90), bevel=0.015)
    return join("Lena", p)


def build_stump():
    """Tocón para sentarse junto al fuego: tronco corto con el pie ensanchado y raíces, y la cara de corte
    clara arriba con sus anillos."""
    p = [cylinder("Tocon_pie", 0.25, 0.12, (0, 0, 0), "Corteza", verts=14, top_radius=0.2),
         cylinder("Tocon_tronco", 0.2, 0.42, (0, 0, 0), "Corteza", verts=14, top_radius=0.185, bevel=0.02),
         cylinder("Tocon_corte", 0.172, 0.012, (0, 0, 0.42), "MaderaCorte", verts=14)]
    for z, r in ((0.432, 0.115), (0.432, 0.055)):
        p.append(torus_ring(f"Tocon_anillo{r}", r, 0.006, (0, 0, z), "AnilloCorte"))
    for i, a in enumerate((0.3, 1.9, 3.3, 4.8)):
        root = ball(f"Tocon_raiz{i}", 0.07, (math.cos(a) * 0.23, math.sin(a) * 0.23, 0.035), "Corteza",
                    scale=(1.8, 0.9, 0.7), segments=8)
        root.rotation_euler = (0, 0, a)
        p.append(root)
    return join("Tocon", p)


def build_log_seat():
    """Tronco tumbado para sentarse junto al fuego, con un muñón de rama atrás. Va a lo largo de X: el
    frente (+Y en el juego, -Y aquí) es el lado del asiento."""
    p = log("TroncoAsiento", 0.17, 1.05, (0, 0, 0.17), bevel=0.025)
    p += log("TroncoAsiento_rama", 0.05, 0.16, (0.18, 0.2, 0.22), yaw=math.radians(70), pitch=math.radians(20),
             bevel=0.01)
    return join("TroncoAsiento", p)


def build_canvas_stall(name, cloth, goods):
    """Puesto de mercado de lona (referencias/plaza_gemini.jpg): cuatro postes, la lona en una sola agua
    (más alta detrás) con un faldón colgando delante, el mostrador con la mercancía y, en el suelo, sacos,
    un cántaro grande y una cesta. Frente hacia -Y (en el juego, +Z)."""
    rnd = random.Random(len(name))
    p = []
    for sx in (-1, 1):
        p.append(cylinder(f"{name}_poste_atras{sx}", 0.055, 2.36, (sx * 1.2, 0.85, 0), "Madera", verts=8))
        p.append(cylinder(f"{name}_poste_frente{sx}", 0.055, 1.98, (sx * 1.2, -0.9, 0), "Madera", verts=8))
    slope = math.atan2(0.42, 1.95)
    p.append(box(f"{name}_lona", (2.8, 2.25, 0.05), (0, -0.05, 2.1), cloth, bevel=0.02, rot=(slope, 0, 0)))
    p.append(box(f"{name}_faldon", (2.8, 0.04, 0.26), (0, -1.14, 1.72), cloth, bevel=0.015))
    for sx in (-1, 1):
        p.append(box(f"{name}_faldon_lado{sx}", (0.04, 2.0, 0.18), (sx * 1.4, -0.1, 1.98), cloth, bevel=0.015,
                     rot=(slope, 0, 0)))
    # Mostrador.
    p.append(box(f"{name}_mostrador", (2.2, 0.7, 0.08), (0, -0.5, 0.74), "Madera", bevel=0.02))
    p.append(box(f"{name}_frente", (2.1, 0.04, 0.5), (0, -0.84, 0.25), "MaderaOscura", bevel=0.015))
    for sx in (-1, 1):
        p.append(box(f"{name}_pata{sx}", (0.08, 0.6, 0.74), (sx * 1.0, -0.5, 0), "MaderaOscura"))
    top = 0.82
    for i, g in enumerate(goods):
        x = -0.72 + i * 0.72
        if g in ("Manzana", "Naranja", "Pera", "Uva"):
            p.append(lathe(f"{name}_cesta{i}", [(0.0, 0.0), (0.16, 0.0), (0.22, 0.09), (0.23, 0.15)], (x, -0.5, top),
                           "Mimbre", verts=14))
            for k in range(7):
                a = 2 * math.pi * k / 7
                d = 0.11 if k else 0.0
                p.append(ball(f"{name}_fruta{i}{k}", 0.055 if g != "Uva" else 0.04,
                              (x + math.cos(a) * d, -0.5 + math.sin(a) * d, top + 0.15 + (0.04 if k == 0 else 0)), g))
        elif g == "Barro":
            for k, dx in enumerate((-0.14, 0.14)):
                prof = [(0.0, 0.0), (0.09, 0.0), (0.14, 0.08), (0.15, 0.18), (0.08, 0.3), (0.06, 0.34), (0.08, 0.37)]
                p.append(lathe(f"{name}_jarra{i}{k}", prof, (x + dx, -0.45 - 0.08 * k, top), "Barro", verts=14))
        else:   # Telas dobladas, una sobre otra.
            for k in range(3):
                p.append(box(f"{name}_tela{i}{k}", (0.5, 0.42, 0.07), (x, -0.5, top + k * 0.075), g, bevel=0.025,
                             rot=(0, 0, rnd.uniform(-0.08, 0.08))))
    # En el suelo, a un lado: sacos abiertos, un cántaro grande y una cesta.
    for k, (sx, sy) in enumerate(((1.55, -0.55), (1.6, 0.05))):
        p.append(ball(f"{name}_saco{k}", 0.24, (sx, sy, 0.2), "Saco", scale=(1, 1, 1.15)))
        p.append(lathe(f"{name}_saco_boca{k}", [(0.0, 0.0), (0.16, 0.0), (0.18, 0.06)], (sx, sy, 0.43), "Saco", verts=12))
        p.append(cylinder(f"{name}_grano{k}", 0.15, 0.03, (sx, sy, 0.47), "TelaOcre" if k else "Mimbre", verts=12))
    p.append(lathe(f"{name}_cantaro", [(0.0, 0.0), (0.14, 0.0), (0.24, 0.16), (0.25, 0.32), (0.14, 0.52), (0.1, 0.58),
                                        (0.13, 0.62)], (-1.55, -0.4, 0), "Barro", verts=16))
    p.append(lathe(f"{name}_cesta_suelo", [(0.0, 0.0), (0.2, 0.0), (0.27, 0.12), (0.28, 0.22)], (-1.5, 0.3, 0), "Mimbre",
                   verts=14))
    return join(name, p)


def barrel(name, center, scale=1.0):
    """Barril de duelas: panzón, con dos aros oscuros y la tapa."""
    x, y = center
    h = 0.62 * scale
    prof = [(0.0, 0.0), (0.21 * scale, 0.0), (0.26 * scale, h * 0.25), (0.28 * scale, h * 0.5), (0.26 * scale, h * 0.75),
            (0.21 * scale, h), (0.0, h)]
    p = [lathe(f"{name}_cuerpo", prof, (x, y, 0), "Madera", verts=16)]
    for z, r in ((0.2, 0.27), (0.8, 0.27)):
        p.append(torus_ring(f"{name}_aro{z}", r * scale, 0.018 * scale, (x, y, h * z), "MaderaOscura"))
    p.append(cylinder(f"{name}_tapa", 0.19 * scale, 0.02, (x, y, h - 0.005), "MaderaOscura", verts=16))
    return p


def crate(name, center, size=0.55, rot=0.0, z=0.0, fruit=None):
    """Caja de tablas con el marco más oscuro; abierta y con fruta si se da `fruit`."""
    x, y = center
    p = [box(f"{name}_caja", (size, size * 0.8, size * 0.6), (x, y, z), "Madera", bevel=0.02, rot=(0, 0, rot))]
    for k in (0.33, 0.66):
        p.append(box(f"{name}_tabla{k}", (size + 0.01, size * 0.8 + 0.01, 0.02), (x, y, z + size * 0.6 * k), "MaderaOscura",
                     rot=(0, 0, rot)))
    if fruit:
        for i in range(6):
            fx, fy = (i % 3 - 1) * size * 0.27, (i // 3 - 0.5) * size * 0.3
            p.append(ball(f"{name}_fruta{i}", size * 0.12, (x + fx * math.cos(rot) - fy * math.sin(rot),
                                                            y + fx * math.sin(rot) + fy * math.cos(rot), z + size * 0.6),
                          fruit))
    return p


def build_barrels():
    """Barriles del mercado: dos juntos y uno más chico delante."""
    return join("Barriles", barrel("Barril0", (0, 0)) + barrel("Barril1", (0.56, 0.12)) +
                barrel("Barril2", (0.3, -0.48), 0.8))


def build_crates():
    """Cajas del mercado apiladas: dos en el suelo, una encima y otra abierta con manzanas."""
    p = crate("Caja0", (0, 0)) + crate("Caja1", (0.6, 0.05), rot=0.1)
    p += crate("Caja2", (0.28, 0.02), z=0.33, rot=-0.15, size=0.5)
    p += crate("Caja3", (0.25, -0.62), rot=0.3, fruit="Manzana")
    return join("Cajas", p)


def build_cart():
    """Carreta de mano de un vendedor ambulante: caja de tablas sobre dos ruedas, varas para tirar y un
    pie delante; lleva cántaros, una caja de naranjas y un saco."""
    p = [box("Carreta_caja", (1.4, 0.9, 0.08), (0, 0, 0.5), "Madera", bevel=0.02)]
    for sy in (-1, 1):
        p.append(box(f"Carreta_lado{sy}", (1.4, 0.06, 0.22), (0, sy * 0.42, 0.58), "MaderaOscura", bevel=0.015))
        p.append(cylinder(f"Carreta_rueda{sy}", 0.36, 0.08, (0.1, sy * 0.52, 0.36), "Madera", verts=16,
                          rot=(math.radians(90), 0, 0), bevel=0.02))
        p.append(cylinder(f"Carreta_cubo{sy}", 0.08, 0.12, (0.1, sy * 0.55, 0.36), "MaderaOscura", verts=10,
                          rot=(math.radians(90), 0, 0)))
        p.append(cylinder(f"Carreta_vara{sy}", 0.035, 1.1, (-0.6, sy * 0.36, 0.52), "Madera", verts=8,
                          rot=(0, math.radians(-100), 0)))
    for sx in (-1, 1):
        p.append(box(f"Carreta_frente{sx}", (0.06, 0.9, 0.22), (sx * 0.67, 0, 0.58), "MaderaOscura", bevel=0.015))
    p.append(box("Carreta_pie", (0.06, 0.06, 0.5), (-0.55, 0, 0), "MaderaOscura"))
    for i, (x, y) in enumerate(((0.35, -0.2), (0.45, 0.18))):
        prof = [(0.0, 0.0), (0.1, 0.0), (0.16, 0.1), (0.17, 0.22), (0.09, 0.36), (0.07, 0.4), (0.09, 0.43)]
        p.append(lathe(f"Carreta_jarra{i}", prof, (x, y, 0.54), "Barro", verts=14))
    p += crate("Carreta_naranjas", (-0.22, 0.05), size=0.5, z=0.54, rot=0.1, fruit="Naranja")
    p.append(ball("Carreta_saco", 0.2, (0.05, 0.22, 0.72), "Saco", scale=(1, 1, 0.8)))
    return join("Carreta", p)


def build_mat(name, cloth, border, goods):
    """Manta de un vendedor sentado en el suelo, con la mercancía encima y un taburete."""
    p = [box(f"{name}_tela", (1.5, 1.1, 0.02), (0, 0, 0), cloth, bevel=0.008)]
    for sy in (-1, 1):
        p.append(box(f"{name}_borde{sy}", (1.5, 0.12, 0.024), (0, sy * 0.45, 0), border))
    for i, g in enumerate(goods):
        x = -0.48 + i * 0.48
        if g == "Barro":
            for k, dx in enumerate((-0.1, 0.12)):
                prof = [(0.0, 0.0), (0.08, 0.0), (0.13, 0.08), (0.14, 0.17), (0.07, 0.28), (0.05, 0.31), (0.07, 0.34)]
                p.append(lathe(f"{name}_jarra{i}{k}", prof, (x + dx, -0.05 + 0.12 * k, 0.02), "Barro", verts=14))
        else:
            p.append(lathe(f"{name}_cesta{i}", [(0.0, 0.0), (0.15, 0.0), (0.2, 0.08), (0.21, 0.13)], (x, 0, 0.02),
                           "Mimbre", verts=14))
            for k in range(6):
                a = 2 * math.pi * k / 6
                d = 0.1 if k else 0.0
                p.append(ball(f"{name}_fruta{i}{k}", 0.05, (x + math.cos(a) * d, math.sin(a) * d, 0.15), g))
    p.append(cylinder(f"{name}_taburete", 0.17, 0.32, (0, 0.8, 0), "Madera", verts=12, bevel=0.02))
    return join(name, p)


def build_peak_tent(name, cloth):
    """Tienda de lona a dos aguas sobre cuatro postes y una cumbrera, abierta delante: mostrador bajo con
    telas y cántaros, y un barril al lado."""
    p = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(cylinder(f"{name}_poste{sx}{sy}", 0.055, 1.75, (sx * 1.25, sy * 0.95, 0), "Madera", verts=8))
        p.append(cylinder(f"{name}_mastil{sx}", 0.06, 2.55, (sx * 1.25, 0, 0), "Madera", verts=8))
    p.append(cylinder(f"{name}_cumbrera", 0.05, 2.8, (-1.4, 0, 2.5), "MaderaOscura", verts=8, rot=(0, math.radians(90), 0)))
    slope = math.atan2(0.8, 1.05)
    for sy in (-1, 1):
        p.append(box(f"{name}_tela{sy}", (2.85, 1.35, 0.045), (0, sy * 0.53, 2.12), cloth, bevel=0.02,
                     rot=(-slope * sy, 0, 0)))
        p.append(box(f"{name}_faldon{sy}", (2.85, 0.04, 0.24), (0, sy * 1.06, 1.62), cloth, bevel=0.015))
    p.append(box(f"{name}_mostrador", (2.0, 0.6, 0.07), (0, -0.45, 0.62), "Madera", bevel=0.02))
    for sx in (-1, 1):
        p.append(box(f"{name}_pata{sx}", (0.07, 0.5, 0.62), (sx * 0.9, -0.45, 0), "MaderaOscura"))
    for i, g in enumerate(("TelaRojaTelar", "TelaOcre", "TelaCrema")):
        for k in range(2):
            p.append(box(f"{name}_tela_venta{i}{k}", (0.5, 0.4, 0.07), (-0.62 + i * 0.62, -0.45, 0.69 + k * 0.075), g,
                         bevel=0.025))
    p += barrel(f"{name}_barril", (1.6, -0.6), 0.9)
    return join(name, p)


def build_trough():
    """Bebedero: tronco ahuecado con agua (referencias/recortes/abrevadero.png)."""
    parts = log("Abrevadero", 0.3, 1.8, (0, 0, 0.3), bevel=0.04)
    cutter = box("Abrevadero_hueco", (1.55, 0.42, 0.4), (0, 0, 0.42), "Hueco", bevel=0.1)
    mod = parts[0].modifiers.new("hueco", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter)
    parts.append(box("Abrevadero_agua", (1.5, 0.38, 0.02), (0, 0, 0.47), "AguaBebedero"))
    # Dos calzos para que no ruede.
    for sx in (-1, 1):
        parts.append(box(f"Abrevadero_calzo{sx}", (0.12, 0.5, 0.08), (sx * 0.6, 0, 0), "MaderaOscura", bevel=0.02))
    return join("Abrevadero", parts)


def build_loom():
    """Telar (referencias/recortes/telar.png): marco de madera con patas de apoyo, hilos de urdimbre crema
    y la tela tejida abajo, roja con franjas crema."""
    p = []
    h, w = 1.55, 1.1
    frame = []
    for sx in (-1, 1):
        frame.append(box(f"Telar_lado{sx}", (0.08, 0.08, h), (sx * w / 2, 0, 0), "Madera", bevel=0.02))
        # Pata de apoyo por detrás: del suelo (y = 0,55) hasta el lateral, a 1,25 m de alto.
        p.append(box(f"Telar_pata{sx}", (0.07, 0.07, 1.37), (sx * w / 2, 0.55, 0), "MaderaOscura", bevel=0.015,
                     rot=(math.atan2(0.55, 1.25), 0, 0)))
    for z in (0.12, h - 0.1, 0.55):
        frame.append(cylinder(f"Telar_barra{z}", 0.04, w + 0.12, (-(w + 0.12) / 2, 0, z), "MaderaOscura", verts=8,
                              rot=(0, math.radians(90), 0)))
    for i in range(16):
        x = -w / 2 + 0.09 + i * (w - 0.18) / 15
        frame.append(cylinder(f"Telar_hilo{i}", 0.006, h - 0.75, (x, 0, 0.6), "HiloCrema", verts=4))
    frame.append(box("Telar_tela", (w - 0.14, 0.02, 0.42), (0, 0, 0.13), "TelaRojaTelar"))
    for z in (0.22, 0.38):
        frame.append(box(f"Telar_franja{z}", (w - 0.14, 0.025, 0.04), (0, 0, z), "HiloCrema"))
    return join("Telar", p + frame)


def torus_ring(name, major, minor, loc, mat):
    """Aro horizontal (borde o franja de cesta)."""
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=20, minor_segments=5,
                                     location=loc)
    obj = bpy.context.active_object
    obj.name = name
    return _finish(obj, mat, smooth=True)


def torus_part(name, major, minor, loc, mat):
    """Aro (media vuelta hacia arriba, como el asa de un cubo)."""
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=24, minor_segments=6,
                                     location=loc, rotation=(math.radians(90), 0, 0))
    obj = bpy.context.active_object
    obj.name = name
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y < -0.01], context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    return _finish(obj, mat, smooth=True)

def build_props():
    props = []
    props.append(build_well())

    p = [lathe("Horno_cuerpo", [(0.42, 0), (0.44, 0.3), (0.4, 0.65), (0.26, 0.88), (0.2, 0.9)], (0, 0, 0), "Barro"),
         box("Horno_boca", (0.3, 0.12, 0.28), (0, -0.4, 0.12), "Hueco", bevel=0.05)]
    props.append(join("Horno", p))

    p = [box("Banco_asiento", (1.6, 0.4, 0.08), (0, 0, 0.42), "Madera", bevel=0.03)]
    for side in (-1, 1):
        p.append(box(f"Banco_pata{side}", (0.12, 0.34, 0.42), (side * 0.62, 0, 0), "MaderaOscura", bevel=0.02))
    props.append(join("Banco", p))

    props.append(join("Cantaro", [lathe("Cantaro_cuerpo", [(0.12, 0), (0.22, 0.12), (0.24, 0.3), (0.16, 0.5),
                                                          (0.09, 0.58), (0.11, 0.64)], (0, 0, 0), "Barro")]))
    props.append(join("Cesta", [lathe("Cesta_cuerpo", [(0.2, 0), (0.26, 0.12), (0.28, 0.25), (0.27, 0.27)],
                                      (0, 0, 0), "Mimbre")]))
    # Leña: troncos apilados.
    p = []
    for row in range(3):
        for i in range(4 - row):
            x = (i - (3 - row) * 0.5) * 0.24
            p.append(cylinder(f"Lena{row}{i}", 0.11, 1.1, (-0.55, x, 0.11 + row * 0.2), "Madera", verts=8,
                              rot=(0, math.radians(90), 0)))
    props.append(join("Lena", p))
    # Tramo de cerca de 2 m: postes algo torcidos y dos travesaños.
    p = []
    for i, x in enumerate((-1.0, 0.0, 1.0)):
        p.append(box(f"Cerca_poste{i}", (0.12, 0.12, 0.85), (x, 0, 0), "Madera", bevel=0.03,
                     rot=(random.uniform(-0.05, 0.05), random.uniform(-0.05, 0.05), 0)))
    for z in (0.35, 0.65):
        p.append(box(f"Cerca_tabla{z}", (2.1, 0.06, 0.1), (0, 0.05, z), "MaderaOscura", bevel=0.02,
                     rot=(0, random.uniform(-0.03, 0.03), 0)))
    props.append(join("Cerca", p))
    # Puesto del alfarero: mesa con toldo y cántaros.
    p = [box("Puesto_mesa", (2.0, 0.8, 0.08), (0, 0, 0.8), "Madera", bevel=0.03)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(box(f"Puesto_pata{sx}{sy}", (0.08, 0.08, 0.8), (sx * 0.9, sy * 0.32, 0), "MaderaOscura"))
            p.append(cylinder(f"Puesto_poste{sx}{sy}", 0.04, 2.1, (sx * 1.0, sy * 0.4, 0), "Madera", verts=8))
    p.append(box("Puesto_toldo", (2.3, 1.1, 0.05), (0, 0, 2.1), "TelaAzul", bevel=0.02, rot=(math.radians(8), 0, 0)))
    for i, x in enumerate((-0.6, 0.0, 0.55)):
        s = 0.7 + 0.15 * i
        prof = [(0.12 * s, 0), (0.22 * s, 0.12 * s), (0.24 * s, 0.3 * s), (0.16 * s, 0.5 * s), (0.1 * s, 0.6 * s)]
        p.append(lathe(f"Puesto_cantaro{i}", prof, (x, 0, 0.88), "Barro"))
    props.append(join("Puesto", p))

    # --- Patios y techos ---
    props.append(join("Maceta", [lathe("Maceta_cuerpo", [(0.13, 0), (0.17, 0.08), (0.2, 0.26), (0.22, 0.3),
                                                        (0.2, 0.32)], (0, 0, 0), "Barro")]))
    props.append(join("Saco", [lathe("Saco_cuerpo", [(0.2, 0), (0.27, 0.1), (0.28, 0.3), (0.2, 0.48), (0.08, 0.56),
                                                    (0.1, 0.62)], (0, 0, 0), "Saco")]))
    p = [box("Alfombra_base", (1.7, 1.0, 0.03), (0, 0, 0.0), "TelaRosa", bevel=0.01)]
    for i, (y, c) in enumerate(((-0.3, "TelaAzul"), (0.0, "TelaOcre"), (0.3, "TelaAzul"))):
        p.append(box(f"Alfombra_raya{i}", (1.7, 0.1, 0.035), (0, y, 0.0), c))
    props.append(join("Alfombra", p))
    p = []
    for side in (-1, 1):
        p.append(cylinder(f"Tendedero_poste{side}", 0.05, 1.75, (side * 1.4, 0, 0), "Madera", verts=8))
    p.append(cylinder("Tendedero_cuerda", 0.012, 2.8, (-1.4, 0, 1.65), "Cuerda", verts=6, rot=(0, math.radians(90), 0)))
    for i, (x, c, hh) in enumerate(((-0.8, "TelaAzul", 0.7), (0.0, "TelaRosa", 0.55), (0.75, "TelaVerde", 0.8))):
        p.append(box(f"Tendedero_tela{i}", (0.6, 0.03, hh), (x, 0, 1.65 - hh), c, bevel=0.01,
                     rot=(math.radians(random.uniform(-6, 6)), 0, 0)))
    props.append(join("Tendedero", p))
    p = []
    for side in (-1, 1):
        p.append(box(f"Telar_lado{side}", (0.08, 0.08, 1.5), (side * 0.65, 0, 0), "Madera", bevel=0.02))
    for z in (0.25, 1.4):
        p.append(cylinder(f"Telar_rodillo{z}", 0.05, 1.4, (-0.7, 0, z), "MaderaOscura", verts=8,
                          rot=(0, math.radians(90), 0)))
    p.append(box("Telar_tela", (1.15, 0.02, 0.55), (0, 0, 0.3), "TelaRosa"))
    for i in range(12):
        x = -0.55 + i * 0.1
        p.append(cylinder(f"Telar_hilo{i}", 0.006, 0.55, (x, 0, 0.85), "Saco", verts=4))
    props.append(join("Telar", p))
    p = [box("Abrevadero_caja", (1.8, 0.6, 0.45), (0, 0, 0), "Madera", bevel=0.04),
         box("Abrevadero_agua", (1.6, 0.42, 0.04), (0, 0, 0.38), "Agua")]
    props.append(join("Abrevadero", p))

    # --- Obra del arca ---
    p = [box("Caballete_viga", (1.4, 0.14, 0.14), (0, 0, 0.75), "Madera", bevel=0.02)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(box(f"Caballete_pata{sx}{sy}", (0.08, 0.08, 0.85), (sx * 0.55, sy * 0.18, 0), "MaderaOscura",
                         rot=(math.radians(-14 * sy), 0, 0)))
    p.append(box("Caballete_tablon", (2.4, 0.32, 0.06), (0.2, 0, 0.82), "Madera", bevel=0.01,
                 rot=(0, 0, math.radians(4))))
    props.append(join("Caballete", p))
    p = []
    for i in range(9):
        layer, k = divmod(i, 3)
        p.append(box(f"Tablones{i}", (2.6, 0.3, 0.07), (random.uniform(-0.08, 0.08), (k - 1) * 0.32, layer * 0.075),
                     "Madera" if i % 2 else "MaderaOscura", bevel=0.01, rot=(0, 0, math.radians(random.uniform(-2, 2)))))
    props.append(join("Tablones", p))
    p = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(cylinder(f"Andamio_poste{sx}{sy}", 0.05, 3.0, (sx * 1.2, sy * 0.45, 0), "Madera", verts=8))
    for z in (1.4, 2.7):
        p.append(box(f"Andamio_plataforma{z}", (2.6, 1.0, 0.06), (0, 0, z), "Madera", bevel=0.01))
        for sy in (-1, 1):
            p.append(cylinder(f"Andamio_travesano{z}{sy}", 0.03, 2.4, (-1.2, sy * 0.45, z - 0.25), "MaderaOscura",
                              verts=6, rot=(0, math.radians(90), 0)))
    for i in range(6):
        p.append(cylinder(f"Andamio_peldano{i}", 0.025, 0.4, (-1.35, -0.2, 0.25 + i * 0.42), "MaderaOscura", verts=6,
                          rot=(math.radians(90), 0, 0)))
    props.append(join("Andamio", p))
    p = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(cylinder(f"Toldo_poste{sx}{sy}", 0.05, 2.0 if sy < 0 else 1.6, (sx * 1.4, sy * 1.1, 0), "Madera",
                              verts=8))
    p.append(box("Toldo_tela", (3.1, 2.5, 0.04), (0, 0, 1.8), "TelaOcre", bevel=0.02, rot=(math.radians(9), 0, 0)))
    p.append(box("Toldo_estera", (2.2, 1.5, 0.03), (0, 0, 0.0), "Mimbre", bevel=0.01))
    props.append(join("Toldo", p))
    p = []
    for i in range(3):
        a = 2 * math.pi * i / 3
        p.append(box(f"Olla_piedra{i}", (0.22, 0.22, 0.2), (math.cos(a) * 0.32, math.sin(a) * 0.32, 0), "Piedra",
                     bevel=0.06))
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.5
        p.append(cylinder(f"Olla_tronco{i}", 0.05, 0.5, (math.cos(a) * 0.25, math.sin(a) * 0.25, 0.05), "MaderaOscura",
                          verts=6, rot=(0, math.radians(80), a)))
        p.append(cylinder(f"Olla_llama{i}", 0.09, 0.28, (math.cos(a) * 0.1, math.sin(a) * 0.1, 0.06), "Fuego",
                          verts=6, top_radius=0.0))
    p.append(lathe("Olla_cuerpo", [(0.2, 0.2), (0.3, 0.3), (0.32, 0.45), (0.28, 0.6), (0.3, 0.64)], (0, 0, 0), "Brea"))
    props.append(join("OllaBrea", p))
    p = [box("Mesa_tablero", (1.8, 0.75, 0.08), (0, 0, 0.78), "Madera", bevel=0.02)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.append(box(f"Mesa_pata{sx}{sy}", (0.09, 0.09, 0.78), (sx * 0.8, sy * 0.3, 0), "MaderaOscura"))
    p.append(cylinder("Mesa_mazo_mango", 0.025, 0.4, (-0.5, 0.1, 0.9), "Madera", verts=6, rot=(0, math.radians(90), 0.3)))
    p.append(cylinder("Mesa_mazo_cabeza", 0.07, 0.2, (-0.55, 0.0, 0.86), "MaderaOscura", verts=8,
                      rot=(math.radians(90), 0, 0.3)))
    p.append(box("Mesa_sierra", (0.6, 0.12, 0.015), (0.3, -0.1, 0.87), "Piedra", rot=(0, 0, 0.2)))
    p.append(box("Mesa_sierra_mango", (0.14, 0.05, 0.05), (0.62, -0.03, 0.88), "MaderaOscura", rot=(0, 0, 0.2)))
    for i in range(4):
        p.append(cylinder(f"Mesa_clavija{i}", 0.02, 0.18, (0.0 + i * 0.07, 0.25, 0.86), "MaderaOscura", verts=5,
                          rot=(0, math.radians(90), i)))
    props.append(join("MesaTrabajo", p))

    # Murete de adobe (tramo de 2 m) para cerrar patios compartidos.
    props.append(join("Murete", [box("Murete_cuerpo", (2.0, 0.34, 1.05), (0, 0, 0), "AdobeSombra", bevel=0.12),
                                 box("Murete_remate", (2.04, 0.4, 0.1), (0, 0, 1.0), "Adobe", bevel=0.04)]))

    # --- Plaza y mercado ---
    for name, cloth in (("TiendaRosa", "TelaRosa"), ("TiendaAzul", "TelaAzul"), ("TiendaVerde", "TelaVerde")):
        # Toldo de mercado a dos aguas sobre cuatro postes, con mostrador y mercancía.
        p = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                p.append(cylinder(f"{name}_poste{sx}{sy}", 0.05, 1.9, (sx * 1.3, sy * 0.9, 0), "Madera", verts=8))
        p.append(cylinder(f"{name}_cumbrera", 0.05, 2.9, (-1.45, 0, 2.35), "MaderaOscura", verts=8,
                          rot=(0, math.radians(90), 0)))
        for sy in (-1, 1):
            p.append(box(f"{name}_tela{sy}", (2.9, 1.15, 0.04), (0, sy * 0.52, 2.13), cloth, bevel=0.02,
                         rot=(math.radians(-27 * sy), 0, 0)))
        p.append(box(f"{name}_mostrador", (2.3, 0.6, 0.08), (0, -0.55, 0.78), "Madera", bevel=0.02))
        for sx in (-1, 1):
            p.append(box(f"{name}_pata{sx}", (0.08, 0.5, 0.78), (sx * 1.05, -0.55, 0), "MaderaOscura"))
        goods = {"TiendaRosa": ["Barro", "Barro", "Barro"], "TiendaAzul": ["TelaRosa", "TelaOcre", "TelaVerde"],
                 "TiendaVerde": ["TelaVerde", "TelaOcre", "Mimbre"]}[name]
        for i, g in enumerate(goods):
            x = -0.75 + i * 0.75
            if g == "Barro":
                prof = [(0.1, 0), (0.18, 0.1), (0.2, 0.25), (0.13, 0.4), (0.09, 0.46)]
                p.append(lathe(f"{name}_bien{i}", prof, (x, -0.55, 0.86), g))
            elif g == "Mimbre":
                p.append(lathe(f"{name}_bien{i}", [(0.16, 0), (0.22, 0.1), (0.23, 0.18)], (x, -0.55, 0.86), g))
                for k in range(3):
                    p.append(cylinder(f"{name}_fruta{i}{k}", 0.06, 0.1, (x - 0.06 + k * 0.06, -0.55, 0.98), "TelaOcre",
                                      verts=8))
            else:
                p.append(box(f"{name}_bien{i}", (0.55, 0.45, 0.16), (x, -0.55, 0.86), g, bevel=0.04))
        p.append(lathe(f"{name}_cesta", [(0.2, 0), (0.26, 0.12), (0.28, 0.25), (0.27, 0.27)], (1.6, 0.4, 0), "Mimbre"))
        props.append(join(name, p))
    # Fogata de la plaza: anillo de piedras, troncos y llamas.
    p = []
    for i in range(9):
        a = 2 * math.pi * i / 9
        p.append(box(f"Fogata_piedra{i}", (0.26, 0.22, 0.18), (math.cos(a) * 0.6, math.sin(a) * 0.6, 0), "Piedra",
                     bevel=0.07, rot=(0, 0, a)))
    for i in range(4):
        a = 2 * math.pi * i / 4 + 0.4
        p.append(cylinder(f"Fogata_tronco{i}", 0.06, 0.65, (math.cos(a) * 0.32, math.sin(a) * 0.32, 0.04), "MaderaOscura",
                          verts=6, rot=(0, math.radians(70), a)))
    for i, (dx, dy, hh) in enumerate(((0, 0, 0.5), (0.12, 0.08, 0.35), (-0.1, 0.1, 0.32), (0.02, -0.12, 0.3))):
        p.append(cylinder(f"Fogata_llama{i}", 0.13 if i == 0 else 0.09, hh, (dx, dy, 0.05), "Fuego", verts=6,
                          top_radius=0.0))
    props.append(join("Fogata", p))
    # Mesa larga de la plaza.
    p = [box("Mesa_tabla", (2.2, 0.8, 0.08), (0, 0, 0.74), "Madera", bevel=0.02)]
    for sx in (-1, 1):
        p.append(box(f"Mesa_caballete{sx}", (0.1, 0.65, 0.74), (sx * 0.85, 0, 0), "MaderaOscura", bevel=0.02))
    p.append(lathe("Mesa_jarra", [(0.07, 0), (0.1, 0.06), (0.1, 0.16), (0.06, 0.24), (0.07, 0.27)], (-0.5, 0.1, 0.82),
                   "Barro"))
    p.append(lathe("Mesa_cuenco", [(0.08, 0), (0.15, 0.06), (0.16, 0.08)], (0.4, -0.1, 0.82), "Barro"))
    props.append(join("Mesa", p))
    # Puente de piedra y madera: arco de piedra sobre el río, tablero de madera y barandas.
    span, width = 9.0, 2.6
    p = []
    blocks = 13
    for i in range(blocks):
        t = (i + 0.5) / blocks
        a = math.pi * t
        x = -span * 0.42 * math.cos(a)
        z = 0.15 + 1.35 * math.sin(a) - 1.45
        p.append(box(f"Puente_dovela{i}", (span * 0.85 / blocks + 0.05, width, 0.42), (x, 0, z), "Piedra", bevel=0.06,
                     rot=(0, -(a - math.pi * 0.5) * 0.9, 0)))
    for side in (-1, 1):
        p.append(box(f"Puente_estribo{side}", (1.4, width + 0.3, 1.7), (side * (span * 0.5 - 0.3), 0, -1.55), "Piedra",
                     bevel=0.12))
    planks = 18
    for i in range(planks):
        x = -span * 0.5 + (i + 0.5) * span / planks
        lift = 0.18 * (1 - (x / (span * 0.5)) ** 2)
        p.append(box(f"Puente_tabla{i}", (span / planks - 0.04, width, 0.1), (x, 0, 0.05 + lift), "Madera" if i % 3 else
                     "MaderaOscura", bevel=0.015))
    for sy in (-1, 1):
        for i in range(5):
            x = -span * 0.5 + 0.4 + i * (span - 0.8) / 4
            lift = 0.18 * (1 - (x / (span * 0.5)) ** 2)
            p.append(box(f"Puente_poste{sy}{i}", (0.13, 0.13, 0.85), (x, sy * (width * 0.5 - 0.08), 0.1 + lift),
                         "MaderaOscura", bevel=0.03))
        p.append(box(f"Puente_baranda{sy}", (span - 0.6, 0.1, 0.1), (0, sy * (width * 0.5 - 0.08), 0.95), "Madera",
                     bevel=0.02))
    props.append(join("PuentePiedra", p))
    return props


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = argv[0]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objs = build_houses() + build_props()
    # Los que mezclan materiales se hacen por script (los generados salían mal pintados).
    nuevos = {"Fogata": build_campfire, "Cesta": build_baskets, "Abrevadero": build_trough, "Telar": build_loom,
              "Lena": build_firewood, "Tocon": build_stump, "TroncoAsiento": build_log_seat,
              "LonaCrema": lambda: build_canvas_stall("LonaCrema", "LonaCrema", ["Manzana", "Barro", "Naranja"]),
              "LonaAzul": lambda: build_canvas_stall("LonaAzul", "LonaAzul", ["TelaRosa", "TelaOcre", "TelaCrema"]),
              "LonaVerde": lambda: build_canvas_stall("LonaVerde", "LonaVerde", ["Pera", "Uva", "Barro"]),
              "LonaSalvia": lambda: build_canvas_stall("LonaSalvia", "LonaSalvia", ["Barro", "Manzana", "TelaVerde"]),
              "LonaGris": lambda: build_canvas_stall("LonaGris", "LonaGris", ["Uva", "Naranja", "Barro"]),
              "TiendaPicoCrema": lambda: build_peak_tent("TiendaPicoCrema", "LonaCrema"),
              "TiendaPicoAzul": lambda: build_peak_tent("TiendaPicoAzul", "LonaAzul"),
              "Barriles": build_barrels, "Cajas": build_crates, "Carreta": build_cart,
              "MantaRoja": lambda: build_mat("MantaRoja", "TelaRoja", "TelaCrema", ["Barro", "Manzana", "Pera"]),
              "MantaAzul": lambda: build_mat("MantaAzul", "TelaAzulFuerte", "TelaCrema", ["Naranja", "Barro", "Uva"])}
    for o in [o for o in objs if o.name in nuevos]:
        objs.remove(o)
        bpy.data.objects.remove(o)
    objs += [f() for f in nuevos.values()]
    # Repartidas en fila para verlas bien en Blender; en Godot se usa cada una por separado.
    x = 0.0
    for o in objs:
        o.location = (x, 0, 0)
        x += o.dimensions.x + 2.0
    for o in objs:
        tris = sum(len(p.vertices) - 2 for p in o.data.polygons)
        print("pieza", o.name, "medidas", tuple(round(v, 2) for v in o.dimensions), "triangulos", tris)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=True)
    print("ALDEA OK ->", out)


main()
