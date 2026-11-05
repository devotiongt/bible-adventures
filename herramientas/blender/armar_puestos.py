"""Arma los cuatro puestos del mercado a partir del puesto vacío y la mercancía generados por separado
(referencias/mercado_piezas.png, procesados con procesar_generados.py; las piezas van en
herramientas/blender/objetos/piezas_puesto/).

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/armar_puestos.py

Para cada puesto: copia el puesto vacío, pinta su toldo (las caras de tela, alfa 0) del color del puesto
(las rayas con el crema las dibuja el shader del juego), y coloca su mercancía sobre el mostrador.
Guarda herramientas/blender/objetos/puesto_<tipo>.blend; luego se exporta con exportar_objetos.py.
"""

import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OBJ = os.path.join(ROOT, "herramientas/blender/objetos")

# Color del toldo (sRGB) y mercancía: (pieza, x, y, giro en grados, escala), en fracción del mostrador
# (x de -1 a 1 a lo ancho, y de -1 delante a 1 detrás).
PUESTOS = {
    "puesto_ceramica": ((0.86, 0.38, 0.35), [("cantaros", -0.35, 0.0, 10, 0.75), ("cantaros", 0.4, 0.05, 200, 0.65)]),
    "puesto_telas": ((0.38, 0.58, 0.80), [("rollos_crema", -0.42, 0.05, 0, 1.0), ("telas_dobladas", 0.45, -0.05, -8, 1.0)]),
    "puesto_telas2": ((0.36, 0.70, 0.72), [("rollos_colores", -0.42, 0.05, 0, 1.0), ("telas_dobladas", 0.45, -0.05, 6, 1.0)]),
    "puesto_frutas": ((0.50, 0.70, 0.30), [("caja_manzanas", -0.48, -0.25, 2, 0.95), ("caja_naranjas", 0.48, -0.25, -3, 0.95),
                                           ("caja_peras", -0.48, 0.45, -2, 0.95), ("caja_uvas", 0.48, 0.45, 4, 0.95)]),
}


def load(name):
    # Las piezas del puesto están en objetos/piezas_puesto/; los cántaros, en objetos/ (se usan también solos).
    path = os.path.join(OBJ, "piezas_puesto", name + ".blend")
    if not os.path.exists(path):
        path = os.path.join(OBJ, name + ".blend")
    with bpy.data.libraries.load(path) as (src, dst):
        dst.objects = list(src.objects)
    obj = next(o for o in dst.objects if o is not None and o.type == "MESH")
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (0, 0, 0)
    return obj


def counter(stall):
    """Altura de la superficie del mostrador y medio ancho y medio fondo de la zona libre entre postes."""
    co = np.array([v.co for v in stall.data.vertices])
    h0, h1 = co[:, 2].min(), co[:, 2].max()
    ups = [f.center.z for f in stall.data.polygons
           if f.normal.z > 0.85 and h0 + (h1 - h0) * 0.25 < f.center.z < h0 + (h1 - h0) * 0.55
           and abs(f.center.x) < np.abs(co[:, 0]).max() * 0.6]
    hist, edges = np.histogram(ups, bins=30)
    top = float(edges[hist.argmax()] + (edges[1] - edges[0]) / 2)
    return top, np.abs(co[:, 0]).max() * 0.72, np.abs(co[:, 1]).max() * 0.55


# Toldo nuevo (el generado salía fundido con los postes). Medidas del puesto vacío, en metros.
CORTE = 1.2                     # Por encima de esto se quita todo (tela y puntas de los postes).
POSTE_X, POSTE_Y, POSTE_R = 1.01, 0.585, 0.105
TOLDO_DELANTE, TOLDO_DETRAS = 1.92, 2.18    # Altura del toldo delante y detrás (cae hacia delante).
TOLDO_X, TOLDO_Y0, TOLDO_Y1 = 1.19, -0.86, 0.78
ONDA = 0.34                     # Ancho de cada onda del faldón: igual que una raya (shaders/props.gdshader).
MADERA = (0.62, 0.40, 0.24)


def _colored(bm_fill, color, alpha):
    me = bpy.data.meshes.new("pieza")
    bm = bmesh.new()
    bm_fill(bm)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("pieza", me)
    bpy.context.scene.collection.objects.link(obj)
    attr = me.color_attributes.new("Color", "BYTE_COLOR", "CORNER")
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color]
    for d in attr.data:
        d.color = (lin[0], lin[1], lin[2], alpha)
    for f in me.polygons:
        f.use_smooth = True
    return obj


def _cut_top(stall):
    bm = bmesh.new()
    bm.from_mesh(stall.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z > CORTE], context="FACES")
    bm.to_mesh(stall.data)
    bm.free()


def _awning_height(y):
    t = (y - TOLDO_Y0) / (TOLDO_Y1 - TOLDO_Y0)
    return TOLDO_DELANTE + (TOLDO_DETRAS - TOLDO_DELANTE) * t + 0.07 * np.sin(np.pi * t)   # Algo abombado.


def _new_top(color):
    """Remates de los postes, vigas y el toldo con su faldón de ondas delante (alfa 0: el shader le pone
    las rayas)."""
    parts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            top = _awning_height(sy * POSTE_Y) - 0.04

            def post(bm, sx=sx, sy=sy, top=top):
                # Empieza bajo el corte para tapar la unión con el poste generado.
                bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=POSTE_R, radius2=POSTE_R * 0.85,
                                      depth=top - CORTE + 0.2)
                bmesh.ops.translate(bm, vec=(sx * POSTE_X, sy * POSTE_Y, (top + CORTE - 0.2) / 2), verts=bm.verts)
            parts.append(_colored(post, MADERA, 1.0))
    for sy in (-1, 1):
        def beam(bm, sy=sy):
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.055, radius2=0.055, depth=POSTE_X * 2 + 0.3)
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(np.pi / 2, 3, "Y"))
            bmesh.ops.translate(bm, vec=(0, sy * POSTE_Y, _awning_height(sy * POSTE_Y) - 0.07), verts=bm.verts)
        parts.append(_colored(beam, MADERA, 1.0))

    def cloth(bm):
        nx, ny = 56, 18
        xs = np.linspace(-TOLDO_X, TOLDO_X, nx + 1)
        ys = np.linspace(TOLDO_Y0, TOLDO_Y1, ny + 1)
        grid = [[bm.verts.new((x, y, _awning_height(y))) for x in xs] for y in ys]
        for j in range(ny):
            for i in range(nx):
                bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
        # Faldón delante: cuelga y acaba en ondas (una por raya).
        front = grid[0]
        top_z = _awning_height(TOLDO_Y0)
        low = []
        for i, x in enumerate(xs):
            u = ((x + TOLDO_X) / ONDA) % 1.0 * 2.0 - 1.0
            drop = 0.12 + 0.09 * np.sqrt(max(0.0, 1.0 - u * u))
            low.append(bm.verts.new((x, TOLDO_Y0 - 0.01, top_z - drop)))
        for i in range(nx):
            bm.faces.new((low[i], low[i + 1], front[i + 1], front[i]))
        # Grosor de la tela.
        geom = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
        bmesh.ops.translate(bm, vec=(0, 0.0, -0.03),
                            verts=[v for v in geom["geom"] if isinstance(v, bmesh.types.BMVert)])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    parts.append(_colored(cloth, color, 0.0))
    return parts


def paint_awning(obj, color):
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color]
    attr = obj.data.color_attributes["Color"]
    for d in attr.data:
        if d.color[3] < 0.35:
            d.color = (lin[0], lin[1], lin[2], d.color[3])


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for name, (awning, goods) in PUESTOS.items():
        stall = load("puesto_vacio")
        stall.data = stall.data.copy()
        top, xh, yh = counter(stall)
        _cut_top(stall)
        parts = _new_top(awning)
        for piece, fx, fy, rot, scale in goods:
            g = load(piece)
            g.data = g.data.copy()
            g.scale = (scale, scale, scale)
            g.rotation_euler = (0, 0, np.radians(rot))
            g.location = (fx * xh, fy * yh, top - 0.005)
            parts.append(g)
        bpy.ops.object.select_all(action="DESELECT")
        for o in parts:
            o.select_set(True)
        stall.select_set(True)
        bpy.context.view_layer.objects.active = stall
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        bpy.ops.object.join()
        stall.name = name
        stall.data.name = name
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OBJ, name + ".blend"), copy=True)
        print("PUESTO", name, "mostrador a", round(top, 2), "m")
        bpy.ops.wm.read_factory_settings(use_empty=True)


main()
