"""Junta los objetos de la aldea retocados a mano (un archivo por objeto en herramientas/blender/objetos/)
y los exporta al juego, todos en assets/aldea/generados.glb.

Uso (sin abrir Blender):
    blender --background --factory-startup --python herramientas/blender/exportar_objetos.py

Cada archivo <nombre>.blend tiene un solo objeto de malla, con el origen en el suelo y su color pintado en
los vértices. El objeto toma el nombre del archivo (así se llama la pieza en el juego).
"""

import glob
import os

import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "herramientas/blender/objetos")
OUT = os.path.join(ROOT, "assets/aldea/generados.glb")

bpy.ops.wm.read_factory_settings(use_empty=True)
names = []
for path in sorted(glob.glob(os.path.join(SRC, "*.blend"))):
    name = os.path.splitext(os.path.basename(path))[0]
    with bpy.data.libraries.load(path) as (src, dst):
        dst.objects = list(src.objects)
    meshes = [o for o in dst.objects if o is not None and o.type == "MESH"]
    if len(meshes) != 1:
        print("AVISO", name, "tiene", len(meshes), "mallas; se toma la primera")
    obj = meshes[0]
    bpy.context.scene.collection.objects.link(obj)
    obj.name = name
    obj.location = (0, 0, 0)
    names.append(name)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_yup=True,
                          export_vertex_color="ACTIVE")
print("EXPORTADO", len(names), "objetos ->", OUT)
