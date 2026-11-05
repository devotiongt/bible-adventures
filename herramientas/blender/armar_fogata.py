"""Arma la fogata con sus dos piezas generadas por separado (referencias/fogata_piezas.png, procesadas con
procesar_generados.py en herramientas/blender/objetos/piezas_fogata/): el anillo de piedras con su ceniza y
los troncos en tipi en el centro. Sin llama: el fuego va aparte, animado en el juego.

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/armar_fogata.py

La ceniza sale del generador del mismo color que las piedras: se pinta aparte, por posición (lo bajo y de
dentro del anillo). Guarda herramientas/blender/objetos/fogata.blend; luego se exporta con exportar_objetos.py.
"""

import os

import bpy
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OBJ = os.path.join(ROOT, "herramientas/blender/objetos")
PIEDRA = (0.62, 0.58, 0.53)        # sRGB: el gris cálido del pozo (el generado sale casi blanco).
CENIZA = (0.46, 0.43, 0.40)        # Algo más oscura que las piedras.
CENIZA_ALTO = 0.07                 # Metros: lo que queda por debajo, dentro del anillo, es ceniza.
CENIZA_RADIO = 0.62                # Fracción del radio del anillo.


def load(name):
    with bpy.data.libraries.load(os.path.join(OBJ, "piezas_fogata", name + ".blend")) as (src, dst):
        dst.objects = list(src.objects)
    obj = next(o for o in dst.objects if o is not None and o.type == "MESH")
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (0, 0, 0)
    return obj


def _linear(color):
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color]


def paint_ring(ring):
    """Piedras de un gris cálido y, dentro del anillo y abajo, la ceniza."""
    me = ring.data
    co = np.array([v.co for v in me.vertices])
    radius = np.abs(co[:, :2]).max()
    stone, ash = _linear(PIEDRA), _linear(CENIZA)
    attr = me.color_attributes["Color"]
    painted = 0
    for poly in me.polygons:
        c = poly.center
        is_ash = c.z < CENIZA_ALTO and np.hypot(c.x, c.y) < radius * CENIZA_RADIO
        col = ash if is_ash else stone
        for li in poly.loop_indices:
            attr.data[li].color = (col[0], col[1], col[2], attr.data[li].color[3])
        painted += is_ash
    return painted


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ring = load("fogata_piedras")
    logs = load("fogata_troncos")
    print("CENIZA caras", paint_ring(ring))
    # Los troncos, hundidos un poco en la ceniza para que no floten.
    logs.location = (0, 0, 0.02)
    bpy.ops.object.select_all(action="DESELECT")
    logs.select_set(True)
    ring.select_set(True)
    bpy.context.view_layer.objects.active = ring
    bpy.ops.object.join()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ring.name = ring.data.name = "fogata"
    print("FOGATA medidas", tuple(round(v, 2) for v in ring.dimensions))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OBJ, "fogata.blend"), copy=True)


main()
