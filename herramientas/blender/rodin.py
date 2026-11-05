"""Importa un modelo generado por Hyper3D Rodin, lo escala y orienta como la hoja de giro de Noé,
y lo renderiza desde las mismas 4 vistas para compararlo.

Uso en vivo (con Blender abierto):
    python3 herramientas/blender/en_vivo.py rodin "paso_importar('/ruta/modelo.glb')" "paso_render('/carpeta')"
"""

import math
import os

import bpy
from mathutils import Vector

ROOT = globals().get("PROJECT_ROOT", os.getcwd())
# Reutiliza las luces, cámaras y escala de noe_datos.py (sin ejecutar su main).
_ns = {"EN_VIVO": True, "PROJECT_ROOT": ROOT, "__name__": "noe_datos"}
exec(open(os.path.join(ROOT, "herramientas/blender/noe_datos.py"), encoding="utf-8").read(), _ns)
paso_render = _ns["paso_render"]
HEIGHT = 1.55


def paso_importar(path, yaw_deg=0.0):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    root = bpy.data.objects.new("Rodin", None)
    bpy.context.scene.collection.objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    scale = HEIGHT / (hi.z - lo.z)
    root.scale = (scale, scale, scale)
    root.location = (-(lo.x + hi.x) / 2 * scale, -(lo.y + hi.y) / 2 * scale, -lo.z * scale)
    # Gira alrededor del eje vertical que pasa por el centro.
    bpy.context.view_layer.update()
    pivot = bpy.data.objects.new("RodinGiro", None)
    bpy.context.scene.collection.objects.link(pivot)
    root.parent = pivot
    pivot.rotation_euler = (0, 0, math.radians(yaw_deg))
    print("importado", len(meshes), "mallas, escala", round(scale, 4), "tamaño original", [round(v, 3) for v in (hi - lo)])


def paso_girar(yaw_deg):
    bpy.data.objects["RodinGiro"].rotation_euler = (0, 0, math.radians(yaw_deg))
